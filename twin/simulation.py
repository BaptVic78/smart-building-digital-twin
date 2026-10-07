import numpy as np
import pandas as pd


def occupation(index, config):
    capacity = config['capacity']
    if not isinstance(capacity, int) or capacity <= 0 or not 0 <= config['daily_variation'] <= 1 or not 0 <= config['weekend_fraction'] <= 1:
        raise ValueError('Paramètres occupation invalides')
    rng = np.random.default_rng(config['seed'])
    days = index.normalize().unique()
    factors = dict(zip(days, rng.uniform(1-config['daily_variation'], 1+config['daily_variation'], len(days))))
    profile = np.interp(index.hour, [0,6,7,8,9,11,12,13,14,16,17,18,19,23], [0,0,0.05,0.4,0.85,0.9,0.55,0.65,0.9,0.8,0.5,0.15,0.02,0])
    profile = np.where(index.dayofweek >= 5, config['weekend_fraction'] * np.where((index.hour >= 9) & (index.hour <= 17), 1, 0), profile)
    rates = np.clip(profile * np.array([factors[d] for d in index.normalize()]), 0, 1)
    counts = rng.binomial(capacity, rates)
    return counts, counts / capacity


def thermal(outdoor, occupants, params):
    r, c = params['resistance_k_per_kw'], params['capacity_kwh_per_k']
    if not all(np.isfinite(list(params.values()))) or r <= 0 or c <= 0 or params['hvac_kw'] < 0 or params['person_kw'] < 0 or params['base_gain_kw'] < 0 or params['heating_c'] >= params['cooling_c']:
        raise ValueError('Paramètres thermiques invalides')
    if not np.isfinite(outdoor).all():
        raise ValueError('Température traitée incomplète: simulation impossible; ajuster explicitement le traitement')
    if len(outdoor) != len(occupants):
        raise ValueError('Entrées thermiques non alignées')
    t = params['initial_c']
    states, powers = [], []
    # Solution exacte RC à forcing constant sur des sous-pas de 5 minutes.
    decay = np.exp(-(1/12)/(r*c))
    for outside, n in zip(outdoor, occupants):
        energy = 0.0
        for _ in range(12):
            hvac = params['hvac_kw'] if t < params['heating_c'] else -params['hvac_kw'] if t > params['cooling_c'] else 0.0
            equilibrium = outside + r*(n*params['person_kw'] + params['base_gain_kw'] + hvac)
            t = equilibrium + (t-equilibrium)*decay
            energy += hvac/12
        if not np.isfinite(t):
            raise ValueError('État thermique non fini')
        states.append(t)
        powers.append(energy)
    return np.array(states), np.array(powers)
