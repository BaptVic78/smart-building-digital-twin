"""Lecture de la table unique préparée localement, sans accès réseau."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from twin.export import read_dataset


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DashboardData:
    measurements: pd.DataFrame
    metadata: dict
    quality_report: dict
    exports_updated_at: datetime


def load_dashboard_data(config_path=ROOT / "config.json"):
    config_path = Path(config_path).resolve()
    with config_path.open(encoding="utf-8") as source:
        config = json.load(source)
    output = Path(config["output"])
    if not output.is_absolute():
        output = config_path.parent / output
    frame, metadata, report = read_dataset(output)
    return DashboardData(
        measurements=frame,
        metadata=metadata,
        quality_report=report,
        exports_updated_at=datetime.fromtimestamp(
            (output / "manifest.json").stat().st_mtime
        ).astimezone(),
    )
