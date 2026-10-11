import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from twin.export import TABLE_KEYS, digest


ROOT = Path(__file__).resolve().parents[1]
TABLE_COLUMNS = {
    "buildings": {"building_id", "site_id", "timezone", "primary_space_usage"},
    "historical_measurements": {
        "building_id",
        "timestamp_local",
        "consumption_kwh",
        "weather_row_present",
        "outdoor_temperature_processed_c",
        "temperature_imputed",
    },
    "simulation_runs": {
        "run_id",
        "building_id",
        "model_version",
        "expected_states",
    },
    "simulated_states": {
        "run_id",
        "timestamp_local",
        "occupants",
        "occupancy_rate",
        "indoor_temperature_c",
        "hvac_thermal_energy_kwh",
    },
}


@dataclass(frozen=True)
class DashboardData:
    buildings: pd.DataFrame
    measurements: pd.DataFrame
    simulation_runs: pd.DataFrame
    states: pd.DataFrame
    quality_report: dict
    exports_updated_at: datetime


def _read_records(path):
    with path.open(encoding="utf-8") as source:
        records = json.load(source)
    if not isinstance(records, list):
        raise ValueError(f"Format d'export invalide: {path.name} doit contenir une liste.")
    return pd.DataFrame.from_records(records)


def _validate_columns(frame, table):
    missing = TABLE_COLUMNS[table] - set(frame.columns)
    if missing:
        raise ValueError(
            f"Export {table}.json incomplet; colonnes absentes: {sorted(missing)}."
        )


def load_dashboard_data(config_path=ROOT / "config.json"):
    config_path = Path(config_path).resolve()
    with config_path.open(encoding="utf-8") as source:
        config = json.load(source)

    output = Path(config["output"])
    if not output.is_absolute():
        output = config_path.parent / output
    manifest_path = output / "manifest.json"
    with manifest_path.open(encoding="utf-8") as source:
        manifest = json.load(source)

    for table in TABLE_KEYS:
        export_path = output / f"{table}.json"
        if manifest.get(table) != digest(export_path):
            raise ValueError(
                f"Export {table}.json absent ou modifié; relancer `python -m twin prepare`."
            )

    tables = {}
    for table in TABLE_KEYS:
        tables[table] = _read_records(output / f"{table}.json")
        _validate_columns(tables[table], table)

    with (output / "quality_report.json").open(encoding="utf-8") as source:
        quality_report = json.load(source)
    if not isinstance(quality_report, dict) or "electricity" not in quality_report:
        raise ValueError("Le rapport qualité est absent ou incomplet.")

    for table in ("historical_measurements", "simulated_states"):
        tables[table]["timestamp_local"] = pd.to_datetime(
            tables[table]["timestamp_local"], errors="raise"
        )

    known_runs = set(tables["simulation_runs"]["run_id"])
    if not set(tables["simulated_states"]["run_id"]).issubset(known_runs):
        raise ValueError("Les états simulés référencent une exécution inconnue.")

    return DashboardData(
        buildings=tables["buildings"],
        measurements=tables["historical_measurements"],
        simulation_runs=tables["simulation_runs"],
        states=tables["simulated_states"],
        quality_report=quality_report,
        exports_updated_at=datetime.fromtimestamp(manifest_path.stat().st_mtime).astimezone(),
    )
