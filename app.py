import json

import numpy as np
import pandas as pd
import streamlit as st

from dashboard.data import ROOT, DashboardData, load_dashboard_data


st.set_page_config(
    page_title="Jumeau énergétique",
    page_icon="🏢",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(180deg, #f3f7f6 0%, #ffffff 280px);
    }
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e2eae7;
        border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 3px 12px rgba(18, 56, 48, 0.05);
    }
    [data-testid="stMetricLabel"] {
        color: #58716a !important;
    }
    [data-testid="stMetricValue"] {
        color: #173c34 !important;
    }
    h1, h2, h3 {
        color: #173c34;
    }
    </style>
    """,
    unsafe_allow_html=True,
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

    last_available_hour = measurements["timestamp_local"].max()
    window = st.sidebar.selectbox(
        "Période affichée",
        ["Période complète", "30 derniers jours", "7 derniers jours"],
    )
    if window == "30 derniers jours":
        start = last_available_hour.normalize() - pd.Timedelta(days=29)
        measurements = measurements.loc[measurements["timestamp_local"] >= start]
    elif window == "7 derniers jours":
        start = last_available_hour.normalize() - pd.Timedelta(days=6)
        measurements = measurements.loc[measurements["timestamp_local"] >= start]

    if measurements.empty:
        st.info("Aucune mesure disponible pour la période sélectionnée.")
        return

    first_hour = measurements["timestamp_local"].min()
    last_hour = measurements["timestamp_local"].max()
    missing_weather = int((~measurements["weather_row_present"]).sum())
    unresolved_temperature = int(
        measurements["outdoor_temperature_processed_c"].isna().sum()
    )
    valid_consumption = (
        measurements["consumption_kwh"].notna()
        & np.isfinite(measurements["consumption_kwh"])
        & measurements["consumption_kwh"].gt(0)
    )

    daily_energy = measurements.groupby(
        measurements["timestamp_local"].dt.date
    )["consumption_kwh"].sum(min_count=1)
    peak_day = daily_energy.idxmax() if daily_energy.notna().any() else None
    columns = st.columns(4)
    columns[1].metric(
        "Total période",
        f"{measurements['consumption_kwh'].sum(min_count=1):,.0f} kWh".replace(",", " "),
    )
    columns[0].metric(
        "Moyenne / intervalle",
        f"{measurements['consumption_kwh'].mean():.2f} kWh",
        help="Énergie moyenne par intervalle horaire ; ce n’est pas une puissance en kW.",
    )
    columns[2].metric(
        "Couverture",
        f"{100 * valid_consumption.mean():.1f} %",
    )
    columns[3].metric(
        "Pic journalier",
        f"{daily_energy.loc[peak_day]:.0f} kWh" if peak_day is not None else "—",
    )

    period_caption = (
        f"Période : {first_hour:%d/%m/%Y %H:%M} — {last_hour:%d/%m/%Y %H:%M}"
    )
    if peak_day is not None:
        period_caption += f" · Jour de pointe : {pd.Timestamp(peak_day):%d/%m/%Y}"
    st.caption(period_caption)
    hours_display = f"{len(measurements):,}".replace(",", " ")
    st.caption(
        f"{hours_display} heures · {missing_weather} heures sans ligne météo · "
        f"{int(measurements['temperature_imputed'].sum())} températures imputées · "
        f"{unresolved_temperature} température(s) non résolue(s)"
    )
    st.info(
        "Données historiques préparées localement — cette application n’est pas "
        "encore connectée à un flux temps réel."
    )

    measurements = measurements.set_index("timestamp_local")
    states = states.set_index("timestamp_local")
    states = states.loc[states.index.isin(measurements.index)]

    historical_tab, simulation_tab, quality_tab = st.tabs(
        ["Historique énergétique", "Simulation", "Qualité des données"]
    )

    with historical_tab:
        st.download_button(
            "Télécharger les données de la période (CSV)",
            data=measurements.reset_index().to_csv(index=False).encode("utf-8"),
            file_name=f"{building_id}_{window.lower().replace(' ', '_')}.csv",
            mime="text/csv",
        )
        st.subheader("Énergie journalière")
        daily_energy = measurements["consumption_kwh"].resample("D").sum(min_count=1)
        trend = pd.DataFrame(
            {
                "Énergie journalière": daily_energy,
                "Moyenne mobile 7 jours": daily_energy.rolling(
                    7, min_periods=1
                ).mean(),
            }
        )
        st.line_chart(
            trend,
            y_label="Énergie électrique (kWh/jour)",
            height=340,
        )

        hourly = measurements.assign(
            heure=measurements.index.hour,
            période=np.where(measurements.index.dayofweek >= 5, "Week-end", "Semaine"),
        )
        profile = hourly.groupby(["heure", "période"])["consumption_kwh"].mean().unstack()
        left, right = st.columns(2)
        with left:
            st.subheader("Profil moyen par heure")
            st.bar_chart(profile, y_label="kWh par intervalle")
        with right:
            st.subheader("Consommation et température extérieure")
            scatter = measurements[
                ["outdoor_temperature_processed_c", "consumption_kwh"]
            ].dropna()
            if scatter.empty:
                st.info("Pas assez de données météo pour afficher cette relation.")
            else:
                scatter = scatter.iloc[:: max(1, len(scatter) // 500)]
                st.scatter_chart(
                    scatter,
                    x="outdoor_temperature_processed_c",
                    y="consumption_kwh",
                    x_label="Température extérieure (°C)",
                    y_label="Électricité (kWh par intervalle)",
                    height=340,
                )
            st.caption("Relation descriptive ; elle ne démontre pas un lien causal.")

    with simulation_tab:
        st.info(
            "L’occupation, la température intérieure et l’énergie HVAC ci-dessous "
            "sont simulées ; elles ne sont pas des mesures du bâtiment."
        )
        left, right = st.columns(2)
        with left:
            st.subheader("Températures moyenne par jour")
            temperatures = pd.DataFrame(
                {
                    "Extérieure observée / traitée": measurements[
                        "outdoor_temperature_processed_c"
                    ].resample("D").mean(),
                    "Intérieure simulée": states["indoor_temperature_c"].resample("D").mean(),
                }
            )
            st.line_chart(temperatures, y_label="Température (°C)", height=340)
        with right:
            st.subheader("Occupation simulée")
            daily_occupancy = states["occupancy_rate"].resample("D").mean() * 100
            st.area_chart(
                daily_occupancy,
                y_label="Occupation moyenne (%)",
                height=340,
            )

        st.subheader("Énergie thermique HVAC simulée")
        hvac_energy = states["hvac_thermal_energy_kwh"].resample("D").sum(min_count=1)
        st.bar_chart(
            hvac_energy,
            y_label="kWh thermiques par jour (chauffage + / refroidissement −)",
            height=300,
        )
        st.caption(
            f"Modèle {run['model_version']} · {len(states):,} états · "
            f"température intérieure moyenne {states['indoor_temperature_c'].mean():.1f} °C · "
            f"énergie HVAC thermique signée cumulée {states['hvac_thermal_energy_kwh'].sum():.1f} kWh"
        )
        with st.expander("Paramètres de cette exécution"):
            st.json(run.get("parameters", {}))

    with quality_tab:
        st.subheader("Complétude mensuelle des mesures")
        monthly = pd.DataFrame(quality.get("monthly", []))
        if not monthly.empty:
            monthly["timestamp"] = pd.to_datetime(monthly["timestamp"], errors="raise")
            monthly["complétude (%)"] = (
                monthly["positive_finite"] / monthly["expected"] * 100
            )
            st.bar_chart(
                monthly.set_index("timestamp")[["complétude (%)"]],
                y_label="Heures valides (%)",
                height=320,
            )
            st.dataframe(monthly, width="stretch", hide_index=True)
        st.caption(
            f"Heures électriques manquantes : {quality.get('missing', 0)} · "
            f"zéros : {quality.get('zeros', 0)} · "
            f"négatives : {quality.get('negative', 0)} · "
            f"séquence manquante maximale : {quality.get('longest_missing_hours', 0)} h · "
            f"séquence constante maximale : {quality.get('longest_constant_hours', 0)} h"
        )
        with st.expander("Rapport qualité complet"):
            st.json(data.quality_report)


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
    st.dataframe(recent, width="stretch", hide_index=True)


def main():
    st.sidebar.title("Jumeau énergétique")
    page = st.sidebar.radio(
        "Navigation",
        ["Vue d’ensemble", "Suivi (flux non connecté)"],
    )

    @st.cache_data(ttl=60)
    def cached_dashboard_data(config_path):
        return load_dashboard_data(config_path)

    if st.sidebar.button("Actualiser les exports"):
        cached_dashboard_data.clear()
        st.rerun()

    try:
        data = cached_dashboard_data(ROOT / "config.json")
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
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
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
