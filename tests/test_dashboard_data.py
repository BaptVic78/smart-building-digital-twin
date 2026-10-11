import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from dashboard.data import load_dashboard_data
from twin.export import write_tables


class DashboardDataTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.output = self.root / "outputs"
        self.config_path = self.root / "config.json"
        self.config_path.write_text(
            json.dumps({"output": "outputs"}), encoding="utf-8"
        )
        timestamp = pd.Timestamp("2016-01-01 00:00:00")
        tables = {
            "buildings": pd.DataFrame(
                [
                    {
                        "building_id": "building-a",
                        "site_id": "site-a",
                        "timezone": "US/Central",
                        "primary_space_usage": "Office",
                    }
                ]
            ),
            "historical_measurements": pd.DataFrame(
                [
                    {
                        "building_id": "building-a",
                        "timestamp_local": timestamp,
                        "consumption_kwh": 12.0,
                        "weather_row_present": True,
                        "outdoor_temperature_processed_c": 8.0,
                        "temperature_imputed": False,
                    }
                ]
            ),
            "simulation_runs": pd.DataFrame(
                [
                    {
                        "run_id": "run-a",
                        "building_id": "building-a",
                        "model_version": "demo-rc-v1",
                        "expected_states": 1,
                    }
                ]
            ),
            "simulated_states": pd.DataFrame(
                [
                    {
                        "run_id": "run-a",
                        "timestamp_local": timestamp,
                        "occupants": 5,
                        "occupancy_rate": 0.05,
                        "indoor_temperature_c": 21.0,
                        "hvac_thermal_energy_kwh": 0.0,
                    }
                ]
            ),
        }
        write_tables(self.output, tables)
        (self.output / "quality_report.json").write_text(
            json.dumps({"electricity": {"missing": 0, "monthly": []}}),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_loads_verified_exports_and_parses_timestamps(self):
        data = load_dashboard_data(self.config_path)

        self.assertEqual(data.buildings.iloc[0]["building_id"], "building-a")
        self.assertEqual(data.measurements.iloc[0]["consumption_kwh"], 12.0)
        self.assertEqual(data.measurements.iloc[0]["timestamp_local"], pd.Timestamp("2016-01-01"))
        self.assertEqual(data.states.iloc[0]["run_id"], "run-a")
        self.assertIn("electricity", data.quality_report)

    def test_rejects_modified_export(self):
        with (self.output / "buildings.json").open("a", encoding="utf-8") as target:
            target.write(" ")

        with self.assertRaisesRegex(ValueError, "absent ou modifié"):
            load_dashboard_data(self.config_path)

    def test_rejects_states_for_unknown_run(self):
        states_path = self.output / "simulated_states.json"
        states = json.loads(states_path.read_text(encoding="utf-8"))
        states[0]["run_id"] = "unknown"
        states_path.write_text(json.dumps(states), encoding="utf-8")
        from twin.export import digest

        manifest_path = self.output / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["simulated_states"] = digest(states_path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "exécution inconnue"):
            load_dashboard_data(self.config_path)


if __name__ == "__main__":
    unittest.main()
