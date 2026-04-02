#!/usr/bin/env python
"""Clear all video encoding Redis queues"""
import os
import redis

# Connect to Redis
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
print(f"Connecting to: {redis_url}")

try:
    r = redis.from_url(redis_url, decode_responses=True)
    # Test connection
    r.ping()
    print("✓ Connected to Redis\n")
except Exception as e:
    print(f"✗ Failed to connect to Redis: {e}")
    exit(1)

print("=" * 60)
print("CLEARING ALL VIDEO ENCODING QUEUES")
print("=" * 60 + "\n")

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
        print(f"✓ Cleared '{queue_key}': {count} items deleted")
    else:
        print(f"✓ '{queue_key}': already empty")

print("\n" + "=" * 60)
print("REDIS CLEANUP COMPLETE")
print("=" * 60)

# Show final status
print("\nFinal Queue Status:")
for queue_key in queue_keys:
    count = r.llen(queue_key)
    print(f"  {queue_key}: {count}")
