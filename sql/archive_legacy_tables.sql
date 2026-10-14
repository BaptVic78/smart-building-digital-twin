-- Après import et vérification de training_measurements.
-- Migration réversible : les anciennes tables et leurs données sont conservées.
begin;

do $migration$
declare
    legacy_table text;
begin
    if to_regclass('public.training_measurements') is null then
        raise exception 'Importer la table finale avant de déplacer les sources';
    end if;
    if not exists (select 1 from public.training_measurements) then
        raise exception 'La table finale est vide';
    end if;

    -- Refuser l'archivage si le compteur importé diffère encore des sources.
    if to_regclass('public.historical_measurements') is not null then
        if exists (
            select 1
            from public.historical_measurements h
            full join public.training_measurements t
                using (building_id, timestamp_local)
            where h.building_id is null or t.building_id is null
                or h.consumption_kwh is distinct from t.consumption_kwh
                or h.electricity_row_present is distinct from t.electricity_row_present
                or h.weather_row_present is distinct from t.weather_row_present
        ) then
            raise exception 'Les mesures de la table finale diffèrent des sources';
        end if;
    end if;

    create schema if not exists archive;
    foreach legacy_table in array array[
        'buildings', 'historical_measurements', 'simulation_runs', 'simulated_states'
    ] loop
        if to_regclass(format('public.%I', legacy_table)) is not null then
            if to_regclass(format('archive.%I', legacy_table)) is not null then
                raise exception 'Une archive existe déjà pour %', legacy_table;
            end if;
            execute format('alter table public.%I set schema archive', legacy_table);
        end if;
    end loop;
end;
$migration$;

grant select, insert, update on public.training_measurements to service_role;
notify pgrst, 'reload schema';
commit;

-- Restauration éventuelle, à exécuter explicitement et sans conflit de noms :
-- alter table archive.buildings set schema public;
-- alter table archive.historical_measurements set schema public;
-- alter table archive.simulation_runs set schema public;
-- alter table archive.simulated_states set schema public;
