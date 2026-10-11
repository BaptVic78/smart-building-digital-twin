"""Prévisions à une heure, évaluées en relecture chronologique sans ajustement."""
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .data import timestamps
from .export import digest


def predict_baseline(consumption):
    """L'index désigne l'heure cible; chaque prédiction utilise un passé strict."""
    if not isinstance(consumption.index, pd.DatetimeIndex) or consumption.empty:
        raise ValueError('Série temporelle vide ou sans index datetime')
    if consumption.index.has_duplicates or consumption.index.hasnans:
        raise ValueError('Timestamps dupliqués ou invalides')
    if consumption.index.tz is not None or not consumption.index.equals(consumption.index.floor('h')):
        raise ValueError('Heures locales naïves entières requises')
    series = pd.to_numeric(consumption.sort_index(), errors='raise')
    result = pd.DataFrame({'actual_kwh': series})
    # Recherche à t-1 h par timestamp: ne pas traverser une heure absente.
    result['last_hour_kwh'] = series.reindex(series.index - pd.Timedelta(hours=1)).to_numpy()
    result.index.name = 'target_timestamp_local'
    return result


def evaluate_baseline(config):
    source = Path(config['output']) / 'historical_measurements.csv'
    history = pd.read_csv(source, usecols=['building_id', 'timestamp_local', 'consumption_kwh'])
    history = history.loc[history.building_id.eq(config['building'])]
    history = timestamps(history.rename(columns={'timestamp_local': 'timestamp'}))
    if history.empty:
        raise ValueError('Aucune mesure pour le bâtiment configuré; lancer prepare')
    predictions = predict_baseline(history.set_index('timestamp').consumption_kwh)
    period = config['baseline_evaluation']
    start, end = pd.Timestamp(period['start']), pd.Timestamp(period['end'])
    if start.tzinfo is not None or end.tzinfo is not None or start > end or start != start.floor('h') or end != end.floor('h'):
        raise ValueError('Bornes locales horaires invalides pour la baseline')
    grid = pd.date_range(start, end, freq='h')
    if start < predictions.index.min() or end > predictions.index.max():
        raise ValueError('Période d’évaluation hors de l’historique disponible')
    predictions = predictions.reindex(grid).rename_axis('target_timestamp_local')
    finite = np.isfinite(predictions)
    evaluated = finite.all(axis=1)
    if not evaluated.any():
        raise ValueError('Aucune heure évaluable pour la baseline')
    predictions['evaluated'] = evaluated
    report = {
        'building_id': config['building'], 'source': str(source), 'source_sha256': digest(source),
        'start_local': str(start), 'end_local': str(end), 'horizon_hours': 1,
        'expected_hours': len(grid), 'actual_finite_hours': int(finite.actual_kwh.sum()),
        'evaluated_hours': int(evaluated.sum()), 'excluded_hours': int((~evaluated).sum()),
        'protocol': 'Rolling one-hour-ahead; previous observations available; no fitting; nominal local hours.',
        'metrics': {},
    }
    error = predictions.loc[evaluated, 'last_hour_kwh'] - predictions.loc[evaluated, 'actual_kwh']
    report['metrics']['last_hour'] = {
        'available_prediction_hours': int(finite.last_hour_kwh.sum()),
        'mae_kwh': float(error.abs().mean()),
        'rmse_kwh': float(np.sqrt(np.mean(error.to_numpy() ** 2))),
        'bias_kwh': float(error.mean()),
    }
    logging.info('Dernière heure: MAE %.3f kWh, RMSE %.3f kWh (%d heures)',
                 report['metrics']['last_hour']['mae_kwh'],
                 report['metrics']['last_hour']['rmse_kwh'], evaluated.sum())
    output = Path(config['output']) / 'baselines'
    output.mkdir(parents=True, exist_ok=True)
    predictions.reset_index().to_csv(output / 'predictions.csv', index=False)
    (output / 'metrics.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    logging.info('Baseline exportée dans %s; %d heures exclues', output, report['excluded_hours'])
    return report
