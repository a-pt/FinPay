"""
FinPay Insights - Application Factory.
Configures and initializes Flask, Blueprints, Sessions, and Security.
"""

from __future__ import annotations
import os
from flask import Flask


def create_app(test_config: dict | None = None) -> Flask:
    """
    Creates and configures an instance of the FinPay Flask application.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FINPAY_SECRET_KEY", "finpay-insecure-dev-key-change-in-prod"),
        JSON_SORT_KEYS=False,
    )

    if test_config:
        app.config.update(test_config)

    # Register Blueprints
    from finpay.api.routes import api_bp
    app.register_blueprint(api_bp)

    return app
