# Jumeau numérique énergétique — PFE

Préparation des données du bâtiment de bureaux **Hog_office_Miriam** sur
2016–2017 et tableau de bord Streamlit. La base finale contient **une seule table
`training_measurements` : une ligne par bâtiment et par heure**, soit 17 544 lignes
et 25 colonnes avec la configuration fournie.

La consommation et la météo proviennent des historiques BDG2. L’occupation, la
température intérieure et l’énergie thermique HVAC sont simulées et signalées
comme telles. Le dataset prépare la prévision à une heure ; aucun modèle
prédictif ni détecteur d’anomalies n’est encore entraîné.

Le plan des dossiers et les fichiers supprimables sont décrits dans
[docs/organisation.md](docs/organisation.md).

## 1. Installer

Depuis la racine du dépôt, utiliser Python 3.12 :

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 2. Générer la base finale

Deux sources sont possibles. Une seule des deux commandes `prepare` est nécessaire.

### Depuis l’export Supabase existant

Placer l’export de données PostgreSQL au format COPY dans
`data/imports/supabase/donnees.sql` (créer le dossier si nécessaire) :

```bash
python -m twin prepare --from-dump data/imports/supabase/donnees.sql
python -m twin load --dry-run
```

Le fichier est lu comme des données : **son SQL n’est jamais exécuté**. Seules les
anciennes tables `public.buildings` et `public.historical_measurements` sont lues.
Les anciennes interpolations rétrospectives sont écartées : la température est
retraitée depuis l’original et le contexte simulé est régénéré selon `config.json`.
Les tables `auth` et `storage` ne sont pas importées. `structure.sql` n’est pas requis.

### Depuis les trois CSV BDG2

Si `data/metadata/metadata.csv`, `data/meters/raw/electricity.csv` et
`data/weather/weather.csv` sont déjà présents :

```bash
python -m twin prepare
python -m twin load --dry-run
```

Sinon, installer [Git LFS](https://git-lfs.com/) et récupérer ces fichiers :

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 \
  https://github.com/buds-lab/building-data-genome-project-2.git ../bdg2-source
git -C ../bdg2-source lfs install --local
git -C ../bdg2-source lfs pull \
  --include="data/metadata/metadata.csv,data/meters/raw/electricity.csv,data/weather/weather.csv" \
  --exclude=""
mkdir -p data/metadata data/meters/raw data/weather
cp -n ../bdg2-source/data/metadata/metadata.csv data/metadata/
cp -n ../bdg2-source/data/meters/raw/electricity.csv data/meters/raw/
cp -n ../bdg2-source/data/weather/weather.csv data/weather/
python -m twin prepare
```

Sauter le clone si `../bdg2-source` existe déjà. Les sources, paramètres, dates de
séparation et dossier de sortie sont configurables dans [config.json](config.json).

## 3. Fichiers produits dans `outputs/dataset/`

| Fichier | Utilisation |
|---|---|
| `training_measurements.sqlite` | Base locale complète, avec une seule table |
| `training_measurements.sql` | Schéma PostgreSQL et données, import transactionnel avec upserts |
| `training_measurements.csv` | Analyse et échange de données |
| `training_measurements.json` | Chargement REST Supabase et lecture du dashboard |
| `dataset_metadata.json` | Liste des entrées du modèle, cible, provenance et paramètres de simulation |
| `quality_report.json` | Comptages, qualité et disponibilité des lignes pour l’entraînement |
| `manifest.json` | Empreintes des six fichiers ; un export modifié ou incomplet est refusé |

`prepare` génère localement ces fichiers et ne modifie pas Supabase. Les données
brutes, exports d’origine, secrets et résultats générés sont exclus de Git ; le
code permet de les reconstruire. Relancer `prepare` remplace les fichiers de
sortie. Un échec invalide le manifeste ; il faut une préparation réussie avant
lecture ou chargement.

## 4. Contenu et utilisation pour l’entraînement

La ligne d’heure cible **s** contient `consumption_kwh = y(s)`. Les entrées mesurées
viennent des étiquettes **s−1 ou antérieures** ; les variables calendaires décrivent s.

| Groupe | Colonnes |
|---|---|
| Identification | `building_id`, `timestamp_local` |
| Mesure cible et météo de contexte | `consumption_kwh`, `outdoor_temperature_processed_c` |
| Contexte simulé | `occupants`, `indoor_temperature_c`, `hvac_thermal_energy_kwh`, `context_is_simulated` |
| Calendrier | `hour`, `dayofweek` (lundi = 0), `month`, `is_weekend` |
| Historique électrique | `consumption_lag_1h_kwh`, `consumption_lag_24h_kwh`, `consumption_lag_168h_kwh` |
| Moyennes du passé | `consumption_mean_24h_kwh`, `consumption_mean_168h_kwh` |
| Météo disponible avant la cible | `outdoor_temperature_lag_1h_c` |
| Qualité et évaluation | `temperature_imputed`, `weather_row_present`, `electricity_row_present`, `dst_time_issue`, `training_split`, `is_training_ready`, `anomaly_label` |

Utiliser exclusivement les **10 colonnes `feature_columns`** du fichier de
métadonnées comme premières entrées. La température extérieure de l’heure cible,
les états simulés, les annotations et la consommation cible sont exclus de cette
liste. La météo prédictive est toujours imputée de façon causale, même si un mode
de contexte rétrospectif est demandé explicitement.

Les moyennes excluent la cible et exigent 24 ou 168 heures passées complètes.
La consommation brute n’est ni imputée, ni écrêtée. Zéro reste une mesure possible ;
une valeur négative/non finie est conservée mais écartée des entrées prédictives.

Les heures DST ambiguës/inexistantes sont signalées sans conversion UTC inventée.
Elles sont exclues des cibles exploitables et des historiques utilisés dans les
variables ; les fenêtres qui les contiennent restent indisponibles. Toutes les
lignes restent dans la table, avec **16 700 lignes exploitables** :

| Partition | Période | Toutes les lignes | `is_training_ready = true` |
|---|---|---:|---:|
| `train` | 2016 | 8 784 | 8 278 |
| `validation` | Janvier–juin 2017 | 4 344 | 4 175 |
| `test` | Juillet–décembre 2017 | 4 416 | 4 247 |

Les 844 lignes restantes correspondent aux 168 premières heures et aux quatre
étiquettes DST avec leurs fenêtres affectées. `is_training_ready` décrit la
disponibilité technique des données, **pas une certification de fonctionnement normal**.
Toutes les annotations `anomaly_label` sont **NULL (inconnues)** ; 0 et 1 sont
réservés à de futures annotations confirmées. Aucune anomalie n’est injectée ici.

Exemple de lecture pour préparer un entraînement :

```python
import json
import sqlite3
import pandas as pd

with open("outputs/dataset/dataset_metadata.json", encoding="utf-8") as source:
    metadata = json.load(source)
with sqlite3.connect("outputs/dataset/training_measurements.sqlite") as connection:
    train = pd.read_sql_query(
        "SELECT * FROM training_measurements "
        "WHERE training_split = 'train' AND is_training_ready = 1 "
        "ORDER BY timestamp_local", connection,
    )
X_train = train[metadata["feature_columns"]]
y_train = train[metadata["target_column"]]
```

Le pas est une heure **nominale locale US/Central**. La disponibilité effective
du relevé précédent et la convention début/fin de l’intervalle compteur restent
à confirmer avant un branchement temps réel.

## 5. Ouvrir le tableau de bord

```bash
python -m streamlit run app.py
```

Ouvrir [http://localhost:8501](http://localhost:8501). Le dashboard lit la table
unique locale : historique, contexte simulé, qualité et données d’entraînement.
Le filtre de période et le téléchargement CSV restent disponibles. Après une
nouvelle préparation, utiliser « Actualiser les exports ».

L’écran de suivi montre les derniers historiques exportés ; aucun flux temps
réel n’est connecté. Les températures intérieures, l’occupation et le HVAC sont
des hypothèses de démonstration non calibrées sur le bâtiment réel.

## 6. Charger la table finale dans Supabase

Deux possibilités :

- Importer `outputs/dataset/training_measurements.sql` avec un client PostgreSQL. Le fichier
  contient le schéma et toutes les données dans une transaction.
- Installer [sql/schema.sql](sql/schema.sql) dans SQL Editor, puis utiliser le
  chargeur REST ci-dessous.

Ces deux chemins créent uniquement `public.training_measurements`. Ils ne
suppriment aucune ancienne table. Sur un projet déjà alimenté, les quatre tables
historiques restent des sources ; leur suppression éventuelle est une opération
de migration séparée. Sur une base vide, le schéma applicatif final comporte une table.

Pour le chargeur REST, créer `.env` à partir de `.env.example` si nécessaire, puis
renseigner l’URL HTTPS du projet et une clé serveur `sb_secret_…` ou legacy
`service_role`. Ne jamais committer ce fichier.

```bash
cp -n .env.example .env
# Compléter .env localement, puis :
set -a
source .env
set +a
python -m twin load --dry-run
python -m twin load --batch-size 500
```

Le dry-run valide les fichiers sans réseau ni secrets. Le chargement réel
effectue des upserts sur `(building_id, timestamp_local)` et vérifie les
comptages du périmètre. Il peut être relancé sans doublons. RLS est activé sans
politique publique ; la clé serveur reste côté serveur.

## 7. Vérifier et contribuer

```bash
python -m unittest discover -s tests -v
python -m compileall -q twin dashboard app.py tests
git diff --check
```

[Le notebook de sélection](notebooks/01_selection_batiment.ipynb) conserve la
justification du choix de Miriam et résout ses chemins depuis la racine du dépôt. `python -m twin diagnose`
reste disponible avec les CSV BDG2 complets et écrit dans `outputs/diagnostics/`. Les tests n’exigent ni les CSV
complets, ni Supabase : ils utilisent des jeux synthétiques et une API simulée.

Le contrat de table et les variables sont dans `twin/dataset.py`, l’import COPY
dans `twin/dump.py`, la préparation dans `twin/pipeline.py` et les exports dans
`twin/export.py`. La méthode et les vérifications sont détaillées dans
[docs/methodologie.md](docs/methodologie.md) et [docs/validation.md](docs/validation.md).
