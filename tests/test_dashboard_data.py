import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from dashboard.data import load_dashboard_data
from twin.dataset import TABLE_NAME
from twin.export import digest, write_dataset
from tests.fixtures import dataset_fixture


class DashboardDataTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.output = self.root / "outputs"
        self.config_path = self.root / "config.json"
        self.config_path.write_text(json.dumps({"output": "outputs"}))
        write_dataset(self.output, *dataset_fixture())

    def tearDown(self):
        self.directory.cleanup()

    def test_loads_single_table_with_context_and_training_features(self):
        data = load_dashboard_data(self.config_path)
        self.assertEqual(len(data.measurements), 200)
        self.assertEqual(
            data.measurements.iloc[0].timestamp_local, pd.Timestamp("2016-01-01")
        )
        self.assertEqual(data.measurements.iloc[0].occupants, 5)
        self.assertEqual(data.metadata["table"], TABLE_NAME)
        self.assertEqual(data.measurements.is_training_ready.sum(), 32)

    def test_rejects_modified_export_or_metadata(self):
        for filename in [
            f"{TABLE_NAME}.json",
            "dataset_metadata.json",
            f"{TABLE_NAME}.sqlite",
        ]:
            with self.subTest(filename=filename):
                write_dataset(self.output, *dataset_fixture())
                with (self.output / filename).open("ab") as target:
                    target.write(b" ")
                with self.assertRaisesRegex(ValueError, "absent ou modifié"):
                    load_dashboard_data(self.config_path)

    def test_rejects_inconsistent_metadata_even_with_updated_manifest(self):
        path = self.output / "dataset_metadata.json"
        metadata = json.loads(path.read_text())
        metadata["building"]["building_id"] = "unknown"
        path.write_text(json.dumps(metadata))
        manifest_path = self.output / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"][path.name] = digest(path)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "incohérents"):
            load_dashboard_data(self.config_path)

    def test_rejects_legacy_four_table_manifest_with_rebuild_hint(self):
        (self.output / "manifest.json").write_text(
            json.dumps({"buildings": "old-format"})
        )
        with self.assertRaisesRegex(ValueError, "relancer prepare"):
            load_dashboard_data(self.config_path)


if __name__ == "__main__":
    unittest.main()
