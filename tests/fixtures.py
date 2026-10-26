import json
from pathlib import Path

import numpy as np
import pandas as pd

from twin.dataset import FEATURE_COLUMNS, SCHEMA_VERSION, TABLE_NAME, build_dataset, training_summary


CONFIG = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text())


def input_frames(periods=200, start="2016-01-01 00:00:00"):
    times = pd.date_range(start, periods=periods, freq="h")
    config = {**CONFIG, "start": str(times[0]), "end": str(times[-1])}
    building = pd.Series(
        {
            "building_id": CONFIG["building"],
            "site_id": "Hog",
            "timezone": "US/Central",
            "primaryspaceusage": "Office",
        }
    )
    history = pd.DataFrame(
        {
            "building_id": CONFIG["building"],
            "timestamp_local": times,
            "consumption_kwh": np.arange(periods, dtype=float) + 10,
            "outdoor_temperature_original_c": np.full(periods, 10.0),
            "outdoor_temperature_processed_c": np.full(periods, 10.0),
            "temperature_imputed": False,
            "weather_row_present": True,
            "electricity_row_present": True,
        }
    )
    states = pd.DataFrame(
        {
            "timestamp_local": times,
            "occupants": 5,
            "indoor_temperature_c": 21.0,
            "hvac_thermal_energy_kwh": 0.0,
        }
    )
    return history, states, building, config


def dataset_fixture(periods=200, start="2016-01-01 00:00:00"):
    frame = build_dataset(*input_frames(periods, start))
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE_NAME,
        "row_count": len(frame),
        "building": {
            "building_id": CONFIG["building"],
            "site_id": "Hog",
            "timezone": "US/Central",
        },
        "simulation": {
            "capacity": 100,
            "model_version": "demo-rc-v1",
            "parameters": {},
        },
        "target_column": "consumption_kwh",
        "feature_columns": FEATURE_COLUMNS,
    }
    report = {
        "electricity": {"missing": 0, "monthly": []},
        "training": training_summary(frame),
    }
    return frame, metadata, report
