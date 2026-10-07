-- À exécuter manuellement dans l'éditeur SQL Supabase. Aucun besoin de TimescaleDB.
begin;
create table if not exists public.buildings (
 building_id text primary key, site_id text not null, timezone text not null,
 primary_space_usage text not null, area_sqm double precision check (area_sqm > 0),
 source_path text not null, source_sha256 text not null
);
create table if not exists public.historical_measurements (
 building_id text not null references public.buildings(building_id),
 timestamp_local timestamp without time zone not null,
 consumption_kwh double precision, electricity_row_present boolean not null,
 weather_row_present boolean not null, outdoor_temperature_original_c double precision,
 outdoor_temperature_processed_c double precision, temperature_imputed boolean not null,
 temperature_treatment text not null check (temperature_treatment in ('none','causal','retrospective')),
 temperature_max_gap_hours integer not null check (temperature_max_gap_hours >= 0),
 weather_original jsonb not null, electricity_source text not null, weather_source text not null,
 electricity_sha256 text not null, weather_sha256 text not null,
 primary key (building_id,timestamp_local),
 check (not temperature_imputed or outdoor_temperature_processed_c is not null),
 check (timestamp_local = date_trunc('hour', timestamp_local))
);
create table if not exists public.simulation_runs (
 run_id uuid primary key, building_id text not null references public.buildings(building_id),
 model_version text not null, parameters jsonb not null,
 is_simulated boolean not null default true check (is_simulated),
 start_local timestamp without time zone not null, end_local timestamp without time zone not null,
 expected_states integer not null check (expected_states > 0),
 created_at timestamptz not null default now(), check (end_local >= start_local)
);
create table if not exists public.simulated_states (
 run_id uuid not null references public.simulation_runs(run_id),
 timestamp_local timestamp without time zone not null,
 occupants integer not null check (occupants >= 0),
 occupancy_rate double precision not null check (occupancy_rate between 0 and 1),
 indoor_temperature_c double precision not null check (indoor_temperature_c > '-Infinity'::float8 and indoor_temperature_c < 'Infinity'::float8),
 hvac_thermal_energy_kwh double precision not null,
 primary key (run_id,timestamp_local), check (timestamp_local = date_trunc('hour', timestamp_local))
);
create index if not exists history_time_idx on public.historical_measurements(timestamp_local);
create index if not exists states_time_idx on public.simulated_states(timestamp_local);
create index if not exists runs_building_idx on public.simulation_runs(building_id);
-- Accès client fermé: le chargeur utilise la clé service_role côté serveur uniquement.
alter table public.buildings enable row level security;
alter table public.historical_measurements enable row level security;
alter table public.simulation_runs enable row level security;
alter table public.simulated_states enable row level security;
commit;
