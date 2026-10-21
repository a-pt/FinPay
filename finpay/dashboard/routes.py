"""
Dashboard Blueprint for FinPay Insights.
Renders protected analytics views for authenticated financial analysts.
"""

from __future__ import annotations
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from finpay.data.repository import repo

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def home():
    """Redirect root path to dashboard (or login if unauthenticated)."""
    return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/dashboard")
@login_required
def index():
    """
    Protected Financial Analyst Dashboard (Requirements 4 & 5).
    Accessible ONLY to authenticated users. Unauthenticated visitors are
    automatically redirected to /login by the @login_required decorator.
    """
    initial_insights = repo.compute_insights()
    return render_template(
        "dashboard.html",
        user=current_user,
        initial_insights=initial_insights,
    )
