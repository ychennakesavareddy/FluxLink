import os
import sqlite3
from backend.repository import get_repository, SqliteRepository, SQLITE_SCHEMA

DB_PATH = os.path.join(os.path.dirname(__file__), "chennalink.db")

def init_db():
    repo = get_repository()
    repo.init_schema()
    
    # Also ensure legacy SQLite compatibility for existing tables
    if isinstance(repo, SqliteRepository):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # Legacy devices table if needed
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    device_id TEXT,
                    device_name TEXT,
                    name TEXT,
                    email TEXT,
                    device_type TEXT,
                    connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (id)
                )
            ''')
            conn.commit()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
