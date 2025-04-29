from datetime import datetime
from typing import Any, Dict, List, Optional
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Database:
    def __init__(self):
        # Get database path from environment or use default
        db_dir = Path(__file__).parent.parent.resolve() / "data"
        db_dir.mkdir(exist_ok=True)
        
        self.db_path = os.getenv("SQLITE_DB_PATH", str(db_dir / "presentation_bot.db"))
        
        # Initialize database if not exists
        self._initialize_database()

    def _get_connection(self):
        """Get a connection to the SQLite database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # This enables column access by name
        return conn

    def _initialize_database(self):
        """Create tables if they don't exist"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
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
            
            # Create dialogs table if needed
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS dialogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                timestamp TEXT,
                message TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            ''')
            
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
            
            # Add default admin if specified in environment
            default_admin = os.getenv("DEFAULT_ADMIN_ID")
            if default_admin:
                try:
                    admin_id = int(default_admin)
                    cursor.execute(
                        "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
                        (admin_id, admin_id, datetime.now().isoformat())
                    )
                except (ValueError, sqlite3.Error) as e:
                    print(f"Error adding default admin: {e}")
            
            conn.commit()
        except Exception as e:
            print(f"Error initializing database: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    def check_if_user_exists(self, user_id: int, raise_exception: bool = False):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            count = result['count'] if result else 0
            
            if count > 0:
                return True
            else:
                if raise_exception:
                    raise ValueError(f"User {user_id} does not exist")
                else:
                    return False
        finally:
            cursor.close()
            conn.close()

    def add_new_user(
        self,
        user_id: int,
        chat_id: int,
        username: str = "",
        first_name: str = "",
        last_name: str = "",
    ):
        if not self.check_if_user_exists(user_id):
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                now = datetime.now().isoformat()
                cursor.execute(
                    """
                    INSERT INTO users 
                    (user_id, chat_id, username, first_name, last_name, last_interaction, first_seen, 
                    current_chat_mode, is_premium, presentations_created, abstracts_created)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, chat_id, username, first_name, last_name, now, now, 
                    "auto", 0, 0, 0)
                )
                conn.commit()
            except Exception as e:
                print(f"Error adding new user: {e}")
                conn.rollback()
            finally:
                cursor.close()
                conn.close()

    def get_user_attribute(self, user_id: int, key: str):
        self.check_if_user_exists(user_id, raise_exception=True)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"SELECT {key} FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            if result is None:
                raise ValueError(f"User {user_id} does not have a value for {key}")
                
            return result[key]
        finally:
            cursor.close()
            conn.close()

    def set_user_attribute(self, user_id: int, key: str, value: Any):
        self.check_if_user_exists(user_id, raise_exception=True)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
            conn.commit()
        except Exception as e:
            print(f"Error updating user attribute: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    
    def increment_user_counter(self, user_id: int, counter_name: str):
        """Increment a counter for a user (presentations_created or abstracts_created)"""
        self.check_if_user_exists(user_id, raise_exception=True)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"UPDATE users SET {counter_name} = {counter_name} + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            
            # Return the new value
            cursor.execute(f"SELECT {counter_name} FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result[counter_name]
        except Exception as e:
            print(f"Error incrementing user counter: {e}")
            conn.rollback()
            return None
        finally:
            cursor.close()
            conn.close()
    
    def set_premium_status(self, user_id: int, is_premium: bool):
        """Set premium status for a user"""
        self.check_if_user_exists(user_id, raise_exception=True)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("UPDATE users SET is_premium = ? WHERE user_id = ?", (1 if is_premium else 0, user_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error setting premium status: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()
    
    def is_premium(self, user_id: int) -> bool:
        """Check if a user has premium status"""
        try:
            return bool(self.get_user_attribute(user_id, "is_premium"))
        except:
            return False
    
    # Admin functions
    def is_admin(self, user_id: int) -> bool:
        """Check if a user is an admin"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) as count FROM admins WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result['count'] > 0
        finally:
            cursor.close()
            conn.close()
    
    def set_admin_status(self, user_id: int, is_admin: bool, added_by: Optional[int] = None) -> bool:
        """Set or remove admin status for a user"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if is_admin:
                # Add admin
                cursor.execute(
                    "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
                    (user_id, added_by or user_id, datetime.now().isoformat())
                )
            else:
                # Remove admin
                cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Error setting admin status: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()
    
    def get_all_admins(self) -> List[Dict]:
        """Get all admins"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT a.user_id, u.username, u.first_name, u.last_name, a.added_at
                FROM admins a
                LEFT JOIN users u ON a.user_id = u.user_id
            """)
            
            admins = []
            for row in cursor.fetchall():
                admins.append(dict(row))
            
            return admins
        finally:
            cursor.close()
            conn.close()
    
    # Required channels functions
    def add_required_channel(self, channel_id: str, channel_name: str, channel_link: str, added_by: int) -> int:
        """Add a required channel"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                INSERT INTO required_channels (channel_id, channel_name, channel_link, added_by, added_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (channel_id, channel_name, channel_link, added_by, datetime.now().isoformat())
            )
            
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"Error adding required channel: {e}")
            conn.rollback()
            return 0
        finally:
            cursor.close()
            conn.close()
    
    def remove_required_channel(self, channel_id: str) -> bool:
        """Remove a required channel"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM required_channels WHERE channel_id = ?", (channel_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error removing required channel: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()
    
    def get_all_required_channels(self) -> List[Dict]:
        """Get all required channels"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM required_channels")
            
            channels = []
            for row in cursor.fetchall():
                channels.append(dict(row))
            
            return channels
        finally:
            cursor.close()
            conn.close()
    
    def get_required_channel(self, channel_id: str) -> Optional[Dict]:
        """Get a specific required channel"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM required_channels WHERE channel_id = ?", (channel_id,))
            
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
        finally:
            cursor.close()
            conn.close()
