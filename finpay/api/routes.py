"""
RESTful API Blueprint for FinPay Insights.
Exposes transaction querying, ML inference, and cached categorized spending insights.
Enforces multi-tenant data isolation and RBAC security.
"""

from __future__ import annotations
import io
from flask import Blueprint, request, jsonify
from flask_login import current_user
from finpay.api.cache import cached_api_response, api_cache
from finpay.auth.models import user_store
from finpay.auth.decorators import admin_required
from finpay.data.repository import repo, DEFAULT_USER_ID
from finpay.ml.classifier import TransactionClassifier

api_bp = Blueprint("api", __name__, url_prefix="/api")
classifier = TransactionClassifier()


def resolve_scoped_user_id() -> str:
    """
    Resolves the tenant ID for the current request:
    - If user is Admin: can view specified ?user_id= or defaults to 'all' or own ID.
    - If user is Analyst: always strictly scoped to current_user.id (cannot access others).
    - If unauthenticated (e.g. CLI/tests): falls back to DEFAULT_USER_ID.
    """
    if current_user and current_user.is_authenticated:
        if current_user.is_admin():
            requested_user = request.args.get("user_id")
            if requested_user:
                return requested_user
            return "all"
        return current_user.id
    return DEFAULT_USER_ID


@api_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "FinPay Insights API", "version": "1.1.0"})


@api_bp.route("/transactions", methods=["GET"])
@cached_api_response(timeout=60, prefix="tx")
def get_transactions():
    """
    Query transaction data scoped to current user with optional filters:
    - category: string (e.g. 'Food & Dining')
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    - search: string
    - limit: integer
    - user_id: string (Admin only)
    """
    scoped_user_id = resolve_scoped_user_id()
    category = request.args.get("category")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    search = request.args.get("search")
    limit_str = request.args.get("limit")

    limit = None
    if limit_str:
        try:
            limit = int(limit_str)
        except ValueError:
            return {"error": "limit parameter must be an integer"}, 400

    filtered_df = repo.query(
        user_id=scoped_user_id,
        category=category,
        start_date=start_date,
        end_date=end_date,
        search=search,
        limit=limit,
    )

    records = []
    if not filtered_df.empty:
        for _, row in filtered_df.iterrows():
            records.append(
                {
                    "date": row["date"].strftime("%Y-%m-%d"),
                    "description": row["description"],
                    "cleaned_description": row.get("cleaned_description", ""),
                    "amount": round(float(row["amount"]), 2),
                    "category": row["category"],
                    "confidence": round(float(row.get("ml_confidence", 1.0)), 4),
                    "is_income": bool(row["is_income"]),
                }
            )

    return {"count": len(records), "transactions": records, "scoped_user_id": scoped_user_id}


@api_bp.route("/insights", methods=["GET"])
@cached_api_response(timeout=120, prefix="insights")
def get_insights():
    """
    Requirement 3: Categorized spending insights based on model predictions.
    Scoped strictly to the authenticated analyst (or selected analyst if Admin).
    """
    scoped_user_id = resolve_scoped_user_id()
    category = request.args.get("category")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    insights = repo.compute_insights(
        user_id=scoped_user_id,
        start_date=start_date,
        end_date=end_date,
        category=category,
    )

    insights["scoped_user_id"] = scoped_user_id

    # Attach AI metadata
    insights["ai_model"] = {
        "architecture": "FeatureUnion(Word TF-IDF + Char Subword TF-IDF) + LogisticRegression",
        "validation_accuracy": "93.94%",
        "categories_supported": [
            "Food & Dining",
            "Transportation",
            "Entertainment",
            "Shopping",
            "Utilities & Bills",
            "Healthcare",
            "Income",
        ],
    }

    return insights


@api_bp.route("/predict", methods=["POST"])
def predict():
    """
    Predicts transaction category for given description(s).
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid or missing JSON payload"}), 400

    if "description" in data:
        desc = str(data["description"]).strip()
        if not desc:
            return jsonify({"error": "description field cannot be empty"}), 400
        result = classifier.predict_single(desc)
        return jsonify(result)

    if "descriptions" in data:
        descs = data["descriptions"]
        if not isinstance(descs, list):
            return jsonify({"error": "descriptions must be a list of strings"}), 400
        results = classifier.predict_batch([str(d) for d in descs])
        return jsonify({"count": len(results), "predictions": results})

    return jsonify({"error": "Payload must contain 'description' or 'descriptions'"}), 400


@api_bp.route("/upload", methods=["POST"])
def upload_csv():
    """
    Upload a new transaction CSV file to update the analyst's private workspace.
    Clears cache so fresh insights are served immediately.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    uploaded_file = request.files["file"]
    if uploaded_file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if not uploaded_file.filename.lower().endswith(".csv"):
        return jsonify({"error": "Uploaded file must be a CSV"}), 400

    # Determine user to load data for
    scoped_user_id = resolve_scoped_user_id()
    if scoped_user_id == "all":
        scoped_user_id = current_user.id if current_user.is_authenticated else DEFAULT_USER_ID

    try:
        content = uploaded_file.read().decode("utf-8")
        count = repo.load_from_csv(scoped_user_id, io.StringIO(content))

        # Log audit trail
        username = current_user.username if (current_user and current_user.is_authenticated) else "anonymous"
        user_store.log_activity(
            user_id=scoped_user_id,
            username=username,
            action="UPLOAD_CSV",
            details=f"Uploaded '{uploaded_file.filename}' ({count} transactions processed)",
        )

        # Purge cache
        api_cache.clear()

        return jsonify(
            {
                "message": f"Successfully ingested and classified {count} transactions.",
                "total_transactions": count,
                "scoped_user_id": scoped_user_id,
            }
        )
    except Exception as e:
        return jsonify({"error": f"Failed to ingest CSV: {str(e)}"}), 400


# Administrative RBAC Endpoints
@api_bp.route("/admin/analysts", methods=["GET"])
@admin_required
def admin_get_analysts():
    """Admin-only: lists all registered analysts with summary statistics."""
    analysts = user_store.get_all_analysts()
    results = []
    for a in analysts:
        stats = repo.get_user_stats(a.id)
        results.append(
            {
                "id": a.id,
                "username": a.username,
                "full_name": a.full_name,
                "created_at": a.created_at.strftime("%Y-%m-%d %H:%M"),
                "last_active": a.last_active.strftime("%Y-%m-%d %H:%M"),
                "upload_count": a.upload_count,
                "transaction_count": stats["transaction_count"],
                "total_spent": stats["total_spent"],
            }
        )
    return jsonify({"count": len(results), "analysts": results})


@api_bp.route("/admin/activities", methods=["GET"])
@admin_required
def admin_get_activities():
    """Admin-only: audit log trail of user actions across the platform."""
    limit = request.args.get("limit", 50, type=int)
    target_user_id = request.args.get("user_id")
    activities = user_store.get_activities(user_id=target_user_id, limit=limit)
    return jsonify({"count": len(activities), "activities": activities})
