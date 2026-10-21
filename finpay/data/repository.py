"""
In-Memory Transaction Repository.
Provides a central data store for querying, filtering, and updating active transactions.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional
import pandas as pd

from finpay.data.ingestion import TransactionIngestionEngine
from finpay.ml.classifier import TransactionClassifier

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = DATA_DIR / "sample_transactions.csv"


class TransactionRepository:
    """Manages active transactions in memory."""

    def __init__(self, initial_csv_path: Optional[Path | str] = DEFAULT_CSV):
        self.ingestion_engine = TransactionIngestionEngine()
        self.classifier = TransactionClassifier()
        self._df: pd.DataFrame = pd.DataFrame()
        self.load_from_csv(initial_csv_path)

    def load_from_csv(self, csv_path_or_buffer) -> int:
        """Loads and enriches transaction data with ML predictions."""
        raw_df = self.ingestion_engine.load_csv(csv_path_or_buffer)
        
        # If category is missing or uncategorized, classify with ML
        if "category" not in raw_df.columns or (raw_df["category"] == "Uncategorized").any():
            enriched_df = self.classifier.classify_dataframe(raw_df)
            enriched_df["category"] = enriched_df["predicted_category"]
        else:
            # Enrich with model validation confidence
            enriched_df = self.classifier.classify_dataframe(raw_df)

        self._df = enriched_df
        return len(self._df)

    def get_all(self) -> pd.DataFrame:
        """Returns a copy of the active DataFrame."""
        return self._df.copy()

    def query(
        self,
        category: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Filters active transactions by multiple criteria."""
        df = self._df.copy()

        if df.empty:
            return df

        if start_date:
            df = df[df["date"] >= pd.to_datetime(start_date)]

        if end_date:
            df = df[df["date"] <= pd.to_datetime(end_date)]

        if category and category.lower() != "all":
            df = df[df["category"].str.lower() == category.lower()]

        if search:
            search_term = search.lower()
            df = df[
                df["description"].str.lower().str.contains(search_term, na=False)
                | df["cleaned_description"].str.lower().str.contains(search_term, na=False)
            ]

        if limit is not None and limit > 0:
            df = df.head(limit)

        return df

    def compute_insights(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        category: Optional[str] = None,
    ) -> dict:
        """Computes aggregated spending insights for the given filter parameters."""
        filtered_df = self.query(
            category=category, start_date=start_date, end_date=end_date
        )

        if filtered_df.empty:
            return {
                "summary": {
                    "total_transactions": 0,
                    "total_spent": 0.0,
                    "total_income": 0.0,
                    "net_savings": 0.0,
                    "date_range": {"start": None, "end": None},
                },
                "category_breakdown": [],
                "monthly_trend": [],
                "top_merchants": [],
            }

        # Separate expenses and income
        expenses = filtered_df[~filtered_df["is_income"]]
        income = filtered_df[filtered_df["is_income"]]

        total_spent = float(expenses["amount"].sum())
        total_income = float(income["amount"].sum())
        net_savings = total_income - total_spent

        # Category breakdown
        category_breakdown = []
        if not expenses.empty:
            grouped = expenses.groupby("category")["amount"].agg(["sum", "count", "mean"]).reset_index()
            for _, row in grouped.iterrows():
                spent = float(row["sum"])
                pct = round((spent / total_spent * 100) if total_spent > 0 else 0, 2)
                category_breakdown.append(
                    {
                        "category": row["category"],
                        "total_spent": round(spent, 2),
                        "percentage": pct,
                        "transaction_count": int(row["count"]),
                        "average_amount": round(float(row["mean"]), 2),
                    }
                )
            category_breakdown.sort(key=lambda x: x["total_spent"], reverse=True)

        # Monthly trend
        monthly_trend = []
        months = filtered_df["year_month"].unique()
        for ym in sorted(months):
            m_exp = float(filtered_df[(filtered_df["year_month"] == ym) & (~filtered_df["is_income"])]["amount"].sum())
            m_inc = float(filtered_df[(filtered_df["year_month"] == ym) & (filtered_df["is_income"])]["amount"].sum())
            monthly_trend.append(
                {
                    "month": ym,
                    "spent": round(m_exp, 2),
                    "income": round(m_inc, 2),
                    "savings": round(m_inc - m_exp, 2),
                }
            )

        # Top 5 merchants
        top_merchants = []
        if not expenses.empty:
            m_grouped = expenses.groupby("cleaned_description")["amount"].agg(["sum", "count"]).reset_index()
            m_grouped = m_grouped.sort_values(by="sum", ascending=False).head(5)
            for _, row in m_grouped.iterrows():
                top_merchants.append(
                    {
                        "merchant": row["cleaned_description"].title(),
                        "total_spent": round(float(row["sum"]), 2),
                        "count": int(row["count"]),
                    }
                )

        return {
            "summary": {
                "total_transactions": int(len(filtered_df)),
                "total_spent": round(total_spent, 2),
                "total_income": round(total_income, 2),
                "net_savings": round(net_savings, 2),
                "date_range": {
                    "start": filtered_df["date"].min().strftime("%Y-%m-%d"),
                    "end": filtered_df["date"].max().strftime("%Y-%m-%d"),
                },
            },
            "category_breakdown": category_breakdown,
            "monthly_trend": monthly_trend,
            "top_merchants": top_merchants,
        }


# Global repository instance
repo = TransactionRepository()
