import json

import pandas as pd
import streamlit as st

from dashboard.data import ROOT, DashboardData, load_dashboard_data


st.set_page_config(
    page_title="Jumeau énergétique",
    page_icon="🏢",
    layout="wide",
)


def render_overview(data: DashboardData, building_id: str, run_id: str):
    building = data.buildings.loc[data.buildings["building_id"].eq(building_id)].iloc[0]
    measurements = data.measurements.loc[
        data.measurements["building_id"].eq(building_id)
    ].copy()
    run = data.simulation_runs.loc[data.simulation_runs["run_id"].eq(run_id)].iloc[0]
    states = data.states.loc[data.states["run_id"].eq(run_id)].copy()
    quality = data.quality_report["electricity"]

    st.title("Vue d’ensemble")
    st.caption(
        f"{building_id} · site {building['site_id']} · {building['timezone']} · "
        f"exports actualisés le {data.exports_updated_at:%d/%m/%Y à %H:%M}"
    )

    first_hour = measurements["timestamp_local"].min()
    last_hour = measurements["timestamp_local"].max()
    missing_weather = int((~measurements["weather_row_present"]).sum())
    unresolved_temperature = int(
        measurements["outdoor_temperature_processed_c"].isna().sum()
    )

    columns = st.columns(4)
    columns[0].metric("Heures historiques", f"{len(measurements):,}".replace(",", " "))
    columns[1].metric(
        "Consommation moyenne",
        f"{measurements['consumption_kwh'].mean():.2f} kWh/intervalle",
    )
    columns[2].metric("Heures électriques manquantes", f"{quality['missing']:,}".replace(",", " "))
    columns[3].metric("Lignes météo absentes", f"{missing_weather:,}".replace(",", " "))

    columns = st.columns(4)
    columns[0].metric(
        "Températures imputées",
        f"{int(measurements['temperature_imputed'].sum()):,}".replace(",", " "),
    )
    columns[1].metric("Températures non résolues", f"{unresolved_temperature:,}")
    columns[2].metric("États simulés", f"{len(states):,}".replace(",", " "))
    columns[3].metric(
        "Occupation moyenne simulée",
        f"{states['occupancy_rate'].mean() * 100:.1f} %",
    )

    st.caption(f"Période disponible : {first_hour:%d/%m/%Y %H:%M} — {last_hour:%d/%m/%Y %H:%M}")
    window = st.selectbox(
        "Période affichée",
        ["Période complète", "30 derniers jours", "7 derniers jours"],
    )
    if window == "30 derniers jours":
        measurements = measurements.loc[
            measurements["timestamp_local"] >= last_hour - pd.Timedelta(days=30)
        ]
    elif window == "7 derniers jours":
        measurements = measurements.loc[
            measurements["timestamp_local"] >= last_hour - pd.Timedelta(days=7)
        ]

    measurements = measurements.set_index("timestamp_local")
    states = states.set_index("timestamp_local")

    left, right = st.columns(2)
    with left:
        st.subheader("Consommation électrique")
        daily_consumption = measurements["consumption_kwh"].resample("D").mean()
        st.line_chart(daily_consumption, y_label="kWh par intervalle horaire")
    with right:
        st.subheader("Température extérieure")
        daily_outdoor = measurements["outdoor_temperature_processed_c"].resample("D").mean()
        st.line_chart(daily_outdoor, y_label="°C")

    left, right = st.columns(2)
    with left:
        st.subheader("Occupation simulée")
        daily_occupancy = states["occupancy_rate"].resample("D").mean()
        st.line_chart(daily_occupancy, y_label="Taux d’occupation")
    with right:
        st.subheader("État thermique simulé")
        daily_indoor = states["indoor_temperature_c"].resample("D").mean()
        st.line_chart(daily_indoor, y_label="°C")

    st.subheader("Qualité des mesures électriques")
    monthly = pd.DataFrame(quality.get("monthly", []))
    if not monthly.empty:
        st.dataframe(monthly, use_container_width=True, hide_index=True)
    st.caption(
        f"Première heure : {quality.get('first_positive') or '—'} · "
        f"Dernière heure : {quality.get('last_positive') or '—'} · "
        f"Séquence manquante maximale : {quality.get('longest_missing_hours', 0)} h · "
        f"Séquence de zéros maximale : {quality.get('longest_zero_hours', 0)} h"
    )

    with st.expander("Rapport qualité complet"):
        st.json(data.quality_report)

    with st.expander("Détails de l’exécution de simulation"):
        st.write(
            {
                "run_id": run["run_id"],
                "model_version": run["model_version"],
                "états_attendus": int(run["expected_states"]),
                "température_intérieure_moyenne_c": round(
                    float(states["indoor_temperature_c"].mean()), 2
                ),
                "énergie_thermique_HVAC_signée_kwh": round(
                    float(states["hvac_thermal_energy_kwh"].sum()), 2
                ),
            }
        )
        st.json(run.get("parameters", {}))


def render_live_view(data: DashboardData, building_id: str, run_id: str):
    st.title("Suivi opérationnel")
    st.warning(
        "Aucun flux temps réel n’est connecté. Les données ci-dessous proviennent "
        "des exports historiques préparés localement ; elles ne représentent pas "
        "des mesures en direct."
    )
    if st.button("Recharger les exports"):
        st.rerun()

    measurements = data.measurements.loc[
        data.measurements["building_id"].eq(building_id)
    ].copy()
    states = data.states.loc[data.states["run_id"].eq(run_id)].copy()
    recent = measurements.merge(
        states[
            [
                "timestamp_local",
                "occupants",
                "indoor_temperature_c",
                "hvac_thermal_energy_kwh",
            ]
        ],
        on="timestamp_local",
        how="left",
        validate="one_to_one",
    )
    recent = recent.sort_values("timestamp_local").tail(24)
    if recent.empty:
        st.info("Aucune donnée exportée pour ce bâtiment et cette exécution.")
        return

    latest = recent.iloc[-1]
    st.caption(
        f"Dernière observation disponible dans l’export : "
        f"{latest['timestamp_local']:%d/%m/%Y %H:%M}"
    )
    columns = st.columns(4)
    columns[0].metric(
        "Consommation",
        f"{latest['consumption_kwh']:.2f} kWh/intervalle",
        help="Valeur historique exportée, pas une mesure en temps réel.",
    )
    columns[1].metric(
        "Température extérieure",
        f"{latest['outdoor_temperature_processed_c']:.1f} °C",
    )
    columns[2].metric("Occupants simulés", f"{int(latest['occupants']):,}".replace(",", " "))
    columns[3].metric("Température intérieure simulée", f"{latest['indoor_temperature_c']:.1f} °C")
    st.subheader("Dernières 24 heures de l’export")
    st.dataframe(recent, use_container_width=True, hide_index=True)


def main():
    st.sidebar.title("Jumeau énergétique")
    page = st.sidebar.radio(
        "Navigation",
        ["Vue d’ensemble", "Suivi (flux non connecté)"],
    )

    try:
        data = load_dashboard_data(ROOT / "config.json")
    except FileNotFoundError as error:
        st.title("Jumeau énergétique")
        st.info(
            "Les exports ne sont pas encore disponibles. Récupérez les données "
            "sources puis exécutez `python -m twin prepare` depuis la racine du projet."
        )
        st.caption(str(error))
        if page == "Suivi (flux non connecté)":
            st.warning("Le suivi en direct sera activé lorsqu’une source de flux sera configurée.")
        return
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        st.error(f"Impossible de charger les exports : {error}")
        return

    building_ids = data.buildings["building_id"].tolist()
    building_id = st.sidebar.selectbox("Bâtiment", building_ids)
    runs = data.simulation_runs.loc[
        data.simulation_runs["building_id"].eq(building_id)
    ]
    run_ids = runs["run_id"].tolist()
    if not run_ids:
        st.error(f"Aucune exécution de simulation trouvée pour {building_id}.")
        return
    run_id = st.sidebar.selectbox("Exécution simulée", run_ids, format_func=str)

    if page == "Vue d’ensemble":
        render_overview(data, building_id, run_id)
    else:
        render_live_view(data, building_id, run_id)


if __name__ == "__main__":
    main()
