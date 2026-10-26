# Notebooks

| Notebook | Rôle | Entrées | Sorties |
|---|---|---|---|
| `01_selection_batiment.ipynb` | Comparaison des bureaux et choix de Hog_office_Miriam | CSV BDG2 dans `data/` | Analyses exploratoires |
| `03_modeles_reference.ipynb` | Ridge, XGBoost, résidus et calibration des alertes | `outputs/dataset/measurements.csv` | `outputs/models/` |

Ouvrir les notebooks depuis la racine ou depuis `notebooks/`.
La numérotation existante est conservée ; aucun notebook 02 n'est nécessaire.

La sélection demande les CSV BDG2 complets ; l'export SQL ne suffit pas à comparer
tous les bâtiments. Les sorties historiques de sélection sont conservées.

État de la détection : étapes 1 à 3 réalisées (modèle figé, résidus de validation,
seuils à 1 % et 99 %, deux dépassements consécutifs du même côté).
Prochaine étape : rejeu chronologique du test. Les alertes restent des écarts
potentiels, sans annotations confirmant des anomalies réelles.

Les calculs d'entraînement, d'évaluation et de calibration sont définis dans
`twin/training.py`. Le notebook les appelle et conserve les graphiques et les
explications. Exécution autonome : `python -m twin.training` ; ajouter
`--evaluate-test` pour afficher les métriques finales sur test.
