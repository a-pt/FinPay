"""
FinPay Insights - Application Factory.
Configures Flask, Blueprints, Flask-Login authentication, and security headers.
"""

from __future__ import annotations
import os
from flask import Flask
from flask_login import LoginManager

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to access FinPay Insights dashboard."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id: str):
    from finpay.auth.models import user_store
    return user_store.get_by_id(user_id)


def create_app(test_config: dict | None = None) -> Flask:
    """
    Creates and configures an instance of the FinPay Flask application.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Security configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FINPAY_SECRET_KEY", "finpay-secure-development-session-key-4921"),
        JSON_SORT_KEYS=False,
    )

    if test_config:
        app.config.update(test_config)

    # Initialize Flask-Login
    login_manager.init_app(app)

    # Register Blueprints
    from finpay.auth.routes import auth_bp
    from finpay.dashboard.routes import dashboard_bp
    from finpay.api.routes import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp)

    return app
