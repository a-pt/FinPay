"""
Inference and Hybrid Categorization Engine.
Combines Machine Learning (TF-IDF + Logistic Regression) with a deterministic
rule-based fallback for banking-specific transaction codes.
"""

from __future__ import annotations
from pathlib import Path
import re
from typing import Dict, Any, List, Union
import joblib
import pandas as pd
from sklearn.pipeline import Pipeline

from finpay.data.ingestion import TransactionIngestionEngine
from finpay.ml.train import train_model, DEFAULT_MODEL_PATH


class TransactionClassifier:
    """
    Hybrid Transaction Classifier.
    Employs an ML pipeline for general merchant categorization and an
    expert rule engine for deterministic banking and payroll keywords.
    """

    # Deterministic banking rules (regex pattern -> Category)
    DETERMINISTIC_RULES = [
        (r"\b(payroll|salary|direct\s+dep(osit)?|tax\s+refund|dividend)\b", "Income"),
        (r"\b(atm\s+cash\s+deposit|mobile\s+check\s+deposit)\b", "Income"),
        (r"\b(uber\s+eats|doordash|grubhub|postmates|instacart)\b", "Food & Dining"),
        (r"\b(netflix|spotify|hulu|disney\s*\+|paramount\s*\+|steam\s+games)\b", "Entertainment"),
        (r"\b(uber(\s+trip)?|lyft(\s+ride)?|caltrain|mta\s+subway|bart)\b", "Transportation"),
        (r"\b(pharmacy|prescription|copay|clinic|urgent\s+care)\b", "Healthcare"),
        (r"\b(gas\s*&\s*electric|utility\s+bill|power\s*&\s*light|sewer\s+autopay)\b", "Utilities & Bills"),
    ]

    def __init__(self, model_path: Union[Path, str] = DEFAULT_MODEL_PATH):
        self.model_path = Path(model_path)
        self.model: Pipeline = self._load_or_train()

    def _load_or_train(self) -> Pipeline:
        """Loads serialized model from disk, or triggers training if not present."""
        if not self.model_path.exists():
            pipeline, _ = train_model(model_save_path=self.model_path)
            return pipeline
        return joblib.load(self.model_path)

    def _apply_rules(self, text: str) -> str | None:
        """Applies deterministic regex rules for high-confidence banking patterns."""
        for pattern, category in self.DETERMINISTIC_RULES:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return category
        return None

    def predict_single(self, description: str, confidence_threshold: float = 0.35) -> Dict[str, Any]:
        """
        Classifies a single transaction description.
        
        Returns:
            Dictionary with prediction, confidence, probabilities, and classification method.
        """
        cleaned = TransactionIngestionEngine.clean_description(description)

        # Check deterministic rules first
        rule_match = self._apply_rules(description) or self._apply_rules(cleaned)

        # Predict using ML pipeline
        probabilities = self.model.predict_proba([cleaned])[0]
        classes = self.model.classes_
        top_idx = probabilities.argmax()
        top_category = classes[top_idx]
        top_confidence = float(probabilities[top_idx])

        # If rule matched and ML confidence is moderate, or if rule is authoritative:
        if rule_match and (rule_match == top_category or top_confidence < 0.65):
            return {
                "description": description,
                "cleaned_description": cleaned,
                "category": rule_match,
                "confidence": 1.0,
                "method": "rule_based",
                "top_probabilities": {
                    cls: round(float(prob), 4) for cls, prob in zip(classes, probabilities)
                },
            }

        return {
            "description": description,
            "cleaned_description": cleaned,
            "category": top_category,
            "confidence": round(top_confidence, 4),
            "method": "machine_learning",
            "top_probabilities": {
                cls: round(float(prob), 4) for cls, prob in zip(classes, probabilities)
            },
        }

    def predict_batch(self, descriptions: List[str]) -> List[Dict[str, Any]]:
        """Classifies a list of transaction descriptions."""
        return [self.predict_single(d) for d in descriptions]

    def classify_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Takes an ingested DataFrame and adds 'predicted_category' and 'ml_confidence'.
        """
        enriched_df = df.copy()
        predictions = self.predict_batch(enriched_df["description"].tolist())

        enriched_df["predicted_category"] = [p["category"] for p in predictions]
        enriched_df["ml_confidence"] = [p["confidence"] for p in predictions]
        enriched_df["classification_method"] = [p["method"] for p in predictions]

        return enriched_df
