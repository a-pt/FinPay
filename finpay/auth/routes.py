"""
Authentication and Registration Blueprint for FinPay Insights.
Handles signup, login, logout, and user session management with audit logging.
"""

from __future__ import annotations
import re
from urllib.parse import urlparse
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from finpay.auth.models import user_store
from finpay.auth.decorators import admin_required

auth_bp = Blueprint("auth", __name__)


def is_safe_url(target: str) -> bool:
    """Validates redirect URL to prevent Open Redirect vulnerabilities."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(target)
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc or not test_url.netloc


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    """
    User Registration Endpoint.
    Allows new financial analysts to create an account with an isolated workspace.
    """
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation checks
        if not full_name:
            flash("Please enter your full name.", "warning")
            return render_template("signup.html", full_name=full_name, username=username)

        if not username or "@" not in username or "." not in username:
            flash("Please enter a valid email address.", "warning")
            return render_template("signup.html", full_name=full_name, username=username)

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "warning")
            return render_template("signup.html", full_name=full_name, username=username)

        if password != confirm_password:
            flash("Passwords do not match. Please re-enter.", "warning")
            return render_template("signup.html", full_name=full_name, username=username)

        # Check if email is already registered
        existing_user = user_store.get_by_username(username)
        if existing_user:
            flash("An account with this email address already exists. Please log in.", "danger")
            return redirect(url_for("auth.login"))

        # Create new Analyst user
        new_user = user_store.create_user(
            username=username,
            raw_password=password,
            role="Analyst",
            full_name=full_name,
        )

        # Log audit activity
        user_store.log_activity(
            user_id=new_user.id,
            username=new_user.username,
            action="SIGNUP",
            details=f"New analyst account registered: {new_user.full_name}",
        )

        # Automatically authenticate the new user
        login_user(new_user)
        user_store.log_activity(
            user_id=new_user.id,
            username=new_user.username,
            action="LOGIN",
            details="Initial login after registration",
        )

        flash(f"Welcome to FinPay Insights, {new_user.full_name}! Your private analyst workspace is ready.", "success")
        return redirect(url_for("dashboard.index"))

    return render_template("signup.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Renders login view or processes credentials.
    Redirects unauthenticated users attempting to access protected pages.
    """
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        # Supports JSON or form submissions
        if request.is_json:
            data = request.get_json()
            username = data.get("username", "")
            password = data.get("password", "")
        else:
            username = request.form.get("username", "")
            password = request.form.get("password", "")

        user = user_store.get_by_username(username)

        if user and user.check_password(password):
            login_user(user)

            # Audit log
            user_store.log_activity(
                user_id=user.id,
                username=user.username,
                action="LOGIN",
                details=f"Successful sign in (Role: {user.role})",
            )

            next_page = request.args.get("next")
            if next_page and is_safe_url(next_page):
                return redirect(next_page)
            if request.is_json:
                return jsonify({"status": "success", "message": "Logged in successfully", "role": user.role})
            return redirect(url_for("dashboard.index"))

        if request.is_json:
            return jsonify({"status": "error", "message": "Invalid username or password"}), 401

        flash("Invalid email or password. Please try again.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    """Logs out active user and clears session with audit entry."""
    user_store.log_activity(
        user_id=current_user.id,
        username=current_user.username,
        action="LOGOUT",
        details="User logged out",
    )
    logout_user()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/api/me", methods=["GET"])
@login_required
def current_user_profile():
    """Returns details of currently authenticated analyst."""
    return jsonify(
        {
            "id": current_user.id,
            "username": current_user.username,
            "full_name": getattr(current_user, "full_name", current_user.username),
            "role": current_user.role,
            "is_admin": current_user.is_admin(),
            "authenticated": True,
        }
    )
