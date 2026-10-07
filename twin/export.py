import hashlib
import json
import logging
import os
import re
import urllib.error
from pathlib import Path
import urllib.request
import urllib.parse

import numpy as np
import pandas as pd

TABLE_KEYS = {'buildings': 'building_id', 'historical_measurements': 'building_id,timestamp_local', 'simulation_runs': 'run_id', 'simulated_states': 'run_id,timestamp_local'}


def supabase_headers(secret, method):
    """Les nouvelles clés secrètes utilisent apikey; les JWT legacy ajoutent Bearer."""
    headers = {
        'apikey': secret,
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates,return=minimal' if method == 'POST' else 'count=exact',
        'Range': '0-0',
    }
    if not secret.startswith('sb_secret_'):
        headers['Authorization'] = f'Bearer {secret}'
    return headers


def http_error_details(error):
    """Expose le statut et un code structuré, jamais le message distant."""
    code = None
    try:
        payload = json.loads(error.read(8192))
        candidate = payload.get('code') if isinstance(payload, dict) else None
        if isinstance(candidate, str) and re.fullmatch(r'(?:PGRST[0-9]{3}|[0-9A-Z]{5})', candidate):
            code = candidate
    except (ValueError, OSError):
        pass
    hint = {
        401: 'Vérifier la clé et son appartenance au projet Supabase.',
        403: 'Vérifier les permissions et la clé serveur utilisée.',
        404: 'Vérifier que le SQL a été exécuté et que la table est accessible.',
    }.get(error.code, 'Vérifier le schéma et les journaux API Supabase.')
    return f"HTTP {error.code}" + (f"; code {code}" if code else '') + f". {hint}"


def records(frame):
    # PostgreSQL float8 accepte les infinis, JSON standard non: représentation textuelle explicite.
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(v) for v in value]
        if pd.isna(value):
            return None
        if isinstance(value, (float, np.floating)) and np.isinf(value):
            return 'Infinity' if value > 0 else '-Infinity'
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        return value
    return [{k: clean(v) for k, v in row.items()} for row in frame.to_dict('records')]


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write_tables(output, tables):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output/'manifest.json').unlink(missing_ok=True)
    for name, frame in tables.items():
        frame.to_csv(output / f'{name}.csv', index=False)
        (output / f'{name}.json').write_text(json.dumps(records(frame), allow_nan=False, indent=2) + '\n')

    (output/'manifest.json').write_text(json.dumps({name: digest(output/f'{name}.json') for name in tables}, indent=2)+'\n')


def load_tables(output, batch_size=500, dry_run=False, request=None):
    if batch_size < 1:
        raise ValueError('Taille de lot invalide')
    manifest = json.loads((Path(output)/'manifest.json').read_text())
    if any(manifest.get(name) != digest(Path(output)/f'{name}.json') for name in TABLE_KEYS):
        raise ValueError('Exports incomplets ou modifiés: relancer prepare')
    payloads = {name: json.loads((Path(output)/f'{name}.json').read_text()) for name in TABLE_KEYS}
    for name, rows in payloads.items():
        keys = TABLE_KEYS[name].split(',')
        ids = [tuple(row[k] for k in keys) for row in rows]
        if len(ids) != len(set(ids)) or any(None in key for key in ids):
            raise ValueError(f'Clés invalides: {name}')
    if dry_run:
        for name, rows in payloads.items():
            logging.info('Dry-run %s: %d lignes, %d lots', name, len(rows), (len(rows)+batch_size-1)//batch_size)
        return
    url, secret = os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    if request is None:
        if not url or not secret or not url.startswith('https://'):
            raise ValueError('SUPABASE_URL HTTPS et SUPABASE_SERVICE_ROLE_KEY requis')
        def request(method, table, query, rows=None):
            headers = supabase_headers(secret, method)
            req = urllib.request.Request(url.rstrip('/')+'/rest/v1/'+table+'?'+urllib.parse.urlencode(query), data=json.dumps(rows, allow_nan=False).encode() if rows is not None else None, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    return response.headers.get('Content-Range', '')
            except urllib.error.HTTPError as error:
                raise RuntimeError(f'Échec Supabase {method} {table}: {http_error_details(error)}') from None
            except urllib.error.URLError:
                raise RuntimeError(f'Échec réseau Supabase {method} {table}: vérifier connexion, DNS et URL du projet.') from None
            except TimeoutError:
                raise RuntimeError(f'Délai dépassé Supabase {method} {table}; relancer le chargement.') from None
    for name, rows in payloads.items():
        for start in range(0, len(rows), batch_size):
            request('POST', name, {'on_conflict': TABLE_KEYS[name]}, rows[start:start+batch_size])
        # Vérifier le périmètre exact importé (la table peut contenir d'autres exécutions).
        scopes = {}
        scope_key = 'run_id' if name in ('simulation_runs', 'simulated_states') else 'building_id'
        for row in rows:
            scopes[row[scope_key]] = scopes.get(row[scope_key], 0)+1
        for scope, expected in scopes.items():
            query = {'select': '*', scope_key: f'eq.{scope}'}
            if 'timestamp_local' in TABLE_KEYS[name]:
                times = [r['timestamp_local'] for r in rows if r[scope_key] == scope]
                query['and'] = f'(timestamp_local.gte.{min(times)},timestamp_local.lte.{max(times)})'
            content_range = request('HEAD', name, query)
            actual = int(content_range.rsplit('/', 1)[-1])
            if actual != expected:
                raise RuntimeError(f'Comptage {name}: attendu {expected}, reçu {actual}')
        logging.info('%s: %d lignes vérifiées', name, len(rows))
