#!/usr/bin/env python
"""
Check Redis encoding queues for the EncodingBackend.
Run from EncodingBackend directory: `python check_queue.py`
"""
import os
import json
import sys
try:
    import redis
except Exception as e:
    print("redis module not available:", e)
    sys.exit(1)

redis_url = os.getenv('REDIS_URL') or 'redis://localhost:6379/0'
print(f"Using REDIS_URL={redis_url}")

try:
    # Use the URL as-is, which includes the database number
    client = redis.from_url(redis_url, decode_responses=True)
except Exception as e:
    print('Failed to connect to Redis:', e)
    sys.exit(1)

queues = [
    'video_encoding_queue',
    'video_encoding_processing',
    'video_encoding_completed',
    'video_encoding_failed'
]

for q in queues:
    try:
        length = client.llen(q)
        print(f"{q}: {length}")
        if length > 0:
            sample = client.lrange(q, 0, 4)
            try:
                parsed = [json.loads(x) if isinstance(x, str) else x for x in sample]
            except Exception:
                parsed = sample
            print('  sample:', parsed)
    except Exception as e:
        print(f"Error reading queue {q}: {e}")

# Show last 5 items in the processing queue (if any)
try:
    if client.llen('video_encoding_processing') > 0:
        proc = client.lrange('video_encoding_processing', 0, 4)
        print('processing_sample:', proc)
except Exception:
    pass

print('\nDone.')
