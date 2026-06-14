# -*- coding: utf-8 -*-
"""Predictive AI core for the NSR-Aegis Panama Canal MVP.

This module trains a multi-output Random Forest model on local Panama Canal
climate, oceanographic, draft, and structural telemetry data. It is intentionally
framework-agnostic so Streamlit, FastAPI, notebooks, or batch jobs can consume it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "panama_climate_data.csv"


FEATURE_COLUMNS = [
    "year",
    "month",
    "precipitation_mm",
    "avg_temp_c",
    "wind_speed_knots",
    "evaporation_rate",
    "sst_anomaly_c",
    "visibility_nm",
    "ocean_salinity_psu",
    "fwa_draft_penalty_cm",
    "balboa_tide_anomaly_m",
]

TARGET_COLUMNS = [
    "lake_level_m",
    "max_allowable_draft_m",
    "structural_stress_mpa",
]

REQUIRED_COLUMNS = FEATURE_COLUMNS + TARGET_COLUMNS


class PanamaPredictiveEngine:
    """Random Forest predictive engine for Panama Canal transit conditions."""

    def __init__(
        self,
        data_path: str | Path = DEFAULT_DATA_PATH,
        *,
        n_estimators: int = 500,
        random_state: int = 42,
        min_samples_leaf: int = 2,
    ) -> None:
        self.data_path = self._resolve_data_path(data_path)
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.min_samples_leaf = min_samples_leaf

        self.data = self._load_dataset()
        self.monthly_feature_medians = self._build_monthly_feature_medians()
        self.global_feature_medians = self.data[FEATURE_COLUMNS].median(numeric_only=True)

        self.model = self._build_model()
        self.validation_metrics = self._train_and_evaluate()

    def _resolve_data_path(self, data_path: str | Path) -> Path:
        """Resolve relative dataset paths against the project root."""
        path = Path(data_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path

        if path.exists():
            return path

        # Backward-compatible fallback for local extracts saved in the repo root.
        fallback_path = PROJECT_ROOT / "panama_climate_data.csv"
        if fallback_path.exists():
            return fallback_path

        raise FileNotFoundError(
            f"Panama climate dataset not found. Expected '{path}' "
            f"or fallback '{fallback_path}'."
        )

    def _load_dataset(self) -> pd.DataFrame:
        """Load and validate the Panama Canal dataset."""
        data = pd.read_csv(self.data_path)
        missing_columns = [column for column in REQUIRED_COLUMNS if column not in data.columns]
        if missing_columns:
            raise ValueError(
                "Dataset schema mismatch. Missing columns: "
                + ", ".join(missing_columns)
            )

        model_data = data[REQUIRED_COLUMNS].copy()
        for column in REQUIRED_COLUMNS:
            model_data[column] = pd.to_numeric(model_data[column], errors="coerce")

        model_data = model_data.dropna(subset=TARGET_COLUMNS)
        if model_data.empty:
            raise ValueError("Dataset has no valid target rows after numeric coercion.")

        return model_data.sort_values(["year", "month"]).reset_index(drop=True)

    def _build_monthly_feature_medians(self) -> pd.DataFrame:
        """Create month-specific defaults for omitted inference features."""
        return self.data.groupby("month")[FEATURE_COLUMNS].median(numeric_only=True)

    def _build_model(self) -> Pipeline:
        """Build the preprocessing and Random Forest regression pipeline."""
        regressor = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            min_samples_leaf=self.min_samples_leaf,
            n_jobs=-1,
        )

        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("regressor", regressor),
            ]
        )

    def _train_and_evaluate(self) -> Dict[str, Dict[str, float]]:
        """Evaluate on the latest holdout slice, then retrain on all data."""
        x = self.data[FEATURE_COLUMNS]
        y = self.data[TARGET_COLUMNS]

        holdout_size = max(12, int(len(self.data) * 0.2))
        holdout_size = min(holdout_size, max(1, len(self.data) - 12))

        if len(self.data) > holdout_size + 12:
            x_train = x.iloc[:-holdout_size]
            y_train = y.iloc[:-holdout_size]
            x_test = x.iloc[-holdout_size:]
            y_test = y.iloc[-holdout_size:]

            self.model.fit(x_train, y_train)
            predictions = self.model.predict(x_test)
            metrics = self._calculate_metrics(y_test, predictions)
        else:
            metrics = {
                target: {"mae": float("nan"), "r2": float("nan")}
                for target in TARGET_COLUMNS
            }

        # Production model uses all available historical rows.
        self.model.fit(x, y)
        return metrics

    def _calculate_metrics(
        self,
        y_true: pd.DataFrame,
        predictions: np.ndarray,
    ) -> Dict[str, Dict[str, float]]:
        """Calculate validation metrics per target variable."""
        metrics: Dict[str, Dict[str, float]] = {}
        for index, target in enumerate(TARGET_COLUMNS):
            metrics[target] = {
                "mae": float(mean_absolute_error(y_true[target], predictions[:, index])),
                "r2": float(r2_score(y_true[target], predictions[:, index])),
            }
        return metrics

    def _feature_defaults_for_month(self, month: int) -> Dict[str, float]:
        """Return robust feature defaults using monthly medians first."""
        if month in self.monthly_feature_medians.index:
            defaults = self.monthly_feature_medians.loc[month].to_dict()
        else:
            defaults = self.global_feature_medians.to_dict()

        for feature in FEATURE_COLUMNS:
            if pd.isna(defaults.get(feature)):
                defaults[feature] = float(self.global_feature_medians[feature])

        return {feature: float(defaults[feature]) for feature in FEATURE_COLUMNS}

    def _build_inference_frame(
        self,
        *,
        month: int,
        precipitation_mm: float,
        avg_temp_c: float,
        year: Optional[int] = None,
        wind_speed_knots: Optional[float] = None,
        evaporation_rate: Optional[float] = None,
        sst_anomaly_c: Optional[float] = None,
        visibility_nm: Optional[float] = None,
        ocean_salinity_psu: Optional[float] = None,
        fwa_draft_penalty_cm: Optional[float] = None,
        balboa_tide_anomaly_m: Optional[float] = None,
    ) -> pd.DataFrame:
        """Build a single-row inference frame in the training feature order."""
        if not 1 <= int(month) <= 12:
            raise ValueError("month must be an integer between 1 and 12.")

        defaults = self._feature_defaults_for_month(int(month))
        values = {
            **defaults,
            "year": float(year if year is not None else self.data["year"].max()),
            "month": float(month),
            "precipitation_mm": float(precipitation_mm),
            "avg_temp_c": float(avg_temp_c),
            "wind_speed_knots": wind_speed_knots,
            "evaporation_rate": evaporation_rate,
            "sst_anomaly_c": sst_anomaly_c,
            "visibility_nm": visibility_nm,
            "ocean_salinity_psu": ocean_salinity_psu,
            "fwa_draft_penalty_cm": fwa_draft_penalty_cm,
            "balboa_tide_anomaly_m": balboa_tide_anomaly_m,
        }

        clean_values = {
            feature: defaults[feature] if values[feature] is None else float(values[feature])
            for feature in FEATURE_COLUMNS
        }
        return pd.DataFrame([clean_values], columns=FEATURE_COLUMNS)

    def predict_panama_conditions(
        self,
        *,
        month: int,
        precipitation_mm: float,
        avg_temp_c: float,
        year: Optional[int] = None,
        wind_speed_knots: Optional[float] = None,
        evaporation_rate: Optional[float] = None,
        sst_anomaly_c: Optional[float] = None,
        visibility_nm: Optional[float] = None,
        ocean_salinity_psu: Optional[float] = None,
        fwa_draft_penalty_cm: Optional[float] = None,
        balboa_tide_anomaly_m: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Predict Panama Canal lake level, allowable draft, and hull stress."""
        features = self._build_inference_frame(
            year=year,
            month=month,
            precipitation_mm=precipitation_mm,
            avg_temp_c=avg_temp_c,
            wind_speed_knots=wind_speed_knots,
            evaporation_rate=evaporation_rate,
            sst_anomaly_c=sst_anomaly_c,
            visibility_nm=visibility_nm,
            ocean_salinity_psu=ocean_salinity_psu,
            fwa_draft_penalty_cm=fwa_draft_penalty_cm,
            balboa_tide_anomaly_m=balboa_tide_anomaly_m,
        )

        prediction = self.model.predict(features)[0]
        result = {
            target: round(float(value), 3)
            for target, value in zip(TARGET_COLUMNS, prediction)
        }

        result["transit_recommendation"] = self._recommend_transit_action(result)
        result["features_used"] = {
            feature: round(float(features.iloc[0][feature]), 3)
            for feature in FEATURE_COLUMNS
        }
        return result

    def _recommend_transit_action(self, prediction: Mapping[str, float]) -> str:
        """Convert model outputs into a concise operational recommendation."""
        lake_level = float(prediction["lake_level_m"])
        max_draft = float(prediction["max_allowable_draft_m"])
        stress = float(prediction["structural_stress_mpa"])

        if lake_level < 24.8 or max_draft < 13.2:
            return "DIVERT_OR_AUCTION_SLOT"
        if stress > 38.0:
            return "TRANSIT_WITH_LOCK_STRESS_MONITORING"
        if lake_level < 25.4 or max_draft < 13.8:
            return "REDUCE_DRAFT_AND_WAIT_WINDOW"
        return "PANAMA_TRANSIT_ACCEPTABLE"

    def feature_importance(self, top_n: int = 8) -> pd.DataFrame:
        """Return the most influential features from the trained forest."""
        regressor = self.model.named_steps["regressor"]
        importance = pd.DataFrame(
            {
                "feature": FEATURE_COLUMNS,
                "importance": regressor.feature_importances_,
            }
        )
        return importance.sort_values("importance", ascending=False).head(top_n)


@lru_cache(maxsize=4)
def get_panama_engine(data_path: str = str(DEFAULT_DATA_PATH)) -> PanamaPredictiveEngine:
    """Return a cached engine instance for Streamlit or API consumers."""
    return PanamaPredictiveEngine(data_path=data_path)


def predict_panama_conditions(
    month: int,
    precipitation_mm: float,
    avg_temp_c: float,
    **optional_features: Any,
) -> Dict[str, Any]:
    """Module-level inference helper for Streamlit callbacks."""
    engine = get_panama_engine()
    return engine.predict_panama_conditions(
        month=month,
        precipitation_mm=precipitation_mm,
        avg_temp_c=avg_temp_c,
        **optional_features,
    )


if __name__ == "__main__":
    engine = PanamaPredictiveEngine()
    sample = engine.predict_panama_conditions(
        year=2026,
        month=4,
        precipitation_mm=45.0,
        avg_temp_c=29.2,
        sst_anomaly_c=1.1,
    )
    print(sample)
