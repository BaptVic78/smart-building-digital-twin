"""Lire un export PostgreSQL COPY sans exécuter son SQL ni importer auth/storage."""

import re

import pandas as pd

from .data import require, timestamps


COPY_HEADER = re.compile(
    r'^COPY "public"\."(buildings|historical_measurements)" \((.*?)\) FROM stdin;$'
)
ESCAPES = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\"}


def copy_value(raw):
    if raw == r"\N":
        return None

    def replace(match):
        value = match.group()[1:]
        if value[0] in "01234567":
            return chr(int(value, 8))
        if value.startswith("x") and len(value) > 1:
            return chr(int(value[1:], 16))
        return ESCAPES.get(value, value)

    return re.sub(r"\\(?:[0-7]{1,3}|x[0-9a-fA-F]{1,2}|.)", replace, raw)


def read_dump(path):
    tables = {}
    active = None
    with open(path, encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            line = line.rstrip("\n").rstrip("\r")
            if line == r"\.":
                active = None
            elif active:
                columns, rows = tables[active]
                values = line.split("\t")
                if len(values) != len(columns):
                    raise ValueError(f"Export COPY invalide à la ligne {line_number}")
                rows.append([copy_value(value) for value in values])
            else:
                match = COPY_HEADER.fullmatch(line)
                if match:
                    active = match[1]
                    if active in tables:
                        raise ValueError(f"Bloc COPY dupliqué: {active}")
                    columns = re.findall(r'"([^"]+)"', match[2])
                    if not columns or len(columns) != len(set(columns)):
                        raise ValueError(f"Colonnes COPY invalides: {active}")
                    tables[active] = (columns, [])
    if active:
        raise ValueError("Bloc COPY incomplet en fin de fichier")
    if set(tables) != {"buildings", "historical_measurements"}:
        raise ValueError(
            "Le dump doit contenir buildings et historical_measurements au format COPY"
        )
    return {
        name: pd.DataFrame(rows, columns=columns)
        for name, (columns, rows) in tables.items()
    }


def load_dump(config, path):
    tables = read_dump(path)
    meta = tables["buildings"].rename(
        columns={"primary_space_usage": "primaryspaceusage", "area_sqm": "sqm"}
    )
    require(meta, ["building_id", "site_id", "timezone", "primaryspaceusage"])
    if meta.building_id.isna().any() or meta.building_id.duplicated().any():
        raise ValueError("Identifiants bâtiment absents ou dupliqués dans le dump")
    chosen = meta.loc[meta.building_id.eq(config["building"])]
    if len(chosen) != 1 or chosen.iloc[0].primaryspaceusage != "Office":
        raise ValueError("Bâtiment Office configuré introuvable dans le dump")
    building = chosen.iloc[0]
    if pd.isna(building.site_id) or pd.isna(building.timezone):
        raise ValueError("Site/fuseau manquant dans le dump")
    history = tables["historical_measurements"]
    require(
        history,
        [
            "building_id",
            "timestamp_local",
            "consumption_kwh",
            "outdoor_temperature_original_c",
            "electricity_row_present",
            "weather_row_present",
        ],
    )
    history = timestamps(
        history.rename(columns={"timestamp_local": "timestamp"}),
        ("building_id", "timestamp"),
    )
    history = history.loc[history.building_id.eq(config["building"])].copy()
    for column in ("electricity_row_present", "weather_row_present"):
        if not history[column].isin(["t", "f"]).all():
            raise ValueError(f"Drapeau invalide dans le dump: {column}")
        history[column] = history[column].eq("t")
    for column in ("consumption_kwh", "outdoor_temperature_original_c"):
        history[column] = pd.to_numeric(history[column], errors="raise")
    if history.loc[~history.electricity_row_present, "consumption_kwh"].notna().any():
        raise ValueError(
            "Consommation présente malgré une ligne électrique déclarée absente"
        )
    if (
        history.loc[~history.weather_row_present, "outdoor_temperature_original_c"]
        .notna()
        .any()
    ):
        raise ValueError("Température présente malgré une ligne météo déclarée absente")

    grid = pd.date_range(config["start"], config["end"], freq="h")
    if len(grid) == 0 or not grid.equals(grid.floor("h")):
        raise ValueError("Période vide ou bornes non horaires")
    electricity = history.loc[
        history.electricity_row_present, ["timestamp", "consumption_kwh"]
    ]
    electricity = electricity.set_index("timestamp").rename(
        columns={"consumption_kwh": config["building"]}
    )
    present = grid.isin(electricity.index)
    electricity = electricity.reindex(grid).rename_axis("timestamp")
    electricity.attrs["row_present"] = present
    weather = history.loc[
        history.weather_row_present, ["timestamp", "outdoor_temperature_original_c"]
    ]
    weather = weather.rename(
        columns={"outdoor_temperature_original_c": "airTemperature"}
    )
    weather["site_id"] = building.site_id
    return meta, building, electricity, weather, int((~present).sum())
