from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from tests.fixtures import input_frames
from twin.dump import copy_value, load_dump, read_dump
from twin.export import read_dataset
from twin.pipeline import prepare


def copy_block(table, frame):
    def encode(value):
        if pd.isna(value):
            return r"\N"
        if isinstance(value, (bool, np.bool_)):
            return "t" if value else "f"
        return (
            str(value).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
        )

    header = ", ".join(f'"{column}"' for column in frame.columns)
    lines = [
        "\t".join(encode(value) for value in row)
        for row in frame.itertuples(index=False, name=None)
    ]
    return (
        f'COPY "public"."{table}" ({header}) FROM stdin;\n'
        + "\n".join(lines)
        + "\n\\.\n"
    )


def dump_text(history, building):
    buildings = pd.DataFrame([building]).rename(
        columns={"primaryspaceusage": "primary_space_usage"}
    )
    return (
        'COPY "auth"."users" ("email") FROM stdin;\nprivate@example.invalid\n\\.\n'
        + copy_block("buildings", buildings)
        + copy_block("historical_measurements", history)
        + "SELECT this_sql_must_never_be_executed();\n"
    )


class DumpTests(unittest.TestCase):
    def test_copy_escaping_and_null_are_distinct(self):
        self.assertIsNone(copy_value(r"\N"))
        self.assertEqual(copy_value(r"\\N"), r"\N")
        self.assertEqual(copy_value(r"a\tb\nc\\d"), "a\tb\nc\\d")
        self.assertEqual(copy_value(r"\101\x42"), "AB")

    def test_sql_dump_and_raw_csv_produce_identical_final_rows(self):
        history, _, building, config = input_frames()
        history.loc[30, "outdoor_temperature_original_c"] = np.nan
        history.loc[31, "weather_row_present"] = False
        history.loc[31, "outdoor_temperature_original_c"] = np.nan
        history.loc[40, "electricity_row_present"] = False
        history.loc[40, "consumption_kwh"] = np.nan
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "donnees.sql"
            path.write_text(dump_text(history, building), encoding="utf-8")
            tables = read_dump(path)
            self.assertEqual(set(tables), {"buildings", "historical_measurements"})
            prepared = {**config, "output": str(root / "from-dump")}
            prepare(prepared, path)
            from_dump, metadata, report = read_dataset(root / "from-dump")
            self.assertEqual(report["electricity_rows_absent"], 1)
            self.assertEqual(report["weather_rows_absent"], 1)
            self.assertEqual(metadata["weather_feature_mode"], "causal")

            pd.DataFrame([building]).to_csv(root / "metadata.csv", index=False)
            history.loc[
                history.electricity_row_present, ["timestamp_local", "consumption_kwh"]
            ].rename(
                columns={
                    "timestamp_local": "timestamp",
                    "consumption_kwh": config["building"],
                }
            ).to_csv(root / "electricity.csv", index=False)
            weather = history.loc[
                history.weather_row_present,
                ["timestamp_local", "outdoor_temperature_original_c"],
            ].rename(
                columns={
                    "timestamp_local": "timestamp",
                    "outdoor_temperature_original_c": "airTemperature",
                }
            )
            weather["site_id"] = building.site_id
            weather.to_csv(root / "weather.csv", index=False)
            raw_config = {
                **config,
                "output": str(root / "from-csv"),
                **{
                    name: str(root / f"{name}.csv")
                    for name in ("metadata", "electricity", "weather")
                },
            }
            prepare(raw_config)
            from_csv, _, _ = read_dataset(root / "from-csv")
            pd.testing.assert_frame_equal(from_csv, from_dump)

    def test_rejects_incomplete_blocks_duplicates_and_bad_flags(self):
        history, _, building, config = input_frames(3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dump.sql"
            for content in [
                dump_text(history, building).replace("\\.\nSELECT", "SELECT"),
                dump_text(history, building)
                + copy_block("buildings", pd.DataFrame([building])),
            ]:
                path.write_text(content)
                with self.assertRaises(ValueError):
                    read_dump(path)
            history["weather_row_present"] = "not-a-boolean"
            path.write_text(dump_text(history, building))
            with self.assertRaisesRegex(ValueError, "Drapeau invalide"):
                load_dump(config, path)


if __name__ == "__main__":
    unittest.main()
