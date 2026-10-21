"""
Transaction Data Ingestion and Preprocessing Module.
Handles schema validation, dirty formatting, text normalization, and date parsing.
"""

from __future__ import annotations
import re
from typing import BinaryIO, TextIO, Union
import pandas as pd


class IngestionError(Exception):
    """Custom exception raised when transaction data ingestion fails."""
    pass


class TransactionIngestionEngine:
    """
    Robust ingestion engine for loading and preprocessing fintech transaction data.
    """

    REQUIRED_COLUMNS = ["date", "description", "amount"]
    OPTIONAL_COLUMNS = ["category", "account_id", "transaction_id"]

    def __init__(self, drop_duplicates: bool = True):
        self.drop_duplicates = drop_duplicates

    @staticmethod
    def clean_description(raw_desc: str) -> str:
        """
        Normalizes a raw bank transaction description for AI classification and analytics.
        
        Example:
            'SQ *STARBUCKS STORE #1042 SAN FRANCISCO CA' -> 'starbucks store'
            'TST* UBER EATS HELP.UBER.COM' -> 'uber eats'
        """
        if not isinstance(raw_desc, str) or not raw_desc.strip():
            return "unknown transaction"

        text = raw_desc.strip()

        # Remove common payment gateway/POS prefixes
        text = re.sub(
            r"^(SQ\s*\*|TST\s*\*|PAYPAL\s*\*|POS\s+DEBIT\s+|ACH\s+DEBIT\s+|CHECKCARD\s+)",
            "",
            text,
            flags=re.IGNORECASE,
        )

        # Remove store/order numbers (e.g., #1042, *2K18A2, STORE 0482)
        text = re.sub(r"#[A-Za-z0-9\-]+", "", text)
        text = re.sub(r"\*[A-Za-z0-9\-]+", "", text)
        text = re.sub(r"\bSTORE\s+\d+\b", "", text, flags=re.IGNORECASE)

        # Remove website/support domain extensions (.com, .org, .net, etc.) without deleting the brand name
        text = re.sub(r"(\.com|\.org|\.net|\.io)\b", "", text, flags=re.IGNORECASE)

        # Remove US state abbreviations at the end of string (e.g. 'CA', 'NY')
        text = re.sub(r"\b[A-Z]{2}\b$", "", text)

        # Replace non-alphanumeric chars (keep spaces and apostrophes)
        text = re.sub(r"[^a-zA-Z0-9\s']", " ", text)

        # Collapse multiple spaces and lowercase
        text = re.sub(r"\s+", " ", text).strip().lower()

        return text if text else "unknown transaction"

    @staticmethod
    def clean_amount(val: Union[str, int, float]) -> float:
        """
        Normalizes transaction amounts: handles currency signs ('$1,250.00'), commas, negative signs.
        """
        if pd.isna(val):
            raise ValueError("Amount cannot be null")
        
        if isinstance(val, (int, float)):
            return float(abs(val))

        s = str(val).strip()
        # Remove currency symbols and commas
        s = re.sub(r"[\$,€£\s]", "", s)
        try:
            amt = float(s)
            return abs(amt)
        except ValueError as err:
            raise ValueError(f"Could not parse amount '{val}' into a valid number") from err

    def load_csv(self, source: Union[str, TextIO, BinaryIO]) -> pd.DataFrame:
        """
        Loads, validates, and preprocesses transaction data from a file path or buffer.

        Returns:
            pd.DataFrame with standardized columns:
                ['date', 'description', 'cleaned_description', 'amount', 'category', 'year_month', 'day_of_week']
        """
        try:
            df = pd.read_csv(source)
        except Exception as e:
            raise IngestionError(f"Failed to read CSV source: {e}") from e

        # Normalize column names: lowercase and strip whitespace
        df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]

        # Verify required columns exist
        missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            raise IngestionError(
                f"CSV is missing required columns: {missing_cols}. Found: {list(df.columns)}"
            )

        # Drop rows where critical fields are entirely null
        df = df.dropna(subset=self.REQUIRED_COLUMNS).copy()

        # Parse and validate dates
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).copy()

        # Clean and parse amounts
        try:
            df["amount"] = df["amount"].apply(self.clean_amount)
        except Exception as e:
            raise IngestionError(f"Error processing transaction amounts: {e}") from e

        # Ensure description is string and clean it
        df["description"] = df["description"].astype(str).str.strip()
        df["cleaned_description"] = df["description"].apply(self.clean_description)

        # Handle category column if present, else default to 'Uncategorized'
        if "category" in df.columns:
            df["category"] = df["category"].fillna("Uncategorized").astype(str).str.strip()
        else:
            df["category"] = "Uncategorized"

        # Deduplication
        if self.drop_duplicates:
            df = df.drop_duplicates(subset=["date", "description", "amount"]).copy()

        # Analytical enrichments
        df["year_month"] = df["date"].dt.strftime("%Y-%m")
        df["day_of_week"] = df["date"].dt.day_name()
        df["is_income"] = df["category"].str.lower() == "income"

        # Sort chronologically
        df = df.sort_values(by="date", ascending=True).reset_index(drop=True)

        return df

    def get_summary(self, df: pd.DataFrame) -> dict:
        """
        Calculates aggregate statistics useful for dashboard overview cards.
        """
        if df.empty:
            return {
                "total_transactions": 0,
                "total_spent": 0.0,
                "total_income": 0.0,
                "net_savings": 0.0,
                "date_range": {"start": None, "end": None},
                "category_count": 0,
            }

        expenses = df[~df["is_income"]]
        income = df[df["is_income"]]

        total_spent = float(expenses["amount"].sum())
        total_income = float(income["amount"].sum())

        return {
            "total_transactions": int(len(df)),
            "total_spent": round(total_spent, 2),
            "total_income": round(total_income, 2),
            "net_savings": round(total_income - total_spent, 2),
            "date_range": {
                "start": df["date"].min().strftime("%Y-%m-%d"),
                "end": df["date"].max().strftime("%Y-%m-%d"),
            },
            "category_count": int(df["category"].nunique()),
        }
