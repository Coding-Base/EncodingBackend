#!/usr/bin/env python
"""
Test Redis connection and job retrieval
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from encoder.queue_manager import redis_client, get_next_job, ENCODING_QUEUE

print("\n=== Redis Worker Test ===\n")

try:
    # Test connection
    print("1. Testing Redis connection...")
    info = redis_client.info("server")
    print(f"   ✓ Redis version: {info['redis_version']}")
    
    # Check queue
    print("\n2. Checking queue status...")
    queue_len = redis_client.llen(ENCODING_QUEUE)
    print(f"   Queue length: {queue_len}")
    
    if queue_len > 0:
        print("\n3. Attempting to get next job...")
        job = get_next_job()
        if job:
            print(f"   ✓ Successfully retrieved job: {job.get('job_id')}")
            print(f"   Video ID: {job.get('video_id')}")
        else:
            print("   ✗ get_next_job() returned None")
    else:
        print("   Note: Queue is empty")
    
    print("\n=== Test Complete ===\n")
    
except Exception as e:
    print(f"\n✗ Error: {str(e)}")
    import traceback
    traceback.print_exc()
