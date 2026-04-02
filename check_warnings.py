import sqlite3

DB='db.sqlite3'
conn=sqlite3.connect(DB)
cur=conn.cursor()
cur.execute("SELECT job_id, message FROM encoder_encodinglog WHERE level='WARNING' LIMIT 15")
print("Recent WARNING messages:")
for row in cur.fetchall():
    print(f"  {row[1]}")
print()
cur.execute("SELECT job_id, message FROM encoder_encodinglog WHERE level='ERROR' LIMIT 5")
print("Recent ERROR messages:")
for row in cur.fetchall():
    print(f"  {row[1]}")
conn.close()
