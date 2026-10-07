"""Tests de la couverture stricte utilisée dans le notebook, sans charger les CSV."""
import ast
import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

NOTEBOOK = Path(__file__).resolve().parents[1] / 'test.ipynb'


class CoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        notebook = json.loads(NOTEBOOK.read_text())
        source = '\n'.join(''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code')
        tree = ast.parse(source)
        names = {'PERIOD_START', 'PERIOD_END', 'expected_hours'}
        nodes = [node for node in tree.body if
                 (isinstance(node, ast.FunctionDef) and node.name in {'longest_run', 'assess_coverage'}) or
                 (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets))]
        namespace = {'pd': pd, 'np': np}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(NOTEBOOK), 'exec'), namespace)
        cls.assess = staticmethod(namespace['assess_coverage'])
        cls.hours = namespace['expected_hours']

    def setUp(self):
        self.series = pd.Series(1., index=self.hours)

    def test_complete_period_includes_leap_day(self):
        result = self.assess(self.series)
        self.assertEqual(len(self.hours), 17544)
        self.assertEqual(result['complete_months'], 24)
        self.assertTrue(result['eligible_full_period'])
        self.assertEqual(len(self.hours[self.hours.date == pd.Timestamp('2016-02-29').date()]), 24)

    def test_missing_boundaries_and_interior_are_rejected(self):
        for position in [0, 1234, -1]:
            with self.subTest(position=position):
                result = self.assess(self.series.drop(self.hours[position]))
                self.assertFalse(result['eligible_full_period'])
                self.assertEqual(result['longest_missing_hours'], 1)
                self.assertEqual(result['complete_months'], 23)

    def test_invalid_measurements_are_rejected(self):
        for value in [0., -1., np.nan, np.inf, -np.inf]:
            with self.subTest(value=value):
                self.series.iloc[0] = value
                self.assertFalse(self.assess(self.series)['eligible_full_period'])

    def test_initial_zero_run_is_visible(self):
        self.series.iloc[:744] = 0
        result = self.assess(self.series)
        self.assertEqual(result['longest_zero_hours'], 744)
        self.assertEqual(result['min_monthly_valid_pct'], 0)
        self.assertEqual(result['first_positive'], pd.Timestamp('2016-02-01'))
        self.assertFalse(result['eligible_full_period'])


if __name__ == '__main__':
    unittest.main()
