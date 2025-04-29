import sqlite3
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

def setup_database():
    # Create data directory if it doesn't exist
    data_dir = Path(__file__).parent.resolve() / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Get database path from environment or use default
    db_path = os.getenv("SQLITE_DB_PATH", str(data_dir / "presentation_bot.db"))
    
    # Connect to SQLite database (creates it if it doesn't exist)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            last_interaction TEXT,
            first_seen TEXT,
            current_chat_mode TEXT DEFAULT 'auto',
            is_premium INTEGER DEFAULT 0,
            presentations_created INTEGER DEFAULT 0,
            abstracts_created INTEGER DEFAULT 0
        )
        ''')
        print("Users table created or already exists.")
        
        # Create dialogs table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS dialogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TEXT,
            message TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        print("Dialogs table created or already exists.")
        
        # Create admins table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (added_by) REFERENCES users(user_id)
        )
        ''')
        print("Admins table created or already exists.")
        
        # Create required_channels table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS required_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            channel_name TEXT NOT NULL,
            channel_link TEXT NOT NULL,
            added_by INTEGER,
            added_at TEXT,
            FOREIGN KEY (added_by) REFERENCES users(user_id)
        )
        ''')
        print("Required channels table created or already exists.")
        
        # Add default admin if specified in environment
        default_admin = os.getenv("DEFAULT_ADMIN_ID")
        if default_admin:
            try:
                admin_id = int(default_admin)
                cursor.execute(
                    "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
                    (admin_id, admin_id, datetime.now().isoformat())
                )
                print(f"Default admin (ID: {admin_id}) added or already exists.")
            except (ValueError, sqlite3.Error) as e:
                print(f"Error adding default admin: {e}")
        
        conn.commit()
        print(f"Database setup completed successfully at {db_path}!")
        
    except sqlite3.Error as err:
        print(f"Error: {err}")
    finally:
        if 'conn' in locals():
            cursor.close()
            conn.close()
            print("SQLite connection closed.")

if __name__ == "__main__":
    setup_database()
