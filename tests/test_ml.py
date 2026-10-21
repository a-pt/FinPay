from pathlib import Path
import pytest
import pandas as pd
from finpay.ml.train import train_model
from finpay.ml.classifier import TransactionClassifier

DATA_PATH = Path(__file__).resolve().parent.parent / "finpay" / "data" / "training_transactions.csv"
MODEL_PATH = Path(__file__).resolve().parent.parent / "finpay" / "ml" / "model.joblib"


def test_model_validation_accuracy_exceeds_threshold():
    """Requirement 2: Must achieve at least 75% accuracy on validation set."""
    _, metrics = train_model(data_path=DATA_PATH, model_save_path=MODEL_PATH)
    assert metrics["val_accuracy"] >= 0.75, (
        f"Model accuracy {metrics['val_accuracy']:.2%} is below the 75% requirement"
    )


@pytest.fixture
def classifier():
    return TransactionClassifier(model_path=MODEL_PATH)


def test_predict_single_transactions(classifier):
    # Food & Dining
    res_food = classifier.predict_single("SQ *STARBUCKS STORE #1042")
    assert res_food["category"] == "Food & Dining"
    assert res_food["confidence"] > 0.40

    # Entertainment
    res_ent = classifier.predict_single("NETFLIX.COM DIGITAL SUBSCRIPTION")
    assert res_ent["category"] == "Entertainment"
    assert res_ent["confidence"] > 0.40

    # Transportation
    res_trans = classifier.predict_single("UBER TRIP AIRPORT SFO")
    assert res_trans["category"] == "Transportation"
    assert res_trans["confidence"] > 0.40

    # Income
    res_inc = classifier.predict_single("DIRECT DEPOSIT ACME CORP PAYROLL")
    assert res_inc["category"] == "Income"
    assert res_inc["confidence"] > 0.40


def test_predict_batch(classifier):
    descriptions = ["Shell Gas Station", "Spotify USA", "Target Department Store"]
    results = classifier.predict_batch(descriptions)
    assert len(results) == 3
    assert results[0]["category"] == "Transportation"
    assert results[1]["category"] == "Entertainment"
    assert results[2]["category"] == "Shopping"


def test_classify_dataframe(classifier):
    df = pd.DataFrame(
        {
            "description": ["Chipotle Mexican Grill", "Verizon Wireless Bill"],
            "amount": [14.50, 85.00],
        }
    )
    enriched = classifier.classify_dataframe(df)
    assert "predicted_category" in enriched.columns
    assert "ml_confidence" in enriched.columns
    assert enriched["predicted_category"].tolist() == ["Food & Dining", "Utilities & Bills"]
