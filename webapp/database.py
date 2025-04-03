import sqlite3
import os
from datetime import datetime, timedelta, timezone

DATABASE_PATH = os.getenv("DATABASE_PATH", "../data/database/metadata.db")
UPLOAD_TOKEN_EXPIRY_SECONDS = int(os.getenv("UPLOAD_TOKEN_EXPIRY_SECONDS", 3600))

# Ensure the directory for the database exists
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)


def get_db():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Return rows as dictionary-like objects
    return conn


def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = get_db()
    cursor = conn.cursor()
    # Create upload_tokens table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS upload_tokens (
            token TEXT PRIMARY KEY,
            expiry DATETIME NOT NULL,
            context_user_id TEXT NOT NULL,
            context_channel_id TEXT NOT NULL
        )
    """
    )
    # Create uploads table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS uploads (
            file_id TEXT PRIMARY KEY,
            original_filename TEXT NOT NULL,
            cached_path TEXT,
            nas_path TEXT,
            status TEXT NOT NULL, -- 'cached', 'uploading_to_nas', 'on_nas', 'error'
            upload_timestamp DATETIME NOT NULL,
            context_user_id TEXT NOT NULL,
            context_channel_id TEXT NOT NULL,
            content_type TEXT,
            file_size INTEGER
        )
    """
    )
    # Create bot_notifications table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_notifications (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    # Index for faster lookup? Optional.
    # cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_created ON bot_notifications (created_at);')
    conn.commit()
    conn.close()
    print("Database initialized (including bot_notifications table).")


# --- Token Functions ---


def add_upload_token(token, context):
    """Adds a new upload token to the database."""
    conn = get_db()
    expiry_time = datetime.now(timezone.utc) + timedelta(
        seconds=UPLOAD_TOKEN_EXPIRY_SECONDS
    )
    try:
        conn.execute(
            "INSERT INTO upload_tokens (token, expiry, context_user_id, context_channel_id) VALUES (?, ?, ?, ?)",
            (
                token,
                expiry_time,
                str(context.get("user_id")),
                str(context.get("channel_id")),
            ),
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error adding token: {e}")
        return False
    finally:
        conn.close()
    return True


def get_token_context(token):
    """Retrieves the context associated with a valid token."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc)
    cursor.execute(
        "SELECT context_user_id, context_channel_id FROM upload_tokens WHERE token = ? AND expiry > ?",
        (token, now),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row["context_user_id"],
            "channel_id": row["context_channel_id"],
        }
    return None


def delete_token(token):
    """Deletes a token from the database."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM upload_tokens WHERE token = ?", (token,))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error deleting token: {e}")
    finally:
        conn.close()


def cleanup_expired_tokens():
    """Removes expired tokens from the database."""
    conn = get_db()
    now = datetime.now(timezone.utc)
    try:
        cursor = conn.execute("DELETE FROM upload_tokens WHERE expiry <= ?", (now,))
        deleted_count = cursor.rowcount
        conn.commit()
        if deleted_count > 0:
            print(f"Cleaned up {deleted_count} expired upload tokens.")
    except sqlite3.Error as e:
        print(f"Database error cleaning up tokens: {e}")
    finally:
        conn.close()


# --- Upload Metadata Functions ---


def add_upload_record(
    file_id, original_filename, cached_path, context, content_type=None, file_size=None
):
    """Adds a record for a newly uploaded file."""
    conn = get_db()
    now = datetime.now(timezone.utc)
    try:
        conn.execute(
            """INSERT INTO uploads (file_id, original_filename, cached_path, status, upload_timestamp,
                                context_user_id, context_channel_id, content_type, file_size)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                file_id,
                original_filename,
                cached_path,
                "cached",
                now,
                str(context.get("user_id")),
                str(context.get("channel_id")),
                content_type,
                file_size,
            ),
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error adding upload record: {e}")
        return False
    finally:
        conn.close()
    return True


def get_upload_record(file_id):
    """Retrieves an upload record by file_id."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM uploads WHERE file_id = ?", (file_id,))
    row = cursor.fetchone()
    conn.close()
    return row  # Returns a Row object or None


def update_upload_status(file_id, status, nas_path=None):
    """Updates the status and optionally the NAS path of an upload record."""
    conn = get_db()
    try:
        if nas_path:
            conn.execute(
                "UPDATE uploads SET status = ?, nas_path = ? WHERE file_id = ?",
                (status, nas_path, file_id),
            )
        else:
            conn.execute(
                "UPDATE uploads SET status = ? WHERE file_id = ?", (status, file_id)
            )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error updating upload status for {file_id}: {e}")
        return False
    finally:
        conn.close()
    return True


def get_uploads_by_status(status):
    """Retrieves all upload records with a specific status."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM uploads WHERE status = ?", (status,))
    rows = cursor.fetchall()
    conn.close()
    return rows  # Returns a list of Row objects


def delete_upload_record(file_id):
    """Deletes an upload record (use with caution)."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM uploads WHERE file_id = ?", (file_id,))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error deleting upload record {file_id}: {e}")
        return False
    finally:
        conn.close()
    return True


# --- Bot Notification Functions ---


def add_bot_notification(file_id, context, original_filename):
    """Adds a notification for the bot to process."""
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO bot_notifications (file_id, channel_id, user_id, original_filename)
               VALUES (?, ?, ?, ?)""",
            (
                file_id,
                str(context.get("channel_id")),
                str(context.get("user_id")),
                original_filename,
            ),
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error adding bot notification for {file_id}: {e}")
        return False
    finally:
        conn.close()
    return True


def get_pending_notifications():
    """Retrieves all pending bot notifications."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM bot_notifications ORDER BY created_at ASC")
        rows = cursor.fetchall()
        return rows  # List of Row objects
    except sqlite3.Error as e:
        print(f"Database error getting pending notifications: {e}")
        return []
    finally:
        conn.close()


def delete_notification(notification_id):
    """Deletes a processed notification by its ID."""
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM bot_notifications WHERE notification_id = ?",
            (notification_id,),
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error deleting notification {notification_id}: {e}")
        return False
    finally:
        conn.close()
    return True


# Initialize the database when this module is loaded
init_db()
