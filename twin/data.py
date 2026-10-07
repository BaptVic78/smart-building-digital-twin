import csv

import numpy as np
import pandas as pd


def require(frame, columns):
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"Colonnes absentes: {sorted(missing)}")


def timestamps(frame, keys=('timestamp',)):
    frame = frame.copy()
    require(frame, keys)
    frame['timestamp'] = pd.to_datetime(frame.timestamp, format='%Y-%m-%d %H:%M:%S', errors='coerce')
    if frame.timestamp.isna().any():
        raise ValueError('Timestamps invalides')
    if frame.duplicated(list(keys)).any():
        raise ValueError(f'Doublons temporels: {keys}')
    if not frame.timestamp.eq(frame.timestamp.dt.floor('h')).all():
        raise ValueError('Timestamps hors grille horaire')
    return frame.sort_values('timestamp')


def load(config, diagnostic=False):
    for path_key in ('metadata', 'electricity', 'weather'):
        with open(config[path_key], newline='') as source:
            header = next(csv.reader(source))
        if len(header) != len(set(header)):
            raise ValueError(f'Colonnes dupliquées: {path_key}')
    meta = pd.read_csv(config['metadata'])
    require(meta, ['building_id', 'site_id', 'timezone', 'primaryspaceusage'])
    if meta.building_id.isna().any() or meta.building_id.duplicated().any():
        raise ValueError('Identifiants bâtiment absents ou dupliqués')
    chosen = meta.loc[meta.building_id.eq(config['building'])]
    if len(chosen) != 1 or chosen.iloc[0].primaryspaceusage != 'Office':
        raise ValueError('Bâtiment Office retenu introuvable')
    building = chosen.iloc[0]
    if pd.isna(building.site_id) or pd.isna(building.timezone):
        raise ValueError('Site/fuseau manquant')
    columns = pd.read_csv(config['electricity'], nrows=0).columns
    ids = [b for b in meta.loc[meta.primaryspaceusage.eq('Office'), 'building_id'] if b in columns] if diagnostic else [config['building']]
    require(pd.DataFrame(columns=columns), ['timestamp', *ids])
    electric = timestamps(pd.read_csv(config['electricity'], usecols=['timestamp', *ids]))
    grid = pd.date_range(config['start'], config['end'], freq='h')
    if len(grid) == 0 or not grid.equals(grid.floor('h')):
        raise ValueError('Période vide ou bornes non horaires')
    electric[ids] = electric[ids].apply(pd.to_numeric, errors='raise')
    electric = electric[electric.timestamp.between(grid[0], grid[-1])].set_index('timestamp')
    absent = len(grid.difference(electric.index))
    electric = electric.reindex(grid).rename_axis('timestamp')
    weather = pd.read_csv(config['weather'])
    require(weather, ['timestamp', 'site_id', 'airTemperature'])
    if weather.site_id.isna().any():
        raise ValueError('Site météo absent')
    weather = timestamps(weather, ('site_id', 'timestamp'))
    return meta, building, electric, weather, absent


def join_weather(electric, weather):
    result = electric.merge(weather, on='timestamp', how='left', validate='one_to_one', indicator=True)
    result['weather_row_present'] = result.pop('_merge').eq('both')
    return result


def treat_temperature(values, mode, max_gap):
    if mode not in ('none', 'causal', 'retrospective') or max_gap < 0:
        raise ValueError('Traitement météo invalide')
    raw = pd.to_numeric(values, errors='raise')
    finite = raw.where(np.isfinite(raw))
    out = finite.copy()
    missing = finite.isna()
    groups = missing.ne(missing.shift()).cumsum()
    if mode == 'retrospective':
        candidate = finite.interpolate(limit_area='inside')
        sizes = missing.groupby(groups).transform('sum')
        out.loc[missing & sizes.le(max_gap)] = candidate
    elif mode == 'causal' and max_gap:
        out = finite.ffill(limit=max_gap)
    return out, missing & out.notna()


def longest(mask):
    return int(mask.groupby(mask.ne(mask.shift()).cumsum()).sum().max()) if len(mask) else 0


def quality(values):
    valid = values.notna() & np.isfinite(values) & values.gt(0)
    monthly = pd.DataFrame({'expected': values.resample('MS').size(), 'positive_finite': valid.resample('MS').sum(), 'missing': values.isna().resample('MS').sum(), 'zeros': values.eq(0).resample('MS').sum(), 'mean_kwh': values.resample('MS').mean(), 'median_kwh': values.resample('MS').median()})
    med = monthly.median_kwh
    def runs(mask):
        groups = mask.ne(mask.shift()).cumsum()
        result = []
        for _, run in mask[mask].groupby(groups[mask]):
            result.append({'start': str(run.index[0]), 'end': str(run.index[-1]), 'hours': len(run)})
        return sorted(result, key=lambda r: r['hours'], reverse=True)
    monthly['negative'] = values.lt(0).resample('MS').sum()
    monthly['infinite'] = (values.notna() & ~np.isfinite(values)).resample('MS').sum()
    from .export import records
    return {'first_positive': str(values[valid].index.min()) if valid.any() else None, 'last_positive': str(values[valid].index.max()) if valid.any() else None, 'missing_pct': float(100*values.isna().mean()), 'zero_pct': float(100*values.eq(0).mean()), 'positive_hours': int(valid.sum()), 'min_monthly_valid_pct': float(100*(monthly.positive_finite/monthly.expected).min()), 'missing_runs': runs(values.isna()), 'zero_runs': runs(values.eq(0)), 'missing': int(values.isna().sum()), 'zeros': int(values.eq(0).sum()), 'negative': int(values.lt(0).sum()), 'infinite': int((values.notna() & ~np.isfinite(values)).sum()), 'longest_missing_hours': longest(values.isna()), 'longest_zero_hours': longest(values.eq(0)), 'longest_constant_hours': int(values.groupby(values.ne(values.shift()).cumsum()).size().max()), 'eligible_full_period': bool(valid.all()), 'complete_months': int(monthly.expected.eq(monthly.positive_finite).sum()), 'monthly_median_ratio': float(med.max()/med.min()) if med.min() > 0 else None, 'monthly': records(monthly.reset_index().assign(timestamp=lambda x: x.timestamp.astype(str)))}
