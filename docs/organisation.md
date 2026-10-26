# Organisation du dépôt

Rangement effectué le 14 octobre 2026. La racine conserve les points d’entrée ;
le code, les sources, la documentation et les résultats ont leurs dossiers dédiés.

```text
smart-building-digital-twin/
├── README.md                         démarrage et commandes
├── app.py                            point d’entrée Streamlit
├── config.json                       sources et paramètres
├── requirements.txt                  dépendances actives
├── .env.example                      modèle de secrets sans identifiants
├── twin/                             préparation, simulation, table finale et exports
├── dashboard/                        lecture des données pour l’interface
├── tests/                            vérifications automatisées
├── notebooks/
│   ├── 03_modeles_reference.ipynb     modèles et calibration des alertes
│   └── 01_selection_batiment.ipynb    exploration et justification du choix de Miriam
├── sql/
│   ├── schema.sql                    schéma PostgreSQL de la table finale
│   └── archive_legacy_tables.sql     migration réversible des quatre tables sources
├── docs/
│   ├── organisation.md               ce plan et les possibilités de nettoyage
│   ├── contexte.md                   cadrage, décisions et historique du projet
│   ├── methodologie.md               contrat des données et hypothèses
│   ├── validation.md                 résultats des vérifications
│   ├── references/                   documents de référence locaux
│   └── archives/                     anciens documents et dépendances historiques
├── data/                             sources locales, exclues de Git
│   ├── imports/supabase/
│   │   ├── donnees.sql               export source utilisé pour régénérer la base
│   │   └── structure.sql             ancien schéma, conservé pour référence
│   ├── metadata/                     métadonnées BDG2 si téléchargées
│   ├── meters/raw/                   électricité BDG2 si téléchargée
│   └── weather/                      météo BDG2 si téléchargée
└── outputs/                          résultats générés, exclus de Git
    ├── dataset/                      base finale, exports, métadonnées et manifeste
    ├── selection_batiment/                  graphiques et diagnostics si exécutés
    ├── deployment/                   rapport de vérification du chargement distant
    └── archives/                     anciennes métadonnées de génération
```

Les dossiers BDG2 et diagnostics sont créés uniquement quand les données ou les
commandes correspondantes sont disponibles. Le portfolio PDF dans
`docs/references/` reste local ; il n’est pas publié sur GitHub.

## Fichiers de travail à conserver

- `twin/`, `dashboard/`, `app.py`, `config.json`, `requirements.txt`, `sql/` et `tests/`
  constituent l’application et ses vérifications.
- `notebooks/01_selection_batiment.ipynb` explique le choix du bâtiment. Ce n’est
  pas un test automatisé, malgré son ancien nom `test.ipynb`.
- `data/imports/supabase/donnees.sql` est actuellement la source complète disponible
  localement pour reconstruire les résultats ; les CSV BDG2 ne sont pas téléchargés.
- `outputs/dataset/` est l’ensemble actuellement utilisé par le dashboard et le
  chargeur. Ses fichiers sont couverts ensemble par `manifest.json` : un fichier
  retiré isolément rend l’ensemble incomplet.
- `.venv/` contient l’environnement Python utilisé pour lancer le projet ;
  `.git/` contient l’historique et la connexion au dépôt distant.

## Nettoyage effectué et fichiers facultatifs

| Élément | État et utilité |
|---|---|
| Quatre exports portant ` 2` identiques aux fichiers officiels | Supprimés après comparaison SHA-256 : CSV, JSON, SQLite et rapport qualité |
| Deux versions antérieures de métadonnées/manifeste | Rangées dans `outputs/archives/provenance-2026-10-14/` ; facultatives |
| `__pycache__/`, `.ruff_cache/`, `.pytest_cache/`, `.ipynb_checkpoints/`, `.DS_Store` | Caches ou métadonnées locales ; supprimables et exclus de Git |
| `docs/archives/requirements-notebook-original.txt` | Ancien état de dépendances, non utilisé ; supprimable si l’historique n’est plus souhaité |
| `data/imports/supabase/structure.sql` | Ancien schéma à quatre tables ; facultatif pour la nouvelle préparation |
| `outputs/selection_batiment/` | Graphiques et diagnostics régénérables, si le dossier existe |
| `outputs/dataset/` complet | Régénérable depuis les sources ; utilisé actuellement par l’application |
| `.venv/` | Recréable depuis `requirements.txt` ; conserver pour continuer à lancer le projet immédiatement |

Le portfolio, les données brutes, les sorties utiles du notebook et l’historique
Git ont été conservés. Les deux fichiers d’ancienne provenance archivés ne forment
pas un dataset autonome : ils servent uniquement de trace historique.

## Régénérer les résultats

Depuis la racine, avec l’environnement activé :

```bash
python -m twin prepare --from-dump data/imports/supabase/donnees.sql
python -m twin load --dry-run
```

Les résultats sont écrits dans `outputs/dataset/`. Les paramètres `output` et
`diagnostics_output` de `config.json` définissent les destinations. Les sources
et documents de référence restent dans leurs dossiers respectifs.

## Rangement du 26 octobre 2026

Le travail actif est `notebooks/03_modeles_reference.ipynb`, avec
`outputs/dataset/` en entrée et `outputs/models/` pour le modèle et les règles.
Le code applicatif reste dans `twin/`, `dashboard/` et `app.py`.

Les anciennes tables placées directement dans `outputs/` et les anciennes
baselines ont été déplacées dans `outputs/archives/avant-modelisation/`.
Les diagnostics exploratoires sont regroupés dans `outputs/selection_batiment/`,
avec les CSV par bâtiment dans `mensuel/`. La configuration des futurs diagnostics
pointe vers ce nouveau dossier. Aucun fichier de données n'a été supprimé.

Les chemins du dataset actif et du modèle restent identiques. Les fichiers
`alert_rule.json` et `xgboost_forecast.joblib` sont des sorties générées locales,
exclues de Git. Le plan des notebooks est décrit dans `notebooks/README.md`.

## État après suppression des sorties facultatives

Les anciennes sorties dans `outputs/archives/`, les diagnostics de sélection
et les caches locaux ont été supprimés après le rangement ci-dessus.
`outputs/` conserve le dataset complet, les modèles et son README local.
Ces suppressions ne retirent aucun module de `twin/`.
La commande `diagnose` recrée les diagnostics si nécessaire ; elle écrit désormais
les CSV mensuels dans `outputs/selection_batiment/mensuel/`.

## Extraction de l'entraînement

`twin/training.py` centralise la préparation des variables, Ridge/XGBoost,
l'évaluation, les résidus et la calibration. Le notebook 03 appelle ces fonctions
et conserve la visualisation. L'entraînement autonome s'exécute avec
`python -m twin.training` ; l'évaluation sur test est facultative
(`--evaluate-test`). Le rejeu sera traité séparément.
