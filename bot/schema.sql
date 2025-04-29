-- Adminlar jadvali
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY,
    added_by INTEGER,
    added_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (added_by) REFERENCES users(user_id)
);

-- Majburiy kanallar jadvali
CREATE TABLE IF NOT EXISTS required_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    channel_link TEXT NOT NULL,
    added_by INTEGER,
    added_at TEXT,
    FOREIGN KEY (added_by) REFERENCES users(user_id)
);

-- Boshlang'ich admin qo'shish
INSERT OR IGNORE INTO admins (user_id, added_by, added_at)
VALUES (123456789, 123456789, datetime('now'));
-- Bu yerda 123456789 o'rniga o'zingizning Telegram ID raqamingizni qo'ying
