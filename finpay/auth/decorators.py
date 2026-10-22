"""
Role-Based Access Control (RBAC) Decorators.
Protects administrative routes from unauthorized access by regular analysts.
"""

from __future__ import annotations
from functools import wraps
from flask import redirect, url_for, flash, request, abort
from flask_login import current_user


def admin_required(f):
    """
    Ensures that only authenticated users with the 'Admin' role can access the route.
    Redirects regular analysts back to the dashboard with an access denied flash warning.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.url))
        if not current_user.is_admin():
            if request.path.startswith("/api/") or request.is_json:
                return {"error": "Forbidden: Admin access required"}, 403
            flash("Access denied: Administrator privileges required.", "danger")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)

    return decorated_function
