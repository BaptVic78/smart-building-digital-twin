import hashlib
import json
import logging
import os
import re
import sqlite3
import tempfile
import urllib.error
from pathlib import Path
import urllib.request
import urllib.parse

import numpy as np
import pandas as pd

from .dataset import (
    COLUMN_TYPES,
    FEATURE_COLUMNS,
    SCHEMA_VERSION,
    TABLE_NAME,
    validate_dataset,
)

TABLE_KEYS = {TABLE_NAME: "building_id,timestamp_local"}
EXPORT_FILES = [
    f"{TABLE_NAME}.{extension}" for extension in ("csv", "json", "sqlite", "sql")
] + ["dataset_metadata.json", "quality_report.json"]


def supabase_headers(secret, method):
    """Les nouvelles clés secrètes utilisent apikey; les JWT legacy ajoutent Bearer."""
    headers = {
        "apikey": secret,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal"
        if method == "POST"
        else "count=exact",
        "Range": "0-0",
    }
    if not secret.startswith("sb_secret_"):
        headers["Authorization"] = "Bearer " + secret
    return headers


def http_error_details(error):
    """Expose le statut et un code structuré, jamais le message distant."""
    code = None
    try:
        payload = json.loads(error.read(8192))
        candidate = payload.get("code") if isinstance(payload, dict) else None
        if isinstance(candidate, str) and re.fullmatch(
            r"(?:PGRST[0-9]{3}|[0-9A-Z]{5})", candidate
        ):
            code = candidate
    except (ValueError, OSError):
        pass
    hint = {
        401: "Vérifier la clé et son appartenance au projet Supabase.",
        403: "Vérifier les permissions et la clé serveur utilisée.",
        404: "Vérifier que le SQL a été exécuté et que la table est accessible.",
    }.get(error.code, "Vérifier le schéma et les journaux API Supabase.")
    return f"HTTP {error.code}" + (f"; code {code}" if code else "") + f". {hint}"


def records(frame):
    # PostgreSQL float8 accepte les infinis, JSON standard non: représentation textuelle explicite.
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(v) for v in value]
        if pd.isna(value):
            return None
        if isinstance(value, (float, np.floating)) and np.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        return value

    return [{k: clean(v) for k, v in row.items()} for row in frame.to_dict("records")]


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def database_schema(dialect="postgres"):
    if dialect not in ("postgres", "sqlite"):
        raise ValueError("Dialecte SQL inconnu")
    table = f"public.{TABLE_NAME}" if dialect == "postgres" else TABLE_NAME
    types = {
        "text": "text",
        "timestamp": "timestamp without time zone",
        "real": "double precision",
        "integer": "integer",
        "boolean": "boolean",
    }
    if dialect == "sqlite":
        types.update(timestamp="text", real="real", boolean="integer")
    nullable = {"consumption_kwh", "outdoor_temperature_processed_c", "anomaly_label"}
    nullable.update(
        name for name in COLUMN_TYPES if "_lag_" in name or "_mean_" in name
    )
    fields = [
        f" {name} {types[kind]}" + ("" if name in nullable else " not null")
        for name, kind in COLUMN_TYPES.items()
    ]
    fields += [
        " primary key (building_id, timestamp_local)",
        " check (occupants >= 0)",
        " check (hour between 0 and 23)",
        " check (dayofweek between 0 and 6)",
        " check (month between 1 and 12)",
        " check (training_split in ('train', 'validation', 'test'))",
        " check (anomaly_label in (0, 1))",
    ]
    if dialect == "postgres":
        fields.append(" check (timestamp_local = date_trunc('hour', timestamp_local))")
    else:
        fields += [
            f" check ({name} in (0, 1))"
            for name, kind in COLUMN_TYPES.items()
            if kind == "boolean"
        ]
    schema = f"create table if not exists {table} (\n" + ",\n".join(fields) + "\n);\n"
    schema += (
        f"create index if not exists training_time_idx on {table}(timestamp_local);\n"
    )
    schema += f"create index if not exists training_split_idx on {table}(training_split, is_training_ready);\n"
    if dialect == "postgres":
        schema += f"alter table {table} enable row level security;\n"
    return schema


def sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def write_dataset(output, frame, metadata, quality_report):
    """Publier un ensemble cohérent; le manifeste est écrit en dernier."""
    validate_dataset(frame)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").unlink(missing_ok=True)
    rows = records(frame)
    columns = list(COLUMN_TYPES)
    with tempfile.TemporaryDirectory(prefix=".dataset-", dir=output) as directory:
        staged = Path(directory)
        frame.to_csv(staged / f"{TABLE_NAME}.csv", index=False)
        (staged / f"{TABLE_NAME}.json").write_text(
            json.dumps(rows, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        for name, payload in [
            ("dataset_metadata.json", metadata),
            ("quality_report.json", quality_report),
        ]:
            (staged / name).write_text(
                json.dumps(
                    payload, ensure_ascii=False, indent=2, allow_nan=False, default=str
                )
                + "\n",
                encoding="utf-8",
            )
        with sqlite3.connect(staged / f"{TABLE_NAME}.sqlite") as connection:
            connection.executescript(database_schema("sqlite"))
            connection.executemany(
                f"insert into {TABLE_NAME} ({', '.join(columns)}) values ({', '.join('?' for _ in columns)})",
                [
                    tuple(
                        float(row[column])
                        if COLUMN_TYPES[column] == "real"
                        and row[column] in ("Infinity", "-Infinity")
                        else row[column]
                        for column in columns
                    )
                    for row in rows
                ],
            )
        with (staged / f"{TABLE_NAME}.sql").open("w", encoding="utf-8") as target:
            target.write(
                "-- Généré par python -m twin prepare. Une seule table, aucun DROP.\n"
            )
            target.write("begin;\nset local standard_conforming_strings = on;\n")
            target.write(database_schema())
            update_columns = [
                name
                for name in columns
                if name not in ("building_id", "timestamp_local")
            ]
            for start in range(0, len(rows), 500):
                target.write(
                    f"insert into public.{TABLE_NAME} ({', '.join(columns)}) values\n"
                )
                target.write(
                    ",\n".join(
                        "("
                        + ", ".join(sql_literal(row[column]) for column in columns)
                        + ")"
                        for row in rows[start : start + 500]
                    )
                )
                target.write(
                    "\non conflict (building_id, timestamp_local) do update set\n"
                )
                target.write(
                    ",\n".join(f" {name} = excluded.{name}" for name in update_columns)
                    + ";\n"
                )
            target.write("commit;\n")
        for name in EXPORT_FILES:
            (staged / name).replace(output / name)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE_NAME,
        "files": {name: digest(output / name) for name in EXPORT_FILES},
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def read_dataset(output):
    output = Path(output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("table") != TABLE_NAME
        or set(manifest.get("files", {})) != set(EXPORT_FILES)
    ):
        raise ValueError("Ancien format ou exports incomplets: relancer prepare")
    for name in EXPORT_FILES:
        if manifest["files"][name] != digest(output / name):
            raise ValueError(f"Export {name} absent ou modifié: relancer prepare")
    rows = json.loads((output / f"{TABLE_NAME}.json").read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("La table finale doit contenir une liste de lignes")
    frame = pd.DataFrame(rows)
    validate_dataset(frame)
    frame["timestamp_local"] = pd.to_datetime(frame.timestamp_local, errors="raise")
    for name, kind in COLUMN_TYPES.items():
        if kind in ("real", "integer"):
            frame[name] = pd.to_numeric(frame[name], errors="raise")
    metadata = json.loads(
        (output / "dataset_metadata.json").read_text(encoding="utf-8")
    )
    report = json.loads((output / "quality_report.json").read_text(encoding="utf-8"))
    if (
        not isinstance(metadata, dict)
        or metadata.get("table") != TABLE_NAME
        or metadata.get("row_count") != len(frame)
        or metadata.get("feature_columns") != FEATURE_COLUMNS
        or metadata.get("target_column") != "consumption_kwh"
        or not isinstance(metadata.get("building"), dict)
        or set(frame.building_id) != {metadata.get("building", {}).get("building_id")}
        or not isinstance(report, dict)
        or "electricity" not in report
    ):
        raise ValueError("Métadonnées ou rapport qualité incohérents")
    return frame, metadata, report


def load_tables(output, batch_size=500, dry_run=False, request=None):
    if batch_size < 1:
        raise ValueError("Taille de lot invalide")
    frame, _, _ = read_dataset(output)
    payloads = {TABLE_NAME: records(frame)}
    if dry_run:
        for name, rows in payloads.items():
            logging.info(
                "Dry-run %s: %d lignes, %d lots",
                name,
                len(rows),
                (len(rows) + batch_size - 1) // batch_size,
            )
        return
    url, secret = (
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY"),
    )
    if request is None:
        parsed = urllib.parse.urlsplit(url or "")
        if (
            not secret
            or parsed.scheme != "https"
            or not parsed.netloc
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("SUPABASE_URL HTTPS et SUPABASE_SERVICE_ROLE_KEY requis")

        def request(method, table, query, rows=None):
            headers = supabase_headers(secret, method)
            req = urllib.request.Request(
                url.rstrip("/")
                + "/rest/v1/"
                + table
                + "?"
                + urllib.parse.urlencode(query),
                data=json.dumps(rows, allow_nan=False).encode()
                if rows is not None
                else None,
                headers=headers,
                method=method,
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    return response.headers.get("Content-Range", "")
            except urllib.error.HTTPError as error:
                raise RuntimeError(
                    f"Échec Supabase {method} {table}: {http_error_details(error)}"
                ) from None
            except urllib.error.URLError:
                raise RuntimeError(
                    f"Échec réseau Supabase {method} {table}: vérifier connexion, DNS et URL du projet."
                ) from None
            except TimeoutError:
                raise RuntimeError(
                    f"Délai dépassé Supabase {method} {table}; relancer le chargement."
                ) from None

    for name, rows in payloads.items():
        for start in range(0, len(rows), batch_size):
            request(
                "POST",
                name,
                {"on_conflict": TABLE_KEYS[name]},
                rows[start : start + batch_size],
            )
        # Vérifier le périmètre exact importé (la table peut contenir d'autres exécutions).
        scopes = {}
        scope_key = "building_id"
        for row in rows:
            scopes[row[scope_key]] = scopes.get(row[scope_key], 0) + 1
        for scope, expected in scopes.items():
            query = {"select": "*", scope_key: f"eq.{scope}"}
            if "timestamp_local" in TABLE_KEYS[name]:
                times = [r["timestamp_local"] for r in rows if r[scope_key] == scope]
                query["and"] = (
                    f"(timestamp_local.gte.{min(times)},timestamp_local.lte.{max(times)})"
                )
            content_range = request("HEAD", name, query)
            actual = int(content_range.rsplit("/", 1)[-1])
            if actual != expected:
                raise RuntimeError(
                    f"Comptage {name}: attendu {expected}, reçu {actual}"
                )
        logging.info("%s: %d lignes vérifiées", name, len(rows))
