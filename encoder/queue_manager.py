"""
Redis Queue Manager for handling encoding jobs
"""
import json
import redis
import os
import uuid
from django.conf import settings

# Initialize Redis connection
# NOTE: The main backend uses DB 0. EncodingBackend must use the same DB.
# When using redis.from_url() with a URL that already has a database number (e.g., redis://localhost:6379/0),
# the db parameter is ignored. We need to properly parse and handle the database from the URL.

redis_url = os.getenv('REDIS_URL') or os.getenv('CELERY_BROKER_URL') or 'redis://localhost:6379/0'

# Parse database from URL if present, otherwise use from environment
redis_db = 0  # Default to DB 0 to match main backend
if 'redis://' in redis_url and '/' in redis_url.split('redis://')[-1]:
    # Extract db number from URL (e.g., redis://localhost:6379/0 -> db=0)
    try:
        db_from_url = int(redis_url.split('/')[-1])
        redis_db = db_from_url
    except (ValueError, IndexError):
        redis_db = 0

# Allow environment variable to override
if os.getenv('REDIS_DB'):
    redis_db = int(os.getenv('REDIS_DB'))

# Create Redis client - use parsed database number
if redis_url and redis_url.startswith('redis://'):
    try:
        # Create from URL but ensure we use the right database
        redis_client = redis.from_url(redis_url, decode_responses=True)
        # redis.from_url respects the database in the URL, so this should work
    except Exception as e:
        print(f"Warning: redis.from_url failed ({e}), falling back to direct connection")
        # Fallback: parse URL manually
        try:
            from urllib.parse import urlparse
            parsed = urlparse(redis_url)
            redis_host = parsed.hostname or 'localhost'
            redis_port = parsed.port or 6379
            redis_password = parsed.password or None
            redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, password=redis_password, decode_responses=True)
        except Exception:
            redis_host = os.getenv('REDIS_HOST', 'localhost')
            redis_port = int(os.getenv('REDIS_PORT', 6379))
            redis_password = os.getenv('REDIS_PASSWORD') or None
            redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, password=redis_password, decode_responses=True)
else:
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = int(os.getenv('REDIS_PORT', 6379))
    redis_password = os.getenv('REDIS_PASSWORD') or None
    redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, password=redis_password, decode_responses=True)

# Queue names
ENCODING_QUEUE = 'video_encoding_queue'
ENCODING_PROCESSING = 'video_encoding_processing'
ENCODING_COMPLETED = 'video_encoding_completed'
ENCODING_FAILED = 'video_encoding_failed'


def queue_encoding_job(job_id, video_id, s3_original_key, s3_hls_folder_key, quality_presets):
    """
    Add a new encoding job to Redis queue
    
    Args:
        job_id: UUID of the encoding job
        video_id: UUID of the video in main backend
        s3_original_key: Path to original video in S3
        s3_hls_folder_key: Path where HLS segments should be saved
        quality_presets: List of quality levels (e.g., ['720p', '480p', '360p'])
    
    Returns:
        bool: True if job was queued successfully
    """
    job_data = {
        'job_id': job_id,
        'video_id': video_id,
        's3_original_key': s3_original_key,
        's3_hls_folder_key': s3_hls_folder_key,
        'quality_presets': quality_presets,
    }
    
    try:
        # Push to queue
        redis_client.rpush(ENCODING_QUEUE, json.dumps(job_data))
        print(f"✓ Encoding job {job_id} queued for video {video_id}")
        return True
    except Exception as e:
        print(f"✗ Error queueing job {job_id}: {str(e)}")
        return False


def get_next_job():
    """
    Get the next encoding job from the queue
    
    Returns:
        dict: Job data or None if queue is empty
    """
    try:
        job_json = redis_client.lpop(ENCODING_QUEUE)
        if job_json:
            job_data = json.loads(job_json)

            # Ensure job_data has a job_id (backwards-compat with older producers)
            if isinstance(job_data, dict):
                if 'job_id' not in job_data or not job_data.get('job_id'):
                    # Prefer video_id when available, otherwise create a UUID
                    job_data['job_id'] = job_data.get('video_id') or str(uuid.uuid4())

            # Move to processing queue
            redis_client.rpush(ENCODING_PROCESSING, json.dumps(job_data))
            return job_data
        return None
    except Exception as e:
        error_msg = f"Error getting job from queue: {str(e)}"
        print(f"✗ {error_msg}")
        try:
            import logging as log_module
            logger = log_module.getLogger(__name__)
            logger.error(error_msg, exc_info=True)
        except:
            pass
        return None


def mark_job_completed(job_id, video_id):
    """
    Mark a job as completed and remove from processing queue
    
    Args:
        job_id: UUID of the encoding job
        video_id: UUID of the video
    """
    try:
        # Add to completed queue for audit
        redis_client.rpush(ENCODING_COMPLETED, json.dumps({
            'job_id': job_id,
            'video_id': video_id,
        }))
        print(f"✓ Job {job_id} marked as completed")
    except Exception as e:
        print(f"Error marking job as completed: {str(e)}")


def mark_job_failed(job_id, video_id, error_message):
    """
    Mark a job as failed and remove from processing queue
    
    Args:
        job_id: UUID of the encoding job
        video_id: UUID of the video
        error_message: Error description
    """
    try:
        redis_client.rpush(ENCODING_FAILED, json.dumps({
            'job_id': job_id,
            'video_id': video_id,
            'error': error_message,
        }))
        print(f"✗ Job {job_id} marked as failed: {error_message}")
    except Exception as e:
        print(f"Error marking job as failed: {str(e)}")


def get_queue_stats():
    """
    Get statistics about queue status
    
    Returns:
        dict: Queue statistics
    """
    try:
        pending = redis_client.llen(ENCODING_QUEUE)
        processing = redis_client.llen(ENCODING_PROCESSING)
        completed = redis_client.llen(ENCODING_COMPLETED)
        failed = redis_client.llen(ENCODING_FAILED)
        
        return {
            'pending_jobs': pending,
            'processing_jobs': processing,
            'completed_jobs': completed,
            'failed_jobs': failed,
            'total_jobs': pending + processing + completed + failed,
        }
    except Exception as e:
        return {
            'error': str(e),
        }


def get_job_status():
    """
    Get detailed queue status
    
    Returns:
        dict: Detailed queue information
    """
    return get_queue_stats()


def clear_queue(queue_name=ENCODING_QUEUE):
    """
    Clear a queue (for testing/cleanup)
    
    Args:
        queue_name: Name of the queue to clear
    """
    try:
        redis_client.delete(queue_name)
        print(f"✓ Queue {queue_name} cleared")
        return True
    except Exception as e:
        print(f"Error clearing queue: {str(e)}")
        return False


def test_redis_connection():
    """
    Test Redis connection
    
    Returns:
        bool: True if connection successful
    """
    try:
        redis_client.ping()
        print("✓ Redis connection successful")
        return True
    except Exception as e:
        print(f"✗ Redis connection failed: {str(e)}")
        return False
