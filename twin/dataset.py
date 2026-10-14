"""Table horaire unique et variables disponibles avant l'heure cible."""

import numpy as np
import pandas as pd

from .data import treat_temperature


TABLE_NAME = "training_measurements"
SCHEMA_VERSION = 2
COLUMN_TYPES = {
    "building_id": "text",
    "timestamp_local": "timestamp",
    "consumption_kwh": "real",
    "outdoor_temperature_processed_c": "real",
    "occupants": "integer",
    "indoor_temperature_c": "real",
    "hvac_thermal_energy_kwh": "real",
    "temperature_imputed": "boolean",
    "weather_row_present": "boolean",
    "electricity_row_present": "boolean",
    "context_is_simulated": "boolean",
    "hour": "integer",
    "dayofweek": "integer",
    "month": "integer",
    "is_weekend": "boolean",
    "consumption_lag_1h_kwh": "real",
    "consumption_lag_24h_kwh": "real",
    "consumption_lag_168h_kwh": "real",
    "consumption_mean_24h_kwh": "real",
    "consumption_mean_168h_kwh": "real",
    "outdoor_temperature_lag_1h_c": "real",
    "dst_time_issue": "boolean",
    "training_split": "text",
    "is_training_ready": "boolean",
    "anomaly_label": "integer",
}
FEATURE_COLUMNS = [
    "hour",
    "dayofweek",
    "month",
    "is_weekend",
    "consumption_lag_1h_kwh",
    "consumption_lag_24h_kwh",
    "consumption_lag_168h_kwh",
    "consumption_mean_24h_kwh",
    "consumption_mean_168h_kwh",
    "outdoor_temperature_lag_1h_c",
]
SIMULATED_COLUMNS = ["occupants", "indoor_temperature_c", "hvac_thermal_energy_kwh"]


def build_dataset(history, states, building, config):
    """La ligne s porte la cible y(s); les entrées mesurées viennent de s-1 ou avant."""
    keys = ["building_id", "timestamp_local"]
    if history.duplicated(keys).any() or states.timestamp_local.duplicated().any():
        raise ValueError("Doublons dans les mesures ou les états simulés")
    frame = history.merge(
        states, on="timestamp_local", validate="one_to_one", how="outer", indicator=True
    )
    if not frame.pop("_merge").eq("both").all():
        raise ValueError(
            "Les mesures et les états simulés ne couvrent pas les mêmes heures"
        )
    frame = frame.sort_values("timestamp_local").reset_index(drop=True)
    times = pd.DatetimeIndex(frame.timestamp_local)
    expected = pd.date_range(config["start"], config["end"], freq="h")
    if not times.equals(expected) or not frame.building_id.eq(config["building"]).all():
        raise ValueError(
            "La table finale ne correspond pas au bâtiment/périmètre configuré"
        )

    frame["context_is_simulated"] = True
    frame["hour"] = times.hour
    frame["dayofweek"] = times.dayofweek
    frame["month"] = times.month
    frame["is_weekend"] = times.dayofweek >= 5
    frame["dst_time_issue"] = times.tz_localize(
        building.timezone, ambiguous="NaT", nonexistent="NaT"
    ).isna()

    # Conserver le compteur brut; masquer seulement les entrées historiques invalides.
    valid_energy = (
        np.isfinite(frame.consumption_kwh)
        & frame.consumption_kwh.ge(0)
        & frame.electricity_row_present
        & ~frame.dst_time_issue
    )
    past_energy = frame.consumption_kwh.where(valid_energy)
    for hours in (1, 24, 168):
        frame[f"consumption_lag_{hours}h_kwh"] = past_energy.shift(hours)
    for hours in (24, 168):
        frame[f"consumption_mean_{hours}h_kwh"] = (
            past_energy.shift(1).rolling(hours, min_periods=hours).mean()
        )

    # Même si le contexte thermique est rétrospectif, la météo prédictive reste causale.
    causal_temperature, _ = treat_temperature(
        frame.outdoor_temperature_original_c, "causal", config["max_gap"]
    )
    frame["outdoor_temperature_lag_1h_c"] = causal_temperature.where(
        ~frame.dst_time_issue
    ).shift(1)

    training = config.get("training", {})
    validation_start = pd.Timestamp(
        training.get("validation_start", "2017-01-01 00:00:00")
    )
    test_start = pd.Timestamp(training.get("test_start", "2017-07-01 00:00:00"))
    if (
        pd.isna(validation_start)
        or pd.isna(test_start)
        or validation_start.tzinfo is not None
        or test_start.tzinfo is not None
        or validation_start >= test_start
    ):
        raise ValueError("Bornes entraînement/validation/test invalides")
    frame["training_split"] = np.select(
        [times < validation_start, times < test_start],
        ["train", "validation"],
        default="test",
    )
    frame["is_training_ready"] = valid_energy & np.isfinite(frame[FEATURE_COLUMNS]).all(
        axis=1
    )
    # L'absence d'annotation ne signifie pas que le fonctionnement est normal.
    frame["anomaly_label"] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    return frame[list(COLUMN_TYPES)]


def validate_dataset(frame):
    """Contrôles communs avant export, lecture du dashboard et chargement distant."""
    if list(frame.columns) != list(COLUMN_TYPES):
        raise ValueError("Colonnes de la table finale invalides; relancer prepare")
    if frame.empty or frame[["building_id", "timestamp_local"]].isna().any().any():
        raise ValueError("Table finale vide ou clés absentes")
    if frame.duplicated(["building_id", "timestamp_local"]).any():
        raise ValueError("Clés dupliquées dans la table finale")
    times = pd.to_datetime(frame.timestamp_local, errors="raise")
    if times.dt.tz is not None or not times.eq(times.dt.floor("h")).all():
        raise ValueError("Horodatages locaux horaires requis")
    for column, kind in COLUMN_TYPES.items():
        values = frame[column]
        if (
            kind == "boolean"
            and not values.map(lambda v: isinstance(v, (bool, np.bool_))).all()
        ):
            raise ValueError(f"Booléens invalides: {column}")
        if kind in ("real", "integer"):
            numbers = pd.to_numeric(values, errors="raise")
            if kind == "integer" and not numbers.dropna().mod(1).eq(0).all():
                raise ValueError(f"Entiers invalides: {column}")
    if not frame.training_split.isin(["train", "validation", "test"]).all():
        raise ValueError("Partition temporelle invalide")
    if not frame.anomaly_label.dropna().isin([0, 1]).all():
        raise ValueError("Les annotations doivent être NULL, 0 ou 1")
    for column in SIMULATED_COLUMNS:
        if not np.isfinite(pd.to_numeric(frame[column], errors="raise")).all():
            raise ValueError(f"Contexte simulé absent ou non fini: {column}")
    if frame.occupants.lt(0).any():
        raise ValueError("Occupation négative")
    for column, minimum, maximum in [
        ("hour", 0, 23),
        ("dayofweek", 0, 6),
        ("month", 1, 12),
    ]:
        if not frame[column].between(minimum, maximum).all():
            raise ValueError(f"Calendrier invalide: {column}")
    numeric_features = frame[FEATURE_COLUMNS].apply(pd.to_numeric, errors="raise")
    target = pd.to_numeric(frame.consumption_kwh, errors="raise")
    eligible = (
        np.isfinite(numeric_features).all(axis=1)
        & np.isfinite(target)
        & target.ge(0)
        & ~frame.dst_time_issue
        & frame.electricity_row_present
    )
    if not frame.is_training_ready.eq(eligible).all():
        raise ValueError("Indicateur de disponibilité pour entraînement incohérent")


def training_summary(frame):
    return {
        "table": TABLE_NAME,
        "rows": len(frame),
        "columns": len(frame.columns),
        "ready_rows": int(frame.is_training_ready.sum()),
        "unlabeled_rows": int(frame.anomaly_label.isna().sum()),
        "dst_time_issue_rows": int(frame.dst_time_issue.sum()),
        "partitions": {
            name: {
                "rows": int(mask.sum()),
                "ready_rows": int((mask & frame.is_training_ready).sum()),
            }
            for name in ("train", "validation", "test")
            for mask in [frame.training_split.eq(name)]
        },
    }
