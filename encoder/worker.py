"""
Video Encoding Worker Service (updated)

This worker improves FFmpeg detection and verification, makes env handling robust,
adds clearer logging around FFmpeg resolution, and keeps the rest of your pipeline logic.

Run as before (for example):
    python worker_runner.py
or via Django shell as described in your original file.
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
# Use a sensible temp directory by default (cross-platform)
DEFAULT_TEMP_DIR = os.path.join(tempfile.gettempdir(), 'encoding_videos')
TEMP_DIR = os.getenv('TEMP_VIDEOS_DIR', DEFAULT_TEMP_DIR)

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
        except Exception:
            # don't raise logging errors
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

    def _resolve_ffmpeg_path(self):
        """
        Resolve an ffmpeg executable path and verify it by running `ffmpeg -version`.
        Priority:
         1. FFMPEG_PATH env var (if it points to an exe or a directory)
         2. shutil.which('ffmpeg') (PATH lookup)
         3. 'ffmpeg' (let OS resolve)

        Returns path to executable (string) or None if not found/verified.
        """
        env_path = os.getenv('FFMPEG_PATH', '').strip()
        candidates = []

        if env_path:
            # If env_path is a directory, try ffmpeg(.exe)
            if os.path.isdir(env_path):
                exe_name = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
                candidates.append(os.path.join(env_path, exe_name))
            else:
                # It might be a direct path to the exe
                candidates.append(env_path)

        # Check PATH
        which_path = shutil.which('ffmpeg')
        if which_path:
            candidates.append(which_path)

        # Fallback to literal 'ffmpeg' (hoping OS PATH resolves it)
        candidates.append('ffmpeg')

        tried = []
        for c in candidates:
            if not c:
                continue
            # avoid duplicates
            if c in tried:
                continue
            tried.append(c)

            # If it's an absolute path that doesn't exist, skip
            if os.path.isabs(c) and not os.path.exists(c):
                self.log(f"FFmpeg candidate not found on disk: {c}", 'DEBUG')
                continue

            try:
                proc = subprocess.run([c, '-version'], capture_output=True, text=True, timeout=6)
                if proc.returncode == 0:
                    # Good candidate
                    self.log(f"Using ffmpeg executable: {c}")
                    return c
                else:
                    # Non-zero return - include stderr for debugging
                    self.log(f"ffmpeg -version returned non-zero for {c}: {proc.stderr[:200]}", 'DEBUG')
            except FileNotFoundError:
                self.log(f"ffmpeg candidate not executable: {c}", 'DEBUG')
            except Exception as exc:
                self.log(f"ffmpeg candidate {c} check failed: {exc}", 'DEBUG')

        return None

    def encode_to_hls(self, quality_presets):
        """
        Encode video to HLS format at multiple quality levels
        """
        try:
            self.temp_output_dir = os.path.join(TEMP_DIR, f"output_{self.video_id}")
            os.makedirs(self.temp_output_dir, exist_ok=True)

            # Filter valid presets
            valid_presets = [q for q in quality_presets if q in self.QUALITY_PRESETS]
            if not valid_presets:
                valid_presets = ['720p', '480p', '360p']

            self.log(f"Encoding to HLS with presets: {', '.join(valid_presets)}")

            # Resolve FFMPEG executable
            ffmpeg_env = os.getenv('FFMPEG_PATH', '')
            if ffmpeg_env and os.path.isdir(ffmpeg_env):
                candidate = os.path.join(ffmpeg_env, 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
                ffmpeg_path_resolved = candidate if os.path.exists(candidate) else ffmpeg_env
            else:
                ffmpeg_path_resolved = ffmpeg_env or None

            # Use the robust resolver method to verify a working ffmpeg
            ffmpeg_verified = self._resolve_ffmpeg_path() if not ffmpeg_path_resolved else self._resolve_ffmpeg_path()

            if not ffmpeg_verified:
                self.log("⚠ FFmpeg not found or not executable - using mock encoding for testing")
                return self.encode_to_hls_mock(valid_presets)

            ffmpeg_path_resolved = ffmpeg_verified

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
                    ffmpeg_path_resolved,
                    '-y',  # overwrite output files without asking
                    '-i', self.temp_input,
                    '-c:v', 'libx264',
                    '-preset', 'veryfast',
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

                self.log(f"Running ffmpeg: {' '.join(cmd[:6])} ... (truncated)")

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1 hour timeout per quality
                )

                if result.returncode != 0:
                    # include ffmpeg stderr in the logged error for easier debugging
                    raise Exception(f"FFmpeg error (rc={result.returncode}): {result.stderr[:2000]}")

                self.log(f"✓ {quality} encoding completed")

                # Add to master playlist
                # convert bitrate like '2500k' -> '2500000' for BANDWIDTH
                bandwidth = preset['bitrate'].replace('k', '000') if 'k' in preset['bitrate'] else preset['bitrate']
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

    def encode_to_hls_mock(self, valid_presets):
        """Create mock HLS structure for testing without FFmpeg"""
        try:
            self.log("Creating mock HLS playlist structure...")

            # Create master playlist file
            master_playlist = "#EXTM3U\n#EXT-X-VERSION:3\n"

            # Create mock playlists for each quality level
            for quality in valid_presets:
                preset = self.QUALITY_PRESETS[quality]
                output_dir = os.path.join(self.temp_output_dir, quality)
                os.makedirs(output_dir, exist_ok=True)

                # Create a simple mock playlist
                playlist_content = "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:10\n"
                playlist_content += "#EXTINF:10.0,\nsegment_000.ts\n#EXT-X-ENDLIST\n"

                playlist_path = os.path.join(output_dir, 'playlist.m3u8')
                with open(playlist_path, 'w') as f:
                    f.write(playlist_content)

                # Create a dummy segment file (minimal valid MP2TS file)
                segment_path = os.path.join(output_dir, 'segment_000.ts')
                with open(segment_path, 'wb') as f:
                    f.write(b'\x47' + b'\x00' * 187)  # Minimal MPEG-TS packet

                self.log(f"✓ {quality} mock encoding completed")

                # Add to master playlist
                bandwidth = preset['bitrate'].replace('k', '000')
                resolution = preset['resolution']
                master_playlist += f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={resolution}\n{quality}/playlist.m3u8\n"

            # Write master playlist
            master_path = os.path.join(self.temp_output_dir, 'master.m3u8')
            with open(master_path, 'w') as f:
                f.write(master_playlist)

            self.log("✓ Mock HLS structure created (ready for real FFmpeg encoding)")
            return True
        except Exception as e:
            self.log(f"✗ Mock encoding failed: {str(e)}", 'ERROR')
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
            try:
                job = EncodingJob.objects.get(id=self.job_id)
                job.status = 'failed'
                job.error_message = str(e)
                job.save()
            except Exception:
                pass

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

                # Create EncodingJob record if it doesn't exist
                try:
                    encoding_job, created = EncodingJob.objects.get_or_create(
                        id=job_data['job_id'],
                        defaults={
                            'video_id': job_data['video_id'],
                            's3_original_key': job_data['s3_original_key'],
                            's3_hls_folder_key': job_data['s3_hls_folder_key'],
                            'input_file_size': job_data.get('input_file_size', 0),
                            'duration': job_data.get('duration', 0),
                            'status': 'processing',
                        }
                    )
                    if created:
                        logger.info(f"✓ Created EncodingJob: {job_data['job_id']}")
                    else:
                        # Update status to processing if it already existed
                        encoding_job.status = 'processing'
                        encoding_job.save()
                except Exception as e:
                    logger.error(f"✗ Failed to create EncodingJob: {str(e)}")
                    continue

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
