import json
import logging
from pathlib import Path
import uuid

import numpy as np
import pandas as pd

from .data import load, join_weather, treat_temperature, quality
from .dataset import (
    FEATURE_COLUMNS,
    SIMULATED_COLUMNS,
    TABLE_NAME,
    build_dataset,
    training_summary,
)
from .dump import load_dump
from .simulation import occupation, thermal
from .export import digest, records, write_dataset

MODEL_VERSION = "demo-rc-v1"


def prepare(config, dump_path=None):
    output = Path(config["output"])
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").unlink(missing_ok=True)
    if dump_path is None:
        _, building, electric, weather, absent = load(config)
        sources = {
            key: {"path": config[key], "sha256": digest(config[key])}
            for key in ("metadata", "electricity", "weather")
        }
    else:
        _, building, electric, weather, absent = load_dump(config, dump_path)
        sources = {"dump": {"path": str(dump_path), "sha256": digest(dump_path)}}
    b = config["building"]
    frame = electric[[b]].reset_index().rename(columns={b: "consumption_kwh"})
    site_weather = weather.loc[weather.site_id.eq(building.site_id)].drop(
        columns="site_id"
    )
    frame = join_weather(frame, site_weather)
    treated, imputed = treat_temperature(
        frame.airTemperature, config["weather_mode"], config["max_gap"]
    )
    frame["outdoor_temperature_processed_c"] = treated
    frame["temperature_imputed"] = imputed
    missing = int(frame.airTemperature.isna().sum())
    report = {
        "building_id": b,
        "site_id": building.site_id,
        "timezone": building.timezone,
        "time_convention": "source local naive; no UTC conversion",
        "expected_hours": len(electric),
        "electricity_rows_absent": absent,
        "electricity": quality(electric[b]),
        "weather_rows_absent": int((~frame.weather_row_present).sum()),
        "weather_rows_with_missing_temperature": int(
            (frame.weather_row_present & frame.airTemperature.isna()).sum()
        ),
        "missing_temperature_total": missing,
        "notebook_expected_missing_temperature": 4,
        "difference_from_notebook": missing - 4,
        "imputed_temperatures": int(imputed.sum()),
        "unresolved_temperatures": int(treated.isna().sum()),
        "missing_by_weather_column": {
            k: int(frame[k].isna().sum())
            for k in site_weather.columns
            if k != "timestamp"
        },
        "weather_mode": config["weather_mode"],
    }
    index = pd.DatetimeIndex(frame.timestamp)
    report["dst_ambiguous_or_nonexistent_labels"] = int(
        index.tz_localize(building.timezone, ambiguous="NaT", nonexistent="NaT")
        .isna()
        .sum()
    )
    report["sources"] = sources
    if missing != 4:
        logging.warning("Températures absentes: %d; notebook: 4", missing)
    logging.info(
        "Qualité: %d heures, %d lignes météo absentes, %d températures absentes, %d imputées",
        len(frame),
        report["weather_rows_absent"],
        missing,
        imputed.sum(),
    )
    counts, _ = occupation(index, config)
    indoor, hvac = thermal(treated.to_numpy(), counts, config["thermal"])
    identity = {
        "config": {k: v for k, v in config.items() if k != "output"},
        "sources": sources,
        "model_version": MODEL_VERSION,
        "implementation_sha256": {
            p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))
        },
        "libraries": {"numpy": np.__version__, "pandas": pd.__version__},
    }
    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(identity, sort_keys=True)))
    building_info = records(
        pd.DataFrame(
            [
                {
                    "building_id": b,
                    "site_id": building.site_id,
                    "timezone": building.timezone,
                    "primary_space_usage": building.primaryspaceusage,
                    "area_sqm": float(building["sqm"])
                    if pd.notna(building.get("sqm"))
                    else None,
                }
            ]
        )
    )[0]
    history = pd.DataFrame(
        {
            "building_id": b,
            "timestamp_local": frame.timestamp,
            "consumption_kwh": frame.consumption_kwh,
            "weather_row_present": frame.weather_row_present,
            "outdoor_temperature_original_c": frame.airTemperature,
            "outdoor_temperature_processed_c": treated,
            "temperature_imputed": imputed,
            "electricity_row_present": electric.attrs["row_present"],
        }
    )
    states = pd.DataFrame(
        {
            "timestamp_local": frame.timestamp,
            "occupants": counts,
            "indoor_temperature_c": indoor,
            "hvac_thermal_energy_kwh": hvac,
        }
    )
    dataset = build_dataset(history, states, building, config)
    report["training"] = training_summary(dataset)
    metadata = {
        "schema_version": 2,
        "table": TABLE_NAME,
        "row_count": len(dataset),
        "building": building_info,
        "simulation": {
            "run_id": run_id,
            "model_version": MODEL_VERSION,
            "capacity": config["capacity"],
            "parameters": identity,
            "context_columns": SIMULATED_COLUMNS,
        },
        "target_column": "consumption_kwh",
        "feature_columns": FEATURE_COLUMNS,
        "forecast_horizon_hours": 1,
        "row_convention": "target hour s; measured features use labels s-1 or earlier",
        "time_convention": report["time_convention"],
        "availability_assumption": "previous nominal interval available before target; verify meter timing before live use",
        "weather_feature_mode": "causal",
        "anomaly_labels": {
            "null": "unlabeled",
            "0": "confirmed normal",
            "1": "confirmed anomaly",
        },
        "training": config.get(
            "training",
            {
                "validation_start": "2017-01-01 00:00:00",
                "test_start": "2017-07-01 00:00:00",
            },
        ),
        "sources": sources,
    }
    write_dataset(output, dataset, metadata, report)
    logging.info(
        "Table %s: %d lignes, %d prêtes pour entraînement; exports %s",
        TABLE_NAME,
        len(dataset),
        report["training"]["ready_rows"],
        output,
    )
    return report


def diagnose(config):
    import os

    cache = Path(config["output"]) / ".matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache.resolve()))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    meta, building, electric, weather, absent = load(config, diagnostic=True)
    output = Path(config["output"]) / "diagnostics"
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for b in electric:
        q = quality(electric[b])
        monthly = q.pop("monthly")
        pd.DataFrame(monthly).to_csv(output / f"{b}_monthly.csv", index=False)
        rows.append({"building_id": b, **q})
    pd.DataFrame(rows).sort_values(
        ["eligible_full_period", "missing", "zeros", "building_id"],
        ascending=[False, True, True, True],
    ).to_csv(output / "office_comparison.csv", index=False)
    candidates = [
        "Hog_office_Miriam",
        "Hog_office_Napoleon",
        "Hog_office_Myles",
        "Robin_office_Antonina",
        "Panther_office_Karla",
    ]
    fig, axes = plt.subplots(5, 1, figsize=(14, 13), sharex=True)
    comparisons = []
    for ax, b in zip(axes, candidates):
        if b not in electric:
            ax.set_title(f"{b}: absent")
            continue
        s = electric[b]
        site = meta.loc[meta.building_id.eq(b), "site_id"].iloc[0]
        joined = join_weather(
            s.reset_index(),
            weather.loc[weather.site_id.eq(site)].drop(columns="site_id"),
        )
        comparisons.append(
            {
                "building_id": b,
                "hours_without_weather": int((~joined.weather_row_present).sum()),
                "missing_temperature": int(joined.airTemperature.isna().sum()),
                "temperature_correlation": joined[b].corr(joined.airTemperature),
                "weekend_vs_weekday": s[s.index.dayofweek >= 5].mean()
                / s[s.index.dayofweek < 5].mean(),
            }
        )
        s.resample("D").mean().plot(ax=ax, label="Moyenne quotidienne")
        s.resample("MS").median().plot(ax=ax, label="Médiane mensuelle")
        ax.set_title(b + (" — RETENU" if b == config["building"] else ""))
        ax.set_ylabel("kWh")
        ax.legend()
    fig.tight_layout()
    fig.savefig(output / "candidate_comparison.png")
    plt.close(fig)
    pd.DataFrame(comparisons).to_csv(output / "candidate_weather.csv", index=False)
    s = electric[config["building"]]
    profile = (
        pd.DataFrame(
            {"value": s, "hour": s.index.hour, "weekend": s.index.dayofweek >= 5}
        )
        .groupby(["hour", "weekend"])
        .value.mean()
        .unstack()
    )
    profile.plot(ylabel="kWh", title="Profil moyen horaire")
    plt.savefig(output / "hourly_profile.png")
    plt.close()
    w = join_weather(
        s.reset_index(),
        weather.loc[weather.site_id.eq(building.site_id)].drop(columns="site_id"),
    )
    plt.scatter(w.airTemperature, w[config["building"]], s=2, alpha=0.2)
    plt.xlabel("Température extérieure °C")
    plt.ylabel("kWh")
    plt.savefig(output / "temperature_consumption.png")
    plt.close()
    logging.info(
        "Diagnostic: %d bureaux; choix explicite %s conservé",
        len(rows),
        config["building"],
    )
