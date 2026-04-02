#!/usr/bin/env python
"""
Migrate stuck jobs from DB 1 back to DB 0 queue
"""
import json
import redis

print("\n=== Redis Job Migration ===\n")

# Connect to both databases
db0 = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
db1 = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)

# Check DB 1 processing queue
stuck_count = db1.llen('video_encoding_processing')
print(f"Found {stuck_count} stuck jobs in DB 1 processing queue")

if stuck_count > 0:
    print("\nMoving jobs back to DB 0 queue...")
    
    moved = 0
    while True:
        # Get job from DB 1 processing queue
        job_json = db1.lpop('video_encoding_processing')
        if not job_json:
            break
        
        try:
            job_data = json.loads(job_json)
            # Push back to DB 0 queue
            db0.rpush('video_encoding_queue', json.dumps(job_data))
            moved += 1
            print(f"  ✓ Moved job {job_data.get('job_id', 'unknown')}")
        except Exception as e:
            print(f"  ✗ Error processing job: {e}")
    
    print(f"\nMoved {moved} jobs from DB 1 → DB 0")
else:
    print("No stuck jobs found")

# Verify final state
print("\n=== Final Queue Status ===\n")
print(f"DB 0 queue: {db0.llen('video_encoding_queue')}")
print(f"DB 0 processing: {db0.llen('video_encoding_processing')}")
print(f"DB 0 completed: {db0.llen('video_encoding_completed')}")
print(f"DB 0 failed: {db0.llen('video_encoding_failed')}")

print(f"\nDB 1 queue: {db1.llen('video_encoding_queue')}")
print(f"DB 1 processing: {db1.llen('video_encoding_processing')}")
print(f"DB 1 completed: {db1.llen('video_encoding_completed')}")
print(f"DB 1 failed: {db1.llen('video_encoding_failed')}")

print("\n✓ Migration complete\n")
