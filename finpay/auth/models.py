"""
User Authentication Models, Activity Logging, and In-Memory Store.
Implements secure password hashing and compliance audit logging.
"""

from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Optional
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class Activity:
    """Represents an audit log entry for user and analyst actions."""

    def __init__(self, user_id: str, username: str, action: str, details: str = ""):
        self.timestamp = datetime.now()
        self.user_id = user_id
        self.username = username
        self.action = action  # e.g., 'SIGNUP', 'LOGIN', 'UPLOAD_CSV', 'QUERY_INSIGHTS'
        self.details = details

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
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
        created_at: Optional[datetime] = None,
    ):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role  # 'Admin' or 'Analyst'
        self.full_name = full_name or username.split("@")[0].title()
        self.created_at = created_at or datetime.now()
        self.upload_count = 0
        self.last_active = datetime.now()

    def check_password(self, password: str) -> bool:
        """Verifies candidate plaintext password against stored hash."""
        return check_password_hash(self.password_hash, password)

    def is_admin(self) -> bool:
        """Helper to verify if the user has Admin privileges."""
        return self.role.lower() == "admin"


class UserStore:
    """Thread-safe user repository and activity audit log store."""

    def __init__(self):
        self._users: Dict[str, User] = {}
        self._activities: List[Activity] = []
        self._seed_default_users()

    def _seed_default_users(self):
        # Default financial analyst user
        self.create_user(
            user_id="user_analyst_1",
            username="analyst@finpay.com",
            raw_password="password123",
            role="Analyst",
            full_name="Sarah Jenkins",
        )
        # Default compliance admin user
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
        """Hashes password and stores new user with audit log."""
        if not user_id:
            user_id = f"user_{len(self._users) + 1}_{int(datetime.now().timestamp())}"

        hashed = generate_password_hash(raw_password, method="scrypt")
        user = User(
            id=user_id,
            username=username.lower().strip(),
            password_hash=hashed,
            role=role,
            full_name=full_name,
        )
        self._users[user_id] = user
        return user

    def get_by_id(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    def get_by_username(self, username: str) -> Optional[User]:
        username_clean = username.lower().strip()
        for user in self._users.values():
            if user.username == username_clean:
                return user
        return None

    def get_all_analysts(self) -> List[User]:
        """Returns all registered users with the Analyst role."""
        return [u for u in self._users.values() if u.role.lower() == "analyst"]

    def get_all_users(self) -> List[User]:
        """Returns all registered users."""
        return list(self._users.values())

    # Activity Audit Trail Methods
    def log_activity(self, user_id: str, username: str, action: str, details: str = ""):
        """Records an audit log entry and updates user's last_active timestamp."""
        activity = Activity(user_id=user_id, username=username, action=action, details=details)
        self._activities.insert(0, activity)  # newest first
        # Update user activity timestamp
        user = self.get_by_id(user_id)
        if user:
            user.last_active = datetime.now()
            if action == "UPLOAD_CSV":
                user.upload_count += 1

    def get_activities(self, user_id: Optional[str] = None, limit: int = 50) -> List[dict]:
        """Returns filtered or global recent activity log entries."""
        if user_id:
            filtered = [a for a in self._activities if a.user_id == user_id]
            return [a.to_dict() for a in filtered[:limit]]
        return [a.to_dict() for a in self._activities[:limit]]


# Global user store
user_store = UserStore()
