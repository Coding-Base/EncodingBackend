import sqlite3
import os

DB='db.sqlite3'
if not os.path.exists(DB):
    print('DB not found:', DB)
    raise SystemExit(1)
conn=sqlite3.connect(DB)
cur=conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print('tables:', cur.fetchall())

for t in ['encoder_encodingjob','encoder_encodinglog']:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"{t}:", cur.fetchone()[0])
    except Exception as e:
        print(f"{t} error:", e)

conn.close()
