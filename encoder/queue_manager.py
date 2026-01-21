"""
Redis Queue Manager for handling encoding jobs
"""
import json
import redis
import os
from django.conf import settings

# Initialize Redis connection
redis_url = os.getenv('REDIS_URL') or os.getenv('CELERY_BROKER_URL')
redis_db = int(os.getenv('REDIS_DB', 1))
if redis_url:
    try:
        redis_client = redis.from_url(redis_url, db=redis_db, decode_responses=True)
    except Exception:
        # fallback to host/port
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        redis_password = os.getenv('REDIS_PASSWORD', None)
        redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, password=redis_password, decode_responses=True)
else:
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = int(os.getenv('REDIS_PORT', 6379))
    redis_password = os.getenv('REDIS_PASSWORD', None)
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
            # Move to processing queue
            redis_client.rpush(ENCODING_PROCESSING, json.dumps(job_data))
            return job_data
        return None
    except Exception as e:
        print(f"Error getting job from queue: {str(e)}")
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
