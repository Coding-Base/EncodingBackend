"""
Video Encoding Worker Service
This script runs continuously and processes videos from the Redis queue
Run this as a separate process: python manage.py shell < encoder/worker.py
Or: python worker_runner.py
"""

import os
import sys
import json
import time
import boto3
import subprocess
import tempfile
import shutil
from pathlib import Path
import requests
from django.utils import timezone
from .models import EncodingJob, EncodingLog
from .queue_manager import (
    get_next_job,
    mark_job_completed,
    mark_job_failed,
)
import logging

# Setup logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# AWS S3 Setup
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_S3_REGION_NAME', 'us-east-1'),
)

BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
CLOUDFRONT_DOMAIN = os.getenv('CLOUDFRONT_DOMAIN')
FFMPEG_PATH = os.getenv('FFMPEG_PATH', 'ffmpeg')
TEMP_DIR = os.getenv('TEMP_VIDEOS_DIR', '/tmp/encoding_videos')

# Ensure temp directory exists
Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)


class VideoEncoder:
    """
    Handles video encoding to HLS format
    """
    
    # HLS encoding presets
    QUALITY_PRESETS = {
        '1080p': {
            'bitrate': '5000k',
            'resolution': '1920x1080',
            'fps': '30',
        },
        '720p': {
            'bitrate': '2500k',
            'resolution': '1280x720',
            'fps': '30',
        },
        '480p': {
            'bitrate': '1000k',
            'resolution': '854x480',
            'fps': '30',
        },
        '360p': {
            'bitrate': '500k',
            'resolution': '640x360',
            'fps': '30',
        },
        '240p': {
            'bitrate': '250k',
            'resolution': '426x240',
            'fps': '24',
        },
    }

    def __init__(self, job_id, video_id, s3_original_key, s3_hls_folder_key):
        self.job_id = job_id
        self.video_id = video_id
        self.s3_original_key = s3_original_key
        self.s3_hls_folder_key = s3_hls_folder_key
        self.temp_input = None
        self.temp_output_dir = None

    def log(self, message, level='INFO'):
        """Log message to both logger and EncodingLog"""
        logger.log(getattr(logging, level), message)
        try:
            job = EncodingJob.objects.get(id=self.job_id)
            EncodingLog.objects.create(
                job=job,
                level=level,
                message=message
            )
        except:
            pass

    def download_from_s3(self):
        """Download original video from S3"""
        try:
            self.log(f"Downloading video from S3: {self.s3_original_key}")
            
            self.temp_input = os.path.join(TEMP_DIR, f"input_{self.video_id}.mp4")
            s3_client.download_file(
                BUCKET_NAME,
                self.s3_original_key,
                self.temp_input
            )
            
            file_size = os.path.getsize(self.temp_input)
            self.log(f"✓ Downloaded {file_size / 1024 / 1024:.2f} MB")
            return True
        except Exception as e:
            self.log(f"✗ Download failed: {str(e)}", 'ERROR')
            return False

    def encode_to_hls(self, quality_presets):
        """
        Encode video to HLS format at multiple quality levels
        
        Args:
            quality_presets: List of quality levels (e.g., ['720p', '480p', '360p'])
        """
        try:
            self.temp_output_dir = os.path.join(TEMP_DIR, f"output_{self.video_id}")
            os.makedirs(self.temp_output_dir, exist_ok=True)

            # Filter valid presets
            valid_presets = [q for q in quality_presets if q in self.QUALITY_PRESETS]
            if not valid_presets:
                valid_presets = ['720p', '480p', '360p']

            self.log(f"Encoding to HLS with presets: {', '.join(valid_presets)}")

            # Create master playlist file
            master_playlist = "#EXTM3U\n#EXT-X-VERSION:3\n"
            
            # Encode each quality level
            for quality in valid_presets:
                preset = self.QUALITY_PRESETS[quality]
                output_dir = os.path.join(self.temp_output_dir, quality)
                os.makedirs(output_dir, exist_ok=True)

                self.log(f"Encoding {quality}...")

                # FFmpeg command for HLS encoding
                cmd = [
                    FFMPEG_PATH,
                    '-i', self.temp_input,
                    '-c:v', 'h264',
                    '-c:a', 'aac',
                    '-b:v', preset['bitrate'],
                    '-s', preset['resolution'],
                    '-r', preset['fps'],
                    '-f', 'hls',
                    '-hls_time', '10',  # 10 second segments
                    '-hls_list_size', '0',
                    '-hls_segment_filename', os.path.join(output_dir, f'segment_%03d.ts'),
                    os.path.join(output_dir, 'playlist.m3u8'),
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1 hour timeout
                )

                if result.returncode != 0:
                    raise Exception(f"FFmpeg error: {result.stderr}")

                self.log(f"✓ {quality} encoding completed")

                # Add to master playlist
                bandwidth = preset['bitrate'].replace('k', '000')
                resolution = preset['resolution']
                master_playlist += f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={resolution}\n{quality}/playlist.m3u8\n"

            # Write master playlist
            master_path = os.path.join(self.temp_output_dir, 'master.m3u8')
            with open(master_path, 'w') as f:
                f.write(master_playlist)

            self.log("✓ HLS encoding completed")
            return True
        except Exception as e:
            self.log(f"✗ Encoding failed: {str(e)}", 'ERROR')
            return False

    def upload_hls_to_s3(self):
        """Upload HLS files to S3"""
        try:
            self.log("Uploading HLS files to S3...")
            
            uploaded_files = 0
            for root, dirs, files in os.walk(self.temp_output_dir):
                for file in files:
                    local_path = os.path.join(root, file)
                    # Calculate S3 key
                    relative_path = os.path.relpath(local_path, self.temp_output_dir)
                    s3_key = f"{self.s3_hls_folder_key}/{relative_path}".replace('\\', '/')

                    s3_client.upload_file(local_path, BUCKET_NAME, s3_key)
                    uploaded_files += 1

            self.log(f"✓ Uploaded {uploaded_files} files to S3")
            return True
        except Exception as e:
            self.log(f"✗ S3 upload failed: {str(e)}", 'ERROR')
            return False

    def delete_original_from_s3(self):
        """Delete original video from S3"""
        try:
            self.log("Deleting original video from S3...")
            s3_client.delete_object(Bucket=BUCKET_NAME, Key=self.s3_original_key)
            self.log("✓ Original video deleted from S3")
            return True
        except Exception as e:
            self.log(f"⚠ Failed to delete original: {str(e)}", 'WARNING')
            return False

    def cleanup_temp_files(self):
        """Delete temporary files"""
        try:
            if self.temp_input and os.path.exists(self.temp_input):
                os.remove(self.temp_input)
            if self.temp_output_dir and os.path.exists(self.temp_output_dir):
                shutil.rmtree(self.temp_output_dir)
            self.log("✓ Temporary files cleaned up")
        except Exception as e:
            self.log(f"⚠ Cleanup error: {str(e)}", 'WARNING')

    def notify_main_backend(self, status, error_message=None):
        """Notify main backend of encoding completion"""
        try:
            main_backend_url = os.getenv('MAIN_BACKEND_URL', 'http://localhost:8000/api')
            endpoint = f"{main_backend_url}/videos/{self.video_id}/update-encoding-status/"
            
            data = {
                'status': status,
                'video_id': self.video_id,
            }
            
            if error_message:
                data['error_message'] = error_message

            response = requests.post(endpoint, json=data)
            if response.status_code == 200:
                self.log(f"✓ Main backend notified: {status}")
            else:
                self.log(f"⚠ Backend notification failed: {response.status_code}", 'WARNING')
        except Exception as e:
            self.log(f"⚠ Failed to notify backend: {str(e)}", 'WARNING')

    def process(self, quality_presets):
        """Execute full encoding pipeline"""
        try:
            job = EncodingJob.objects.get(id=self.job_id)
            job.status = 'processing'
            job.started_at = timezone.now()
            job.save()

            self.log(f"Starting encoding for video {self.video_id}")

            # Step 1: Download
            if not self.download_from_s3():
                raise Exception("Download failed")

            # Step 2: Encode
            if not self.encode_to_hls(quality_presets):
                raise Exception("Encoding failed")

            # Step 3: Upload
            if not self.upload_hls_to_s3():
                raise Exception("Upload failed")

            # Step 4: Delete original
            self.delete_original_from_s3()

            # Mark as completed
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.save()

            mark_job_completed(self.job_id, self.video_id)
            self.notify_main_backend('ready')
            self.log("✓ Encoding pipeline completed successfully")

            return True
        except Exception as e:
            self.log(f"✗ Pipeline failed: {str(e)}", 'ERROR')
            job = EncodingJob.objects.get(id=self.job_id)
            job.status = 'failed'
            job.error_message = str(e)
            job.save()
            
            mark_job_failed(self.job_id, self.video_id, str(e))
            self.notify_main_backend('failed', str(e))
            return False
        finally:
            self.cleanup_temp_files()


def run_worker():
    """
    Main worker loop
    Continuously processes jobs from Redis queue
    """
    logger.info("=" * 60)
    logger.info("Video Encoding Worker Started")
    logger.info("=" * 60)
    
    worker_id = os.getenv('WORKER_ID', 'worker-1')
    poll_interval = int(os.getenv('POLL_INTERVAL', '5'))

    while True:
        try:
            # Get next job from queue
            job_data = get_next_job()
            
            if job_data:
                logger.info(f"\n📹 Processing job: {job_data['job_id']}")
                
                encoder = VideoEncoder(
                    job_id=job_data['job_id'],
                    video_id=job_data['video_id'],
                    s3_original_key=job_data['s3_original_key'],
                    s3_hls_folder_key=job_data['s3_hls_folder_key'],
                )
                
                quality_presets = job_data.get('quality_presets', ['720p', '480p', '360p'])
                encoder.process(quality_presets)
            else:
                # No job available, wait before checking again
                time.sleep(poll_interval)

        except KeyboardInterrupt:
            logger.info("\n✓ Worker stopped by user")
            break
        except Exception as e:
            logger.error(f"Worker error: {str(e)}")
            time.sleep(poll_interval)


if __name__ == '__main__':
    run_worker()
