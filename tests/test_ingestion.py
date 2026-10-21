import io
from pathlib import Path
import pytest
import pandas as pd
from finpay.data.ingestion import TransactionIngestionEngine, IngestionError

DATA_DIR = Path(__file__).resolve().parent.parent / "finpay" / "data"


@pytest.fixture
def engine():
    return TransactionIngestionEngine()


def test_clean_description(engine):
    # Tests removing prefixes and tags while preserving key tokens
    assert "starbucks" in engine.clean_description("SQ *STARBUCKS STORE #1042 SAN FRANCISCO CA")
    assert "uber eats" in engine.clean_description("TST* UBER EATS HELP.UBER.COM")
    assert "amazon" in engine.clean_description("AMAZON.COM*2K18A2 MARKETPLACE")
    assert engine.clean_description("   ") == "unknown transaction"
    assert engine.clean_description(None) == "unknown transaction"


def test_clean_amount(engine):
    assert engine.clean_amount("$1,250.50") == 1250.50
    assert engine.clean_amount("-45.20") == 45.20
    assert engine.clean_amount(89.0) == 89.0
    with pytest.raises(ValueError):
        engine.clean_amount("invalid_amount")


def test_load_sample_csv(engine):
    sample_file = DATA_DIR / "sample_transactions.csv"
    df = engine.load_csv(sample_file)
    assert not df.empty
    assert "date" in df.columns
    assert "cleaned_description" in df.columns
    assert "amount" in df.columns
    assert "category" in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert pd.api.types.is_float_dtype(df["amount"])


def test_missing_required_column(engine):
    csv_data = "date,amount\n2024-01-01,25.00"
    with pytest.raises(IngestionError, match="missing required columns"):
        engine.load_csv(io.StringIO(csv_data))


def test_deduplication(engine):
    csv_data = """date,description,amount,category
2024-01-01,Starbucks,5.00,Food & Dining
2024-01-01,Starbucks,5.00,Food & Dining
"""
    df = engine.load_csv(io.StringIO(csv_data))
    assert len(df) == 1


def test_summary_calculation(engine):
    csv_data = """date,description,amount,category
2024-01-01,Starbucks,10.00,Food & Dining
2024-01-02,Uber,20.00,Transportation
2024-01-03,Salary,100.00,Income
"""
    df = engine.load_csv(io.StringIO(csv_data))
    summary = engine.get_summary(df)
    assert summary["total_transactions"] == 3
    assert summary["total_spent"] == 30.00
    assert summary["total_income"] == 100.00
    assert summary["net_savings"] == 70.00
