"""
User Authentication Models and In-Memory User Store.
Implements secure password hashing.
"""

from __future__ import annotations
from typing import Dict, Optional
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class User(UserMixin):
    """User entity for authentication and authorization."""

    def __init__(self, id: str, username: str, password_hash: str, role: str = "analyst"):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role

    def check_password(self, password: str) -> bool:
        """Verifies candidate plaintext password against stored hash."""
        return check_password_hash(self.password_hash, password)


class UserStore:
    """Thread-safe user repository with pre-seeded demo accounts."""

    def __init__(self):
        self._users: Dict[str, User] = {}
        self._seed_default_users()

    def _seed_default_users(self):
        # Default financial analyst user
        self.create_user(
            user_id="user_1",
            username="analyst@finpay.com",
            raw_password="password123",
            role="Senior Financial Analyst",
        )
        self.create_user(
            user_id="user_2",
            username="admin@finpay.com",
            raw_password="adminpassword",
            role="Admin",
        )

    def create_user(self, user_id: str, username: str, raw_password: str, role: str = "analyst") -> User:
        """Hashes password and stores new user."""
        hashed = generate_password_hash(raw_password, method="scrypt")
        user = User(id=user_id, username=username.lower().strip(), password_hash=hashed, role=role)
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


# Global user store
user_store = UserStore()
