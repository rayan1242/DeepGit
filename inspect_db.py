import sqlite3
from pathlib import Path

DB_FILE = Path("deepsearch.db")

def check_db():
    if not DB_FILE.exists():
        print(f"❌ DB file {DB_FILE} does not exist!")
        return

    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_config'")
        if not c.fetchone():
            print("❌ Table 'user_config' does not exist!")
            conn.close()
            return

        c.execute("SELECT key, value, updated_at FROM user_config")
        rows = c.fetchall()
        conn.close()

        if not rows:
            print("⚠️ Database is empty (no config keys).")
        else:
            print("✅ Database Content:")
            for key, val, updated in rows:
                print(f"  - {key}: {val[:10]}... (updated: {updated})")

    except Exception as e:
        print(f"❌ Error reading DB: {e}")

if __name__ == "__main__":
    check_db()
