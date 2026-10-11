import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from twin.baselines import predict_baseline, evaluate_baseline


class BaselineTests(unittest.TestCase):
    def test_exact_lags_and_no_future_leakage(self):
        index = pd.date_range('2017-01-01', periods=200, freq='h')
        series = pd.Series(np.arange(200, dtype=float), index=index)
        result = predict_baseline(series)
        self.assertEqual(list(result.columns), ['actual_kwh', 'last_hour_kwh'])
        self.assertEqual(result.iloc[168].last_hour_kwh, 167)
        modified = series.copy(); modified.iloc[168:] = 99999
        other = predict_baseline(modified)
        pd.testing.assert_frame_equal(result.iloc[:169, 1:], other.iloc[:169, 1:])

    def test_missing_hour_does_not_shift_lags(self):
        index = pd.date_range('2017-01-01', periods=200, freq='h')
        series = pd.Series(np.arange(200, dtype=float), index=index).drop(index[1])
        result = predict_baseline(series)
        self.assertTrue(pd.isna(result.loc[index[2], 'last_hour_kwh']))

    def test_duplicate_rejected(self):
        index = pd.DatetimeIndex(['2017-01-01']*2)
        with self.assertRaises(ValueError): predict_baseline(pd.Series([1.,2.], index=index))

    def test_evaluation_and_known_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            index = pd.date_range('2017-01-01', periods=200, freq='h')
            values = np.arange(200, dtype=float); values[2] = np.nan
            pd.DataFrame({'building_id':'b','timestamp_local':index,'consumption_kwh':values}).to_csv(Path(directory)/'historical_measurements.csv',index=False)
            config = {'output':directory,'building':'b','baseline_evaluation':{'start':str(index[1]),'end':str(index[-1])}}
            report = evaluate_baseline(config)
            self.assertEqual(report['evaluated_hours'],197)
            self.assertEqual(report['excluded_hours'],2)
            for metric in ['mae_kwh','rmse_kwh','bias_kwh']:
                self.assertEqual(report['metrics']['last_hour'][metric],-1 if metric=='bias_kwh' else 1)
            exported=json.loads((Path(directory)/'baselines/metrics.json').read_text())
            self.assertEqual(exported,report)
