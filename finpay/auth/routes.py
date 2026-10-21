"""
Authentication Blueprint for FinPay Insights.
Handles login, logout, and session state.
"""

from __future__ import annotations
from urllib.parse import urlparse
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from finpay.auth.models import user_store

auth_bp = Blueprint("auth", __name__)


def is_safe_url(target: str) -> bool:
    """Validates redirect URL to prevent Open Redirect vulnerabilities."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(target)
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc or not test_url.netloc


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
    """Logs out active user and clears session."""
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
            "role": current_user.role,
            "authenticated": True,
        }
    )
