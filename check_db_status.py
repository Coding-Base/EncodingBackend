import sqlite3
import os

DB='db.sqlite3'
if not os.path.exists(DB):
    print('DB not found:', DB)
    raise SystemExit(1)
conn=sqlite3.connect(DB)
cur=conn.cursor()

# Check job statuses
cur.execute("SELECT status, COUNT(*) FROM encoder_encodingjob GROUP BY status")
print("Job statuses:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Show last 10 jobs with details
cur.execute("""
SELECT id, video_id, status, created_at, completed_at 
FROM encoder_encodingjob 
ORDER BY created_at DESC 
LIMIT 10
""")
print("\nLast 10 jobs:")
for row in cur.fetchall():
    print(f"  {row[0][:8]}... video={row[1][:8]}... status={row[2]} created={row[3]} completed={row[4]}")

# Check for errors in logs
cur.execute("""
SELECT job_id, level, COUNT(*) 
FROM encoder_encodinglog 
WHERE level IN ('ERROR', 'WARNING')
GROUP BY job_id, level
ORDER BY job_id DESC
LIMIT 5
""")
print("\nRecent errors/warnings in logs:")
for row in cur.fetchall():
    print(f"  job={row[0][:8]}... level={row[1]} count={row[2]}")

conn.close()
