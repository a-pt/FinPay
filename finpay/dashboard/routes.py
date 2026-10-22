"""
Dashboard Blueprint for FinPay Insights.
Renders protected analytics views for authenticated financial analysts,
and administrative user management & audit feeds for admins.
"""

from __future__ import annotations
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from finpay.auth.decorators import admin_required
from finpay.auth.models import user_store
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
    Accessible to authenticated users. Unauthenticated visitors are redirected to /login.
    - An Analyst can ONLY see their own dashboard.
    - An Admin can optionally view any specific analyst via ?view_user_id=<id>.
    """
    scoped_user_id = current_user.id
    active_analyst_name = current_user.full_name

    # If Admin, allow inspecting a specific analyst's portfolio
    analysts_list = []
    if current_user.is_admin():
        analysts_list = user_store.get_all_analysts()
        view_user_id = request.args.get("view_user_id")
        if view_user_id:
            scoped_user_id = view_user_id
            target_analyst = user_store.get_by_id(view_user_id)
            if target_analyst:
                active_analyst_name = f"{target_analyst.full_name} (Admin Inspection View)"
        else:
            scoped_user_id = "all"
            active_analyst_name = "Global System View (All Analysts)"

    initial_insights = repo.compute_insights(user_id=scoped_user_id)
    user_stats = repo.get_user_stats(scoped_user_id)

    return render_template(
        "dashboard.html",
        user=current_user,
        scoped_user_id=scoped_user_id,
        active_analyst_name=active_analyst_name,
        analysts_list=analysts_list,
        user_stats=user_stats,
        initial_insights=initial_insights,
    )


@dashboard_bp.route("/admin")
@login_required
@admin_required
def admin_portal():
    """
    Administrative Oversight Portal (RBAC Protected).
    Accessible ONLY to users with the 'Admin' role.
    Displays all registered analysts, their upload statistics, and real-time audit activity feed.
    """
    analysts = user_store.get_all_analysts()
    analysts_data = []
    total_system_transactions = 0
    total_system_spent = 0.0

    for a in analysts:
        stats = repo.get_user_stats(a.id)
        total_system_transactions += stats["transaction_count"]
        total_system_spent += stats["total_spent"]
        analysts_data.append(
            {
                "user": a,
                "stats": stats,
            }
        )

    activities = user_store.get_activities(limit=50)

    system_metrics = {
        "total_analysts": len(analysts),
        "total_transactions": total_system_transactions,
        "total_spent": round(total_system_spent, 2),
        "total_activities": len(activities),
    }

    return render_template(
        "admin.html",
        user=current_user,
        analysts_data=analysts_data,
        activities=activities,
        metrics=system_metrics,
    )
