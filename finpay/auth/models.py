"""
User Authentication Models, Activity Logging, and SQLite Database Store.
Provides persistent storage across server restarts with secure password hashing.
"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Dict, List, Optional
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "finpay.db"


class Activity:
    """Represents an audit log entry for user and analyst actions."""

    def __init__(self, user_id: str, username: str, action: str, details: str = "", timestamp: Optional[datetime] = None):
        self.timestamp = timestamp or datetime.now()
        self.user_id = user_id
        self.username = username
        self.action = action  # e.g., 'SIGNUP', 'LOGIN', 'UPLOAD_CSV', 'PROFILE_UPDATE', 'PASSWORD_CHANGE'
        self.details = details

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "user_id": self.user_id,
            "username": self.username,
            "action": self.action,
            "details": self.details,
        }


class User(UserMixin):
    """User entity for authentication and authorization."""

    def __init__(
        self,
        id: str,
        username: str,
        password_hash: str,
        role: str = "Analyst",
        full_name: str = "",
        upload_count: int = 0,
        created_at: Optional[datetime] = None,
        last_active: Optional[datetime] = None,
    ):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role  # 'Admin' or 'Analyst'
        self.full_name = full_name or username.split("@")[0].title()
        self.upload_count = upload_count
        self.created_at = created_at or datetime.now()
        self.last_active = last_active or datetime.now()

    def check_password(self, password: str) -> bool:
        """Verifies candidate plaintext password against stored hash."""
        return check_password_hash(self.password_hash, password)

    def set_password(self, new_password: str) -> None:
        """Hashes and updates user password."""
        self.password_hash = generate_password_hash(new_password, method="scrypt")
        # Update in database
        user_store.update_user_password(self.id, self.password_hash)

    def is_admin(self) -> bool:
        """Helper to verify if the user has Admin privileges."""
        return self.role.lower() == "admin"


class UserStore:
    """
    Persistent SQLite-backed repository for Users and Activity Audit logs.
    Preserves user accounts and audit history across server restarts.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = str(db_path)
        self._init_db()
        self._seed_default_users()

    def _get_connection(self) -> sqlite3.Connection:
        """Thread-safe connection provider with Row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates tables if they do not exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'Analyst',
                    full_name TEXT NOT NULL,
                    upload_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_active TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _row_to_user(self, row: sqlite3.Row) -> User:
        """Converts an SQLite row into a User object."""
        try:
            created_at = datetime.fromisoformat(row["created_at"])
        except Exception:
            created_at = datetime.now()

        try:
            last_active = datetime.fromisoformat(row["last_active"])
        except Exception:
            last_active = datetime.now()

        return User(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            role=row["role"],
            full_name=row["full_name"],
            upload_count=int(row["upload_count"]),
            created_at=created_at,
            last_active=last_active,
        )

    def _seed_default_users(self):
        """Seeds default analyst and admin accounts if not already present."""
        if not self.get_by_username("analyst@finpay.com"):
            self.create_user(
                user_id="user_analyst_1",
                username="analyst@finpay.com",
                raw_password="password123",
                role="Analyst",
                full_name="Sarah Jenkins",
            )
        if not self.get_by_username("admin@finpay.com"):
            self.create_user(
                user_id="user_admin_1",
                username="admin@finpay.com",
                raw_password="adminpassword",
                role="Admin",
                full_name="Alex Rivera (System Admin)",
            )

    def create_user(
        self,
        user_id: Optional[str] = None,
        username: str = "",
        raw_password: str = "",
        role: str = "Analyst",
        full_name: str = "",
    ) -> User:
        """Hashes password and permanently stores new user in SQLite."""
        clean_username = username.lower().strip()
        if not user_id:
            user_id = f"user_{int(datetime.now().timestamp() * 1000)}"

        hashed = generate_password_hash(raw_password, method="scrypt")
        now = datetime.now().isoformat()
        name = full_name.strip() if full_name else clean_username.split("@")[0].title()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO users (id, username, password_hash, role, full_name, upload_count, created_at, last_active)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (user_id, clean_username, hashed, role, name, now, now),
            )
            conn.commit()

        return self.get_by_id(user_id)

    def get_by_id(self, user_id: str) -> Optional[User]:
        """Fetches user by primary key ID."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cur.fetchone()
            if row:
                return self._row_to_user(row)
        return None

    def get_by_username(self, username: str) -> Optional[User]:
        """Fetches user by unique username/email."""
        clean_username = username.lower().strip()
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM users WHERE username = ?", (clean_username,))
            row = cur.fetchone()
            if row:
                return self._row_to_user(row)
        return None

    def get_all_analysts(self) -> List[User]:
        """Returns all registered users with role 'Analyst'."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM users WHERE LOWER(role) = 'analyst' ORDER BY created_at ASC")
            return [self._row_to_user(r) for r in cur.fetchall()]

    def get_all_users(self) -> List[User]:
        """Returns all registered users."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM users ORDER BY created_at ASC")
            return [self._row_to_user(r) for r in cur.fetchall()]

    def update_user_profile(
        self,
        user_id: str,
        full_name: Optional[str] = None,
        username: Optional[str] = None,
    ) -> User:
        """Updates user profile fields in SQLite with uniqueness validation."""
        user = self.get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        clean_username = user.username
        if username:
            clean_username = username.lower().strip()
            existing = self.get_by_username(clean_username)
            if existing and existing.id != user_id:
                raise ValueError(f"Email '{clean_username}' is already in use by another user.")

        clean_name = full_name.strip() if full_name else user.full_name

        with self._get_connection() as conn:
            conn.execute(
                "UPDATE users SET full_name = ?, username = ? WHERE id = ?",
                (clean_name, clean_username, user_id),
            )
            conn.commit()

        return self.get_by_id(user_id)

    def update_user_password(self, user_id: str, password_hash: str) -> None:
        """Persists updated password hash in SQLite."""
        with self._get_connection() as conn:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
            conn.commit()

    # Activity Audit Trail Methods
    def log_activity(self, user_id: str, username: str, action: str, details: str = ""):
        """Records an audit log entry in SQLite and updates last_active timestamp."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO activities (timestamp, user_id, username, action, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now, user_id, username, action, details),
            )
            if action == "UPLOAD_CSV":
                conn.execute(
                    "UPDATE users SET last_active = ?, upload_count = upload_count + 1 WHERE id = ?",
                    (now, user_id),
                )
            else:
                conn.execute("UPDATE users SET last_active = ? WHERE id = ?", (now, user_id))
            conn.commit()

    def get_activities(self, user_id: Optional[str] = None, limit: int = 50) -> List[dict]:
        """Returns recent activity audit log entries from SQLite."""
        with self._get_connection() as conn:
            if user_id:
                cur = conn.execute(
                    "SELECT * FROM activities WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                    (user_id, limit),
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM activities ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            rows = cur.fetchall()
            return [
                {
                    "timestamp": r["timestamp"][:19].replace("T", " "),
                    "user_id": r["user_id"],
                    "username": r["username"],
                    "action": r["action"],
                    "details": r["details"],
                }
                for r in rows
            ]

    def reset_for_testing(self):
        """Removes test users and activities to ensure test isolation."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM users WHERE id NOT IN ('user_analyst_1', 'user_admin_1')")
            conn.execute("DELETE FROM activities")
            # Reset default analyst details
            conn.execute(
                "UPDATE users SET full_name = 'Sarah Jenkins', username = 'analyst@finpay.com', upload_count = 0 WHERE id = 'user_analyst_1'"
            )
            conn.commit()


# Global user store
user_store = UserStore()
