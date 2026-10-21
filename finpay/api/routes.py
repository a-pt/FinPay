"""
RESTful API Blueprint for FinPay Insights.
Exposes transaction querying, ML inference, and cached categorized spending insights.
"""

from __future__ import annotations
import io
from flask import Blueprint, request, jsonify
from finpay.api.cache import cached_api_response, api_cache
from finpay.data.repository import repo
from finpay.ml.classifier import TransactionClassifier

api_bp = Blueprint("api", __name__, url_prefix="/api")
classifier = TransactionClassifier()


@api_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "FinPay Insights API", "version": "1.0.0"})


@api_bp.route("/transactions", methods=["GET"])
@cached_api_response(timeout=60, prefix="tx")
def get_transactions():
    """
    Query transaction data with optional filters:
    - category: string (e.g. 'Food & Dining')
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    - search: string
    - limit: integer
    """
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
        category=category,
        start_date=start_date,
        end_date=end_date,
        search=search,
        limit=limit,
    )

    records = []
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

    return {"count": len(records), "transactions": records}


@api_bp.route("/insights", methods=["GET"])
@cached_api_response(timeout=120, prefix="insights")
def get_insights():
    """
    Requirement 3: Categorized spending insights based on model predictions.
    Supports query filters:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    - category: string
    """
    category = request.args.get("category")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    insights = repo.compute_insights(
        start_date=start_date, end_date=end_date, category=category
    )

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
    Accepts JSON:
        {"description": "Whole Foods Market #104"}
    or:
        {"descriptions": ["Uber Trip", "Netflix Sub"]}
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
    Upload a new transaction CSV file to update the data repository.
    Clears cache so fresh insights are served immediately.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    uploaded_file = request.files["file"]
    if uploaded_file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if not uploaded_file.filename.lower().endswith(".csv"):
        return jsonify({"error": "Uploaded file must be a CSV"}), 400

    try:
        content = uploaded_file.read().decode("utf-8")
        count = repo.load_from_csv(io.StringIO(content))
        # Purge cache
        api_cache.clear()
        return jsonify(
            {
                "message": f"Successfully ingested and classified {count} transactions.",
                "total_transactions": count,
            }
        )
    except Exception as e:
        return jsonify({"error": f"Failed to ingest CSV: {str(e)}"}), 400
