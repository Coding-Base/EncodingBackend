#!/usr/bin/env python
"""Clear all video encoding queues and optionally database records"""
import os
import sys
import django
import redis
from django.conf import settings

# Add the backend to path for Django
sys.path.insert(0, 'c:\\Users\\USER\\Desktop\\Lebanon Acedemy\\backend')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

# Now import Django models
from encoder.models import EncodingJob, EncodingLog

# Connect to Redis
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
r = redis.from_url(redis_url, decode_responses=True)

print("=" * 60)
print("CLEARING ALL VIDEO ENCODING QUEUES AND DATABASE RECORDS")
print("=" * 60)

# Clear Redis queues
queue_keys = [
    'video_encoding_queue',
    'video_encoding_processing',
    'video_encoding_completed',
    'video_encoding_failed'
]

for queue_key in queue_keys:
    count = r.llen(queue_key)
    if count > 0:
        r.delete(queue_key)
        print(f"✓ Cleared {queue_key}: {count} items deleted")
    else:
        print(f"✓ {queue_key}: already empty")

# Clear database records
job_count = EncodingJob.objects.count()
log_count = EncodingLog.objects.count()

if job_count > 0:
    EncodingJob.objects.all().delete()
    print(f"✓ Deleted {job_count} EncodingJob records")
else:
    print(f"✓ EncodingJob: already empty")

if log_count > 0:
    EncodingLog.objects.all().delete()
    print(f"✓ Deleted {log_count} EncodingLog records")
else:
    print(f"✓ EncodingLog: already empty")

print("\n" + "=" * 60)
print("CLEANUP COMPLETE - Ready for fresh test!")
print("=" * 60)
