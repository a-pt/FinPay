"""
Multi-Tenant In-Memory Transaction Repository.
Provides user-scoped data stores for querying, filtering, and updating active transactions.
Ensures strict data isolation between analysts while allowing admin oversight.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, List
import pandas as pd

from finpay.data.ingestion import TransactionIngestionEngine
from finpay.ml.classifier import TransactionClassifier

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = DATA_DIR / "sample_transactions.csv"
DEFAULT_USER_ID = "user_analyst_1"
UPLOAD_DIR = DATA_DIR / "user_uploads"


class TransactionRepository:
    """Manages multi-tenant transaction datasets with disk persistence."""

    def __init__(self, initial_csv_path: Optional[Path | str] = DEFAULT_CSV):
        self.ingestion_engine = TransactionIngestionEngine()
        self.classifier = TransactionClassifier()
        # Per-user isolated DataFrames: user_id -> pd.DataFrame
        self._user_dfs: Dict[str, pd.DataFrame] = {}
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        # Pre-seed default analyst with sample portfolio data
        if initial_csv_path and Path(initial_csv_path).exists():
            self.load_from_csv(DEFAULT_USER_ID, initial_csv_path)

    def load_from_csv(self, user_id: str, csv_path_or_buffer) -> int:
        """
        Loads, validates, enriches with ML, and permanently saves to disk for a specific user.
        """
        raw_df = self.ingestion_engine.load_csv(csv_path_or_buffer)

        # Run AI classification on raw transaction descriptions
        enriched_df = self.classifier.classify_dataframe(raw_df)
        enriched_df["category"] = enriched_df["predicted_category"]

        # Re-evaluate income status based on model prediction
        enriched_df["is_income"] = enriched_df["category"].str.lower() == "income"

        # Tag with user ownership
        enriched_df["user_id"] = user_id

        # Replace in-memory cache
        self._user_dfs[user_id] = enriched_df

        # Persist to disk so it survives server restarts
        try:
            persisted_path = UPLOAD_DIR / f"{user_id}.csv"
            enriched_df.to_csv(persisted_path, index=False)
        except Exception:
            pass

        return len(enriched_df)

    def get_user_df(self, user_id: Optional[str] = None) -> pd.DataFrame:
        """Retrieves DataFrame for a given user, checking memory and persisted disk storage."""
        target_user = user_id or DEFAULT_USER_ID
        if target_user == "all":
            # Admin cross-tenant aggregation
            all_dfs = list(self._user_dfs.values())
            # Also check disk for any users not currently in memory
            for path in UPLOAD_DIR.glob("*.csv"):
                uid = path.stem
                if uid not in self._user_dfs:
                    try:
                        df = pd.read_csv(path)
                        df["date"] = pd.to_datetime(df["date"])
                        all_dfs.append(df)
                    except Exception:
                        pass
            if not all_dfs:
                return pd.DataFrame()
            return pd.concat(all_dfs, ignore_index=True)

        # Check in-memory
        if target_user in self._user_dfs:
            return self._user_dfs[target_user].copy()

        # Check persisted file on disk
        persisted_file = UPLOAD_DIR / f"{target_user}.csv"
        if persisted_file.exists():
            try:
                df = pd.read_csv(persisted_file)
                df["date"] = pd.to_datetime(df["date"])
                self._user_dfs[target_user] = df
                return df.copy()
            except Exception:
                pass

        return pd.DataFrame()

    def get_all(self, user_id: Optional[str] = None) -> pd.DataFrame:
        """Returns a copy of the active DataFrame for the given user."""
        return self.get_user_df(user_id)

    def get_user_stats(self, user_id: str) -> dict:
        """Returns summary metadata for an analyst (count, total spent, date range)."""
        df = self.get_user_df(user_id)
        if df.empty:
            return {"transaction_count": 0, "total_spent": 0.0, "has_data": False}

        expenses = df[~df["is_income"]]
        return {
            "transaction_count": len(df),
            "total_spent": round(float(expenses["amount"].sum()), 2),
            "has_data": True,
            "first_date": df["date"].min().strftime("%Y-%m-%d"),
            "last_date": df["date"].max().strftime("%Y-%m-%d"),
        }

    def query(
        self,
        user_id: Optional[str] = None,
        category: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Filters active user-scoped transactions by multiple criteria."""
        df = self.get_user_df(user_id)

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
        user_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        category: Optional[str] = None,
    ) -> dict:
        """Computes aggregated spending insights for the given user and filter parameters."""
        filtered_df = self.query(
            user_id=user_id, category=category, start_date=start_date, end_date=end_date
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
