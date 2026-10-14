-- Table finale unique. Aucun DROP des anciennes tables.
begin;
create table if not exists public.training_measurements (
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
create index if not exists training_time_idx on public.training_measurements(timestamp_local);
create index if not exists training_split_idx on public.training_measurements(training_split, is_training_ready);
alter table public.training_measurements enable row level security;
commit;
