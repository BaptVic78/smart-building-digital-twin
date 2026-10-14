import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from tests.fixtures import dataset_fixture
from twin.export import write_dataset


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "Streamlit non installé")
class AppTests(unittest.TestCase):
    def test_single_table_dashboard_filter_and_recent_view(self):
        from streamlit.testing.v1 import AppTest

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.json").write_text(json.dumps({"output": "outputs"}))
            write_dataset(root / "outputs", *dataset_fixture())
            app = AppTest.from_string(
                f"from pathlib import Path\nimport app\napp.ROOT = Path({str(root)!r})\napp.main()\n",
                default_timeout=30,
            ).run()
            self.assertFalse(app.exception)
            self.assertIn("Données d’entraînement", [tab.label for tab in app.tabs])
            period = next(
                box for box in app.sidebar.selectbox if box.label == "Période affichée"
            )
            period.select("7 derniers jours").run()
            self.assertFalse(app.exception)
            app.sidebar.radio[0].set_value("Suivi (flux non connecté)").run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.metric), 4)


if __name__ == "__main__":
    unittest.main()
