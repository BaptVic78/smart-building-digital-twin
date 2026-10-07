import json
import io
import urllib.error
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from twin.data import timestamps, join_weather, treat_temperature
from twin.simulation import occupation, thermal
from twin.export import write_tables, load_tables, TABLE_KEYS, records

CONFIG = json.loads((Path(__file__).resolve().parents[1]/'config.json').read_text())


class PipelineTests(unittest.TestCase):
    def test_supabase_headers_support_both_server_key_formats(self):
        from twin.export import supabase_headers
        modern = supabase_headers('sb_secret_test_fixture', 'POST')
        self.assertEqual(modern['apikey'], 'sb_secret_test_fixture')
        self.assertNotIn('Authorization', modern)
        self.assertIn('resolution=merge-duplicates', modern['Prefer'])
        legacy = supabase_headers('legacy-jwt-test-fixture', 'HEAD')
        self.assertEqual(legacy['Authorization'], 'Bearer legacy-jwt-test-fixture')
        self.assertEqual(legacy['Prefer'], 'count=exact')

    def test_http_diagnostics_hide_sensitive_content(self):
        from twin.export import http_error_details
        for payload in [{'code':'PGRST205','message':'secret-token'}, {'code':'secret-token','message':'secret-token'}, ['secret-token']]:
            error = urllib.error.HTTPError('https://private-url',404,'secret-token',{},io.BytesIO(json.dumps(payload).encode()))
            message = http_error_details(error)
            self.assertIn('HTTP 404',message)
            self.assertNotIn('secret-token',message)
            self.assertNotIn('private-url',message)
        error = urllib.error.HTTPError('https://private-url',401,'secret-token',{},io.BytesIO(b'not JSON secret-token'))
        self.assertIn('HTTP 401',http_error_details(error))

    def test_temporal_validation(self):
        for times in [['bad'], ['2016-01-01 00:00:00']*2, ['2016-01-01 00:30:00']]:
            with self.assertRaises(ValueError): timestamps(pd.DataFrame({'timestamp': times}))

    def test_left_join_preserves_and_distinguishes(self):
        index = pd.date_range('2016-01-01', periods=3, freq='h')
        e = pd.DataFrame({'timestamp':index, 'energy':[0.,-1.,np.inf]})
        w = pd.DataFrame({'timestamp':index[:2], 'airTemperature':[10.,np.nan]})
        result = join_weather(e,w)
        self.assertEqual(len(result),3)
        self.assertEqual(result.weather_row_present.tolist(),[True,True,False])
        pd.testing.assert_series_equal(result.energy,e.energy)
        with self.assertRaises(pd.errors.MergeError): join_weather(e,pd.concat([w,w]))

    def test_weather_modes(self):
        s = pd.Series([np.nan,10.,np.nan,np.nan,16.,np.nan,np.nan,np.nan,20.,np.nan])
        retro, flags = treat_temperature(s,'retrospective',2)
        self.assertEqual(retro.iloc[2],12)
        self.assertEqual(retro.iloc[3],14)
        self.assertTrue(retro.iloc[5:8].isna().all())
        self.assertTrue(pd.isna(retro.iloc[0]))
        self.assertTrue(pd.isna(retro.iloc[-1]))
        causal, _ = treat_temperature(s,'causal',2)
        self.assertEqual(causal.iloc[2],10)
        self.assertTrue(pd.isna(causal.iloc[7]))
        altered = s.copy(); altered.iloc[4:] = 999
        a,_ = treat_temperature(altered,'causal',2)
        pd.testing.assert_series_equal(causal.iloc[:4],a.iloc[:4])
        self.assertEqual(flags.sum(),2)

    def test_occupation_reproducibility(self):
        index = pd.date_range('2016-01-01',periods=24*30,freq='h')
        counts,rates = occupation(index,CONFIG)
        other,_ = occupation(index,CONFIG)
        np.testing.assert_equal(counts,other)
        self.assertTrue(np.issubdtype(counts.dtype,np.integer))
        self.assertTrue(((rates>=0)&(rates<=1)).all())
        changed,_ = occupation(index,{**CONFIG,'seed':43})
        self.assertFalse(np.array_equal(counts,changed))

    def test_rc_analytic_and_extreme_stability(self):
        p = {**CONFIG['thermal'],'hvac_kw':0.,'person_kw':0.,'base_gain_kw':0.}
        result,_ = thermal(np.full(100,10.), np.zeros(100),p)
        expected = 10+(p['initial_c']-10)*np.exp(-np.arange(1,101)/(p['resistance_k_per_kw']*p['capacity_kwh_per_k']))
        np.testing.assert_allclose(result,expected)
        p.update(resistance_k_per_kw=.0001,capacity_kwh_per_k=.0001)
        result,_ = thermal(np.full(100,-50.),np.zeros(100),p)
        self.assertTrue(np.isfinite(result).all())
        self.assertAlmostEqual(result[-1],-50.)
        with self.assertRaises(ValueError): thermal(np.array([np.nan]),[0],p)

    def test_prepare_synthetic_fixture_and_manifest(self):
        from twin.pipeline import prepare
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            times = pd.date_range('2016-01-01', periods=48, freq='h')
            pd.DataFrame([{'building_id':'Hog_office_Miriam','site_id':'actual_site', 'timezone':'US/Central','primaryspaceusage':'Office'}]).to_csv(root/'metadata.csv',index=False)
            pd.DataFrame({'timestamp':times, 'Hog_office_Miriam':np.arange(48,dtype=float)}).drop(index=5).to_csv(root/'electricity.csv',index=False)
            temperatures = np.full(48,10.); temperatures[10]=np.nan
            pd.DataFrame({'timestamp':times,'site_id':'actual_site','airTemperature':temperatures}).drop(index=11).to_csv(root/'weather.csv',index=False)
            config = {**CONFIG, 'metadata':str(root/'metadata.csv'),'electricity':str(root/'electricity.csv'),'weather':str(root/'weather.csv'),'output':str(root/'out'),'end':str(times[-1])}
            report = prepare(config)
            self.assertEqual(report['site_id'],'actual_site')
            self.assertEqual(report['electricity_rows_absent'],1)
            self.assertEqual(report['weather_rows_absent'],1)
            history=json.loads((root/'out/historical_measurements.json').read_text())
            self.assertEqual(len(history),48)
            self.assertEqual(history[0]['consumption_kwh'],0.)
            self.assertIsNone(history[5]['consumption_kwh'])
            self.assertFalse(history[5]['electricity_row_present'])
            self.assertTrue(history[10]['temperature_imputed'])
            manifest=(root/'out/manifest.json').read_text()
            prepare(config)
            self.assertEqual(manifest,(root/'out/manifest.json').read_text())
            load_tables(root/'out',dry_run=True)
            with (root/'out/buildings.json').open('a') as f: f.write(' ')
            with self.assertRaises(ValueError): load_tables(root/'out',dry_run=True)

    def test_null_and_infinity_serialization(self):
        result = records(pd.DataFrame({'v':[np.nan,np.inf,-np.inf,0.]}))
        self.assertEqual(result,[{'v':None},{'v':'Infinity'},{'v':'-Infinity'},{'v':0.}])
        json.dumps(result,allow_nan=False)

    def test_loader_idempotence_batches_counts_and_dry_run(self):
        tables = {
            'buildings':pd.DataFrame([{'building_id':'b'}]),
            'historical_measurements':pd.DataFrame([{'building_id':'b','timestamp_local':f'2016-01-01 0{i}:00:00','consumption_kwh':np.nan} for i in range(3)]),
            'simulation_runs':pd.DataFrame([{'run_id':'r'}]),
            'simulated_states':pd.DataFrame([{'run_id':'r','timestamp_local':f'2016-01-01 0{i}:00:00'} for i in range(3)])}
        store = {name:{} for name in tables}; calls=[]
        def fake(method,table,query,rows=None):
            calls.append((method,table))
            if method=='POST':
                self.assertEqual(query['on_conflict'],TABLE_KEYS[table])
                self.assertLessEqual(len(rows),2)
                for row in rows:
                    key=tuple(row[k] for k in TABLE_KEYS[table].split(',')); store[table][key]=row
            else: return f'*/{len(store[table])}'
        with tempfile.TemporaryDirectory() as directory:
            write_tables(directory,tables)
            load_tables(directory,2,True,request=fake)
            self.assertEqual(calls,[])
            load_tables(directory,2,request=fake)
            load_tables(directory,2,request=fake)
            self.assertEqual([len(store[t]) for t in tables],[1,3,1,3])
            self.assertIsNone(next(iter(store['historical_measurements'].values()))['consumption_kwh'])
            def wrong_count(method,table,query,rows=None): return '*/99'
            with self.assertRaises(RuntimeError): load_tables(directory,2,request=wrong_count)


if __name__ == '__main__': unittest.main()
