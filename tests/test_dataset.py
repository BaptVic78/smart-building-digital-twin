from pathlib import Path
import sqlite3
import tempfile
import unittest

import numpy as np
import pandas as pd

from tests.fixtures import dataset_fixture, input_frames
from twin.dataset import FEATURE_COLUMNS, TABLE_NAME, build_dataset, validate_dataset
from twin.export import database_schema, read_dataset, write_dataset


class DatasetTests(unittest.TestCase):
    def test_lags_and_full_past_windows_exclude_target(self):
        frame, _, _ = dataset_fixture()
        row = frame.iloc[168]
        self.assertEqual(row.consumption_kwh, 178.0)
        self.assertEqual(row.consumption_lag_1h_kwh, 177.0)
        self.assertEqual(row.consumption_lag_24h_kwh, 154.0)
        self.assertEqual(row.consumption_lag_168h_kwh, 10.0)
        self.assertEqual(row.consumption_mean_24h_kwh, 165.5)
        self.assertEqual(row.consumption_mean_168h_kwh, 93.5)
        self.assertFalse(frame.is_training_ready.iloc[:168].any())
        self.assertTrue(frame.is_training_ready.iloc[168:].all())
        self.assertTrue(frame.anomaly_label.isna().all())

    def test_modifying_target_and_future_cannot_change_its_inputs(self):
        history, states, building, config = input_frames()
        history.loc[179, "outdoor_temperature_original_c"] = np.nan
        reference = build_dataset(history, states, building, config)
        history.loc[180:, "consumption_kwh"] = 9999.0
        history.loc[180:, "outdoor_temperature_original_c"] = 999.0
        # Le contexte rétrospectif n'entre pas dans les variables prédictives.
        history.loc[179:, "outdoor_temperature_processed_c"] = 999.0
        altered = build_dataset(history, states, building, config)
        pd.testing.assert_frame_equal(
            reference[FEATURE_COLUMNS].iloc[:181], altered[FEATURE_COLUMNS].iloc[:181]
        )
        self.assertEqual(altered.iloc[180].outdoor_temperature_lag_1h_c, 10.0)

    def test_dst_values_are_kept_but_excluded_from_feature_windows(self):
        history, states, building, config = input_frames(400, "2016-03-06 00:00:00")
        frame = build_dataset(history, states, building, config)
        self.assertEqual(frame.dst_time_issue.sum(), 1)
        self.assertEqual(
            frame.iloc[170].consumption_kwh, history.iloc[170].consumption_kwh
        )
        self.assertFalse(frame.iloc[170].is_training_ready)
        self.assertTrue(pd.isna(frame.iloc[171].consumption_lag_1h_kwh))
        self.assertFalse(frame.is_training_ready.iloc[170:339].any())
        self.assertTrue(frame.iloc[339].is_training_ready)

    def test_invalid_energy_kept_without_becoming_a_training_input(self):
        history, states, building, config = input_frames()
        history.loc[175, "consumption_kwh"] = -2.0
        history.loc[176, "consumption_kwh"] = 0.0
        frame = build_dataset(history, states, building, config)
        self.assertEqual(frame.iloc[175].consumption_kwh, -2.0)
        self.assertTrue(pd.isna(frame.iloc[176].consumption_lag_1h_kwh))
        self.assertEqual(frame.iloc[177].consumption_lag_1h_kwh, 0.0)
        self.assertFalse(frame.iloc[175].is_training_ready)

    def test_chronological_boundaries_and_duplicate_protection(self):
        history, states, building, config = input_frames(4, "2016-12-31 22:00:00")
        frame = build_dataset(history, states, building, config)
        self.assertEqual(
            frame.training_split.tolist(),
            ["train", "train", "validation", "validation"],
        )
        history, states, building, config = input_frames(4, "2017-06-30 22:00:00")
        frame = build_dataset(history, states, building, config)
        self.assertEqual(
            frame.training_split.tolist(), ["validation", "validation", "test", "test"]
        )
        with self.assertRaisesRegex(ValueError, "Doublons"):
            build_dataset(
                pd.concat([history, history.iloc[:1]]), states, building, config
            )
        with self.assertRaisesRegex(ValueError, "mêmes heures"):
            build_dataset(history, states.iloc[:-1], building, config)

    def test_sqlite_has_one_table_and_matches_json_nulls_and_counts(self):
        frame, metadata, report = dataset_fixture()
        with tempfile.TemporaryDirectory() as directory:
            write_dataset(directory, frame, metadata, report)
            restored, actual_metadata, _ = read_dataset(directory)
            self.assertEqual(actual_metadata, metadata)
            self.assertEqual(len(restored), len(frame))
            with sqlite3.connect(
                Path(directory) / f"{TABLE_NAME}.sqlite"
            ) as connection:
                tables = connection.execute(
                    "select name from sqlite_master where type='table'"
                ).fetchall()
                self.assertEqual(tables, [(TABLE_NAME,)])
                self.assertEqual(
                    connection.execute(
                        f"select count(*), count(anomaly_label), sum(is_training_ready) from {TABLE_NAME}"
                    ).fetchone(),
                    (200, 0, 32),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(f"update {TABLE_NAME} set anomaly_label=2")
            sql = (Path(directory) / f"{TABLE_NAME}.sql").read_text()
            self.assertNotIn("drop table", sql.lower())
            self.assertIn("on conflict (building_id, timestamp_local)", sql)

    def test_schema_file_stays_in_sync_with_populated_export(self):
        schema = (Path(__file__).resolve().parents[1] / "sql/schema.sql").read_text()
        self.assertEqual(
            schema,
            "-- Table finale unique. Aucun DROP des anciennes tables.\nbegin;\n"
            + database_schema()
            + "commit;\n",
        )

    def test_rejects_invalid_ready_flag_and_labels(self):
        frame, _, _ = dataset_fixture()
        frame.loc[0, "is_training_ready"] = True
        with self.assertRaisesRegex(ValueError, "disponibilité"):
            validate_dataset(frame)
        frame.loc[0, "is_training_ready"] = False
        frame.loc[0, "anomaly_label"] = 2
        with self.assertRaisesRegex(ValueError, "annotations"):
            validate_dataset(frame)


if __name__ == "__main__":
    unittest.main()
