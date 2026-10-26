"""Entraînement et calibration : python -m twin.training.

Les calculs sont ceux du notebook 03, avec les mêmes partitions et paramètres.
Les fonctions retournent des dictionnaires pour garder les résultats accessibles.
"""

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]


def prepare_data(dataset_path):
    """Lire les données et construire les retards avant le filtrage."""
    df = pd.read_csv(dataset_path)
    df["timestamp_local"] = pd.to_datetime(df["timestamp_local"])
    df = df.sort_values("timestamp_local").reset_index(drop=True)
    previous_time = df["timestamp_local"].shift(1)
    previous_dst_issue = df["dst_time_issue"].shift(1).astype("boolean").fillna(True)
    valid_previous_hour = (
        df["timestamp_local"].sub(previous_time).eq(pd.Timedelta(hours=1))
        & ~df["dst_time_issue"].astype(bool)
        & ~previous_dst_issue
    )

    context_lags = {
        "occupants": "occupants_lag_1h",
        "indoor_temperature_c": "indoor_temperature_lag_1h_c",
        "hvac_thermal_energy_kwh": "hvac_thermal_energy_lag_1h_kwh",
    }
    for column, lag_column in context_lags.items():
        df[lag_column] = df[column].shift(1).where(valid_previous_hour)
    df = df.loc[df["is_training_ready"].eq(True)].copy()
    training_features = [
        'hour', 'dayofweek','month', "is_weekend", 
        "consumption_lag_1h_kwh", 
        "consumption_lag_24h_kwh",
        "consumption_lag_168h_kwh",
        "consumption_mean_24h_kwh",
        "consumption_mean_168h_kwh",
        "outdoor_temperature_lag_1h_c",
        "occupants_lag_1h",
        "indoor_temperature_lag_1h_c",
        "hvac_thermal_energy_lag_1h_kwh",
    ]
    # Même ensemble d'heures pour les comparaisons avec et sans contexte simulé.
    model_df = df.dropna(subset=training_features + ["consumption_kwh"]).copy()
    base_features = [f for f in training_features if f not in context_lags.values()]

    X_train = model_df.loc[model_df["training_split"] == "train", training_features].copy()
    X_val = model_df.loc[model_df["training_split"] == "validation", training_features].copy()
    X_test = model_df.loc[model_df["training_split"] == "test", training_features].copy()
    y_train = model_df.loc[X_train.index, "consumption_kwh"].copy()
    y_val = model_df.loc[X_val.index, "consumption_kwh"].copy()
    y_test = model_df.loc[X_test.index, "consumption_kwh"].copy()
    return {'model_df': model_df, 'training_features': training_features, 'base_features': base_features, 'X_train': X_train, 'X_val': X_val, 'X_test': X_test, 'y_train': y_train, 'y_val': y_val, 'y_test': y_test}


def train_models(data):
    """Entraîner sur train et comparer uniquement sur validation."""
    X_train, y_train = data["X_train"], data["y_train"]
    X_val, y_val = data["X_val"], data["y_val"]
    ridge_model = make_pipeline(
        StandardScaler(),
        Ridge(alpha=1.0),
    )
    ridge_model.fit(X_train, y_train)
    ridge_val_pred = ridge_model.predict(X_val)
    # Configuration retenue et figée pour la suite de la détection.
    xgb_model = XGBRegressor(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="reg:squarederror",
        tree_method="hist",
        random_state=42,
        n_jobs=2,
    )
    xgb_model.fit(X_train, y_train)
    xgb_val_pred = xgb_model.predict(X_val)
    validation_predictions = {
        "Persistance (t-1)": X_val["consumption_lag_1h_kwh"],
        "Ridge": ridge_val_pred,
        "XGBoost": xgb_val_pred,
    }

    validation_results = pd.DataFrame([
        {
            "modèle": name,
            "MAE (kWh)": mean_absolute_error(y_val, prediction),
            "RMSE (kWh)": root_mean_squared_error(y_val, prediction),
        }
        for name, prediction in validation_predictions.items()
    ]).set_index("modèle").sort_values("MAE (kWh)")
    return {'ridge_model': ridge_model, 'xgb_model': xgb_model, 'validation_results': validation_results}


def evaluate_test(data, trained):
    """Évaluer le modèle choisi sur validation, sans ajustement sur test."""
    X_test, y_test = data["X_test"], data["y_test"]
    ridge_model, xgb_model = trained["ridge_model"], trained["xgb_model"]
    validation_results = trained["validation_results"]
    models = {"Ridge": ridge_model, "XGBoost": xgb_model}
    best_model_name = validation_results.loc[list(models), "MAE (kWh)"].idxmin()
    best_model = models[best_model_name]
    test_pred = best_model.predict(X_test)

    test_results = pd.DataFrame([
        {
            "modèle": name,
            "MAE (kWh)": mean_absolute_error(y_test, prediction),
            "RMSE (kWh)": root_mean_squared_error(y_test, prediction),
        }
        for name, prediction in {
            "Persistance (t-1)": X_test["consumption_lag_1h_kwh"],
            best_model_name: test_pred,
        }.items()
    ]).set_index("modèle")
    return test_results


def calculate_residuals(data, forecast_model):
    """Calculer les résidus et leurs statistiques sur validation."""
    model_df = data["model_df"]
    X_val, y_val = data["X_val"], data["y_val"]
    forecast_features = data["training_features"]
    validation_residuals = model_df.loc[X_val.index, ["timestamp_local"]].copy()
    validation_residuals["actual_kwh"] = y_val
    validation_residuals["predicted_kwh"] = forecast_model.predict(X_val[forecast_features])
    validation_residuals["residual_kwh"] = (
        validation_residuals["actual_kwh"] - validation_residuals["predicted_kwh"]
    )
    validation_residuals = validation_residuals.set_index("timestamp_local").sort_index()

    # Statistiques descriptives, sans choix de seuil.
    residual_summary = validation_residuals["residual_kwh"].describe(
        percentiles=[0.01, 0.05, 0.5, 0.95, 0.99]
    )
    return (validation_residuals, residual_summary)


def calibrate_alerts(validation_residuals):
    """Calibrer les deux seuils et comparer les persistances de 1 h et 2 h."""
    lower_quantile = 0.01
    upper_quantile = 0.99
    lower_threshold_kwh = float(validation_residuals["residual_kwh"].quantile(lower_quantile))
    upper_threshold_kwh = float(validation_residuals["residual_kwh"].quantile(upper_quantile))

    # Grille horaire complète : les heures absentes cassent les séquences.
    validation_alerts = validation_residuals.asfreq("h").copy()
    validation_alerts["under_1h"] = validation_alerts["residual_kwh"] < lower_threshold_kwh
    validation_alerts["over_1h"] = validation_alerts["residual_kwh"] > upper_threshold_kwh

    alert_comparison = []
    for direction in ["under", "over"]:
        exceeded = validation_alerts[f"{direction}_1h"]
        validation_alerts[f"{direction}_2h"] = (
            exceeded & exceeded.shift(1, fill_value=False)
        )
        for duration in [1, 2]:
            column = f"{direction}_{duration}h"
            active = validation_alerts[column]
            starts = active & ~active.shift(1, fill_value=False)
            alert_comparison.append({
                "règle": column,
                "heures en alerte": int(active.sum()),
                "épisodes": int(starts.sum()),
                "% des heures observées": 100 * active.sum() / len(validation_residuals),
            })

    validation_alerts["alert_type"] = ""
    validation_alerts.loc[validation_alerts["under_2h"], "alert_type"] = "Sous-consommation potentielle"
    validation_alerts.loc[validation_alerts["over_2h"], "alert_type"] = "Surconsommation potentielle"

    alert_comparison = pd.DataFrame(alert_comparison).set_index("règle")
    alert_rule = {
        "residual_definition": "actual_kwh - predicted_kwh",
        "rules": {
            "underconsumption": {
                "label": "Sous-consommation potentielle",
                "comparison": "<",
                "threshold_kwh": lower_threshold_kwh,
                "quantile": lower_quantile,
            },
            "overconsumption": {
                "label": "Surconsommation potentielle",
                "comparison": ">",
                "threshold_kwh": upper_threshold_kwh,
                "quantile": upper_quantile,
            },
        },
        "consecutive_same_direction": True,
        "calibration_split": "validation",
        "calibration_start": str(validation_residuals.index.min()),
        "calibration_end": str(validation_residuals.index.max()),
        "calibration_observations": len(validation_residuals),
        "consecutive_hours": 2,
        "missing_hour_breaks_sequence": True,
        "forecast_model_file": "xgboost_forecast.joblib",
    }
    return (validation_alerts, alert_comparison, alert_rule)


def save_artifacts(data, forecast_model, alert_rule, output):
    """Sauvegarder le XGBoost figé et les règles ; remplace les fichiers existants."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    train_times = data["model_df"].loc[data["X_train"].index, "timestamp_local"]
    model_path = output / "xgboost_forecast.joblib"
    joblib.dump({
        "model": forecast_model,
        "feature_columns": data["training_features"].copy(),
        "target_column": "consumption_kwh",
        "training_split": "train",
        "training_start": str(train_times.min()),
        "training_end": str(train_times.max()),
        "context_is_simulated": True,
    }, model_path)
    rule_path = output / "alert_rule.json"
    rule_path.write_text(json.dumps(alert_rule, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return (model_path, rule_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "outputs/dataset/training_measurements.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/models")
    parser.add_argument("--evaluate-test", action="store_true", help="Afficher aussi l'évaluation finale, sans réglage sur test")
    args = parser.parse_args()

    data = prepare_data(args.dataset)
    trained = train_models(data)
    print("Comparaison sur validation :")
    print(trained["validation_results"])
    residuals, summary = calculate_residuals(data, trained["xgb_model"])
    alerts, comparison, rule = calibrate_alerts(residuals)
    print("Résidus de validation :")
    print(summary)
    print("Alertes de validation :")
    print(comparison)
    paths = save_artifacts(data, trained["xgb_model"], rule, args.output)
    for path in paths:
        print(f"Sauvegarde : {path}")
    if args.evaluate_test:
        print("Évaluation finale :")
        print(evaluate_test(data, trained))


if __name__ == "__main__":
    main()
