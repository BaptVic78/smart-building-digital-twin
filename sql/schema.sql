-- Installation neuve : mesures et suivi des rejeux.
begin;
create table if not exists public.measurements (
 building_id text not null,
 timestamp_local timestamp without time zone not null,
 consumption_kwh double precision,
 outdoor_temperature_processed_c double precision,
 occupants integer not null,
 indoor_temperature_c double precision not null,
 hvac_thermal_energy_kwh double precision not null,
 temperature_imputed boolean not null,
 weather_row_present boolean not null,
 electricity_row_present boolean not null,
 context_is_simulated boolean not null,
 hour integer not null,
 dayofweek integer not null,
 month integer not null,
 is_weekend boolean not null,
 consumption_lag_1h_kwh double precision,
 consumption_lag_24h_kwh double precision,
 consumption_lag_168h_kwh double precision,
 consumption_mean_24h_kwh double precision,
 consumption_mean_168h_kwh double precision,
 outdoor_temperature_lag_1h_c double precision,
 dst_time_issue boolean not null,
 training_split text not null,
 is_training_ready boolean not null,
 anomaly_label integer,
 primary key (building_id, timestamp_local),
 check (occupants >= 0),
 check (hour between 0 and 23),
 check (dayofweek between 0 and 6),
 check (month between 1 and 12),
 check (training_split in ('train', 'validation', 'test')),
 check (anomaly_label in (0, 1)),
 check (timestamp_local = date_trunc('hour', timestamp_local))
);
create index if not exists measurements_time_idx on public.measurements(timestamp_local);
create index if not exists measurements_split_idx on public.measurements(training_split, is_training_ready);
alter table public.measurements enable row level security;

-- Tables de suivi. Les heures du dataset restent locales sans conversion UTC.
create table if not exists public.replay_runs (
 run_id uuid primary key default gen_random_uuid(),
 building_id text not null,
 status text not null default 'pending' check (status in ('pending', 'running', 'completed', 'failed')),
 replay_start timestamp without time zone not null,
 replay_end timestamp without time zone not null,
 last_processed_at timestamp without time zone,
 model_version text not null,
 model_sha256 text not null check (model_sha256 ~ '^[0-9a-f]{64}$'),
 dataset_sha256 text not null check (dataset_sha256 ~ '^[0-9a-f]{64}$'),
 feature_columns jsonb not null check (jsonb_typeof(feature_columns) = 'array'),
 alert_rule jsonb not null check (jsonb_typeof(alert_rule) = 'object'),
 started_at timestamptz,
 finished_at timestamptz,
 unique (run_id, building_id),
 check (replay_start <= replay_end),
 check (replay_start = date_trunc('hour', replay_start)),
 check (replay_end = date_trunc('hour', replay_end)),
 check (last_processed_at is null or
   (last_processed_at between replay_start and replay_end
    and last_processed_at = date_trunc('hour', last_processed_at))),
 check (finished_at is null or (started_at is not null and finished_at >= started_at)),
 check (status = 'pending' or started_at is not null),
 check (status not in ('completed', 'failed') or finished_at is not null)
);

create table if not exists public.predictions (
 run_id uuid not null,
 building_id text not null,
 timestamp_local timestamp without time zone not null,
 predicted_kwh double precision not null check (predicted_kwh > '-Infinity'::float8 and predicted_kwh < 'Infinity'::float8),
 actual_kwh double precision,
 residual_kwh double precision,
 predicted_at timestamptz not null default now(),
 evaluated_at timestamptz,
 primary key (run_id, building_id, timestamp_local),
 foreign key (run_id, building_id) references public.replay_runs(run_id, building_id),
 foreign key (building_id, timestamp_local) references public.measurements(building_id, timestamp_local),
 check (
   (actual_kwh is null and residual_kwh is null and evaluated_at is null)
   or (actual_kwh is not null and residual_kwh is not null and evaluated_at is not null
       and actual_kwh > '-Infinity'::float8 and actual_kwh < 'Infinity'::float8
       and residual_kwh > '-Infinity'::float8 and residual_kwh < 'Infinity'::float8
       and abs(residual_kwh - (actual_kwh - predicted_kwh)) <= 1e-9
       and evaluated_at >= predicted_at)
 )
);

create table if not exists public.alerts (
 run_id uuid not null,
 building_id text not null,
 timestamp_local timestamp without time zone not null,
 alert_type text not null check (alert_type in ('underconsumption', 'overconsumption')),
 threshold_kwh double precision not null,
 context jsonb not null default '{}'::jsonb check (jsonb_typeof(context) = 'object'),
 hypotheses jsonb not null default '[]'::jsonb check (jsonb_typeof(hypotheses) = 'array'),
 triggered_at timestamptz not null default now(),
 primary key (run_id, building_id, timestamp_local),
 foreign key (run_id, building_id, timestamp_local)
   references public.predictions(run_id, building_id, timestamp_local),
 check ((alert_type = 'underconsumption' and threshold_kwh < 0 and threshold_kwh > '-Infinity'::float8)
     or (alert_type = 'overconsumption' and threshold_kwh > 0 and threshold_kwh < 'Infinity'::float8))
);

create index if not exists predictions_measurement_idx on public.predictions(building_id, timestamp_local);
alter table public.replay_runs enable row level security;
alter table public.predictions enable row level security;
alter table public.alerts enable row level security;
-- Aucun accès public : lecture/écriture depuis Python côté serveur uniquement.
grant select, insert, update on public.measurements, public.replay_runs, public.predictions, public.alerts to service_role;
commit;
