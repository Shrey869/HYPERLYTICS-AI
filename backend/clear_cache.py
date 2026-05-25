import sqlite3
import os

db_path = os.path.join('data', 'hyperlytics.db')
print('Using DB:', os.path.abspath(db_path))

con = sqlite3.connect(db_path)
tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('Tables:', [t[0] for t in tables])

for (t,) in tables:
    if 'dashboard' in t.lower():
        count = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        con.execute(f'DELETE FROM "{t}"')
        print(f'Cleared {count} rows from "{t}"')

con.commit()
con.close()
print('Done! Fresh dashboard widgets will be generated on next load.')
