import io
import pytest
from finpay import create_app
from finpay.api.cache import api_cache


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    api_cache.clear()
    with app.test_client() as client:
        yield client


def test_api_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"


def test_api_transactions(client):
    res = client.get("/api/transactions?limit=10")
    assert res.status_code == 200
    data = res.get_json()
    assert "count" in data
    assert "transactions" in data
    assert len(data["transactions"]) <= 10


def test_api_insights_requirement_3(client):
    """Requirement 3: GET request to insights returns categorized spending insights."""
    res = client.get("/api/insights")
    assert res.status_code == 200
    data = res.get_json()

    # Check required structured insights
    assert "summary" in data
    assert "category_breakdown" in data
    assert "monthly_trend" in data
    assert "top_merchants" in data
    assert "ai_model" in data

    # Summary verification
    summary = data["summary"]
    assert summary["total_transactions"] > 0
    assert summary["total_spent"] > 0

    # Category breakdown verification
    breakdown = data["category_breakdown"]
    assert len(breakdown) > 0
    first_cat = breakdown[0]
    assert "category" in first_cat
    assert "total_spent" in first_cat
    assert "percentage" in first_cat


def test_api_insights_filtering(client):
    res = client.get("/api/insights?category=Transportation")
    assert res.status_code == 200
    data = res.get_json()
    breakdown = data["category_breakdown"]
    # Only Transportation should be present
    assert len(breakdown) == 1
    assert breakdown[0]["category"] == "Transportation"


def test_api_predict(client):
    payload = {"description": "Chipotle Mexican Grill"}
    res = client.post("/api/predict", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["category"] == "Food & Dining"
    assert "confidence" in data
    assert data["confidence"] > 0.40


def test_api_caching_and_telemetry_requirement_7(client):
    """Requirement 7: Caching reduces response time and attaches telemetry."""
    api_cache.clear()

    # First request -> Cache MISS
    res1 = client.get("/api/insights")
    assert res1.status_code == 200
    assert res1.headers.get("X-Cache") == "MISS"
    assert "X-Response-Time-Ms" in res1.headers

    # Second request with identical params -> Cache HIT
    res2 = client.get("/api/insights")
    assert res2.status_code == 200
    assert res2.headers.get("X-Cache") == "HIT"
    assert "X-Response-Time-Ms" in res2.headers


def test_api_upload_csv(client):
    csv_content = """date,description,amount
2024-04-01,Test Coffee,4.50
2024-06-30,Test Bus,2.75
"""
    data = {"file": (io.BytesIO(csv_content.encode("utf-8")), "upload_test.csv")}
    res = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    result = res.get_json()
    assert result["total_transactions"] == 2

    # Query insights and verify date range reflects new dataset bounds
    insights_res = client.get("/api/insights")
    assert insights_res.status_code == 200
    insights_data = insights_res.get_json()
    assert insights_data["summary"]["date_range"]["start"] == "2024-04-01"
    assert insights_data["summary"]["date_range"]["end"] == "2024-06-30"
