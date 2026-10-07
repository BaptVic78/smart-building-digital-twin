# Jumeau numérique énergétique — PFE

Pipeline du bâtiment de bureaux **Hog_office_Miriam**, sur 2016–2017 : données
électriques et météo historiques, simulation de l’occupation et de la température
intérieure, puis ingestion dans Supabase. `test.ipynb` conserve l’analyse ayant
motivé le choix du bâtiment. Le pipeline fonctionne sans Jupyter.

## 1. Installer et récupérer les données

Cloner ce dépôt, se placer à sa racine et utiliser **Python 3.12**.
Les commandes ci-dessous sont prévues pour Bash sous Linux/macOS.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`data/` est exclu de Git : un nouveau contributeur doit récupérer les fichiers
BDG2 depuis le [dépôt source](https://github.com/buds-lab/building-data-genome-project-2)
ou auprès de l’équipe, et les placer ainsi :

```text
data/metadata/metadata.csv
data/meters/raw/electricity.csv
data/weather/weather.csv
```

Utiliser la consommation **raw**, sans la remplacer par la version nettoyée.
[config.json](config.json) centralise les chemins, la période et les paramètres.
Tous les chemins sont relatifs à la racine depuis laquelle les commandes sont lancées.

## 2. Préparer et vérifier les exports

```bash
python -m twin prepare
python -m twin load --dry-run
```

`prepare` lit et valide les sources, joint la météo du site, traite les petits
trous de température et simule l’occupation et la température intérieure.
Il écrit les quatre tables en CSV/JSON et `quality_report.json` dans `outputs/`.
Il n’écrit rien dans Supabase. Une seule exécution suffit ; la relancer remplace
les exports locaux. Ne pas modifier les JSON manuellement : leurs empreintes sont vérifiées.

Le **dry-run** vérifie les exports sans réseau, sans secrets et sans écriture.
Pour produire les graphiques du notebook ou exécuter les tests :

```bash
python -m twin diagnose                    # Optionnel
python -m unittest discover -s tests -v
```

## 3. Installer le schéma Supabase

Dans le projet Supabase de destination, ouvrir **SQL Editor**, coller le contenu
de [sql/schema.sql](sql/schema.sql), puis cliquer sur **Run**. Vérifier que
l’exécution réussit. Cette étape installe les quatre tables ; elle ne charge pas de données.
Si le schéma est déjà installé et correspond au fichier, passer à l’étape suivante.

## 4. Configurer les accès et charger

Créer le fichier local de secrets, seulement s’il n’existe pas encore :

```bash
cp .env.example .env
```

Renseigner les deux valeurs dans `.env` pour le **même projet Supabase**.

> [!TIP]
> **Où trouver ces valeurs ?**
>
> - `SUPABASE_URL` : **Project Settings → Data API → API URL**.
>   Copier uniquement l’URL du projet, avant `/rest/v1` si ce suffixe est présent.
> - `SUPABASE_SERVICE_ROLE_KEY` : **Project Settings → API Keys → Secret Keys → API KEY**.
>   Copier une clé secrète `sb_secret_…` ; la clé legacy `service_role` est aussi acceptée.

```dotenv
SUPABASE_URL=https://TON-PROJET.supabase.co
SUPABASE_SERVICE_ROLE_KEY=TA_CLE_SECRETE
```

Garder la clé privée : `.env` est exclu de Git. Le programme ne lit pas ce fichier
automatiquement ; exporter les variables dans le terminal qui lancera le chargement :

```bash
set -a
source .env
set +a
python -m twin load --batch-size 500
```

Cette commande **écrit réellement dans Supabase**, par lots de 500 lignes maximum,
puis vérifie les comptages. Les upserts permettent de reprendre après une interruption
sans doublons. Dans un nouveau terminal, réactiver `.venv` et recharger `.env`.

## 5. Vérifier le résultat

Les logs doivent indiquer les lignes vérifiées. Dans **Table Editor**, pour la
configuration par défaut et une première ingestion dans une base vide :

| Table | Contenu | Lignes attendues |
|---|---|---:|
| `buildings` | Métadonnées et provenance | 1 |
| `historical_measurements` | Consommation et météo | 17 544 |
| `simulation_runs` | Paramètres et provenance de simulation | 1 |
| `simulated_states` | Occupation et température intérieure simulées | 17 544 |

Des configurations, sources ou versions de code différentes créent d’autres
exécutions, avec 17 544 états par exécution sur la période par défaut.
L’historique du bâtiment est mis à jour par upsert.

## En cas d’erreur

| Erreur | Action |
|---|---|
| Variables Supabase requises | Vérifier `.env`, puis refaire `set -a`, `source .env`, `set +a`. |
| `HTTP 404 / PGRST125` | Retirer tout chemin de `SUPABASE_URL`, puis recharger `.env`. |
| `HTTP 401` ou `403` | Vérifier la clé serveur, le projet et ses permissions. |
| Table introuvable | Vérifier que le SQL a été exécuté dans le projet correspondant à l’URL. |
| Exports absents, incomplets ou modifiés | Relancer `python -m twin prepare`, puis le dry-run. |

Pour signaler un problème, partager la commande et le statut/code d’erreur,
jamais le contenu de `.env`. [Référence des erreurs API Supabase](https://supabase.com/docs/guides/api/rest/postgrest-error-codes).

## Repères pour contribuer

`twin/__main__.py` reçoit les commandes ; `data.py` charge et valide,
`pipeline.py` prépare et diagnostique, `simulation.py` simule, `export.py` exporte
et charge. Le schéma est dans `sql/`, les tests dans `tests/`, les détails dans
[docs/methodologie.md](docs/methodologie.md) et [docs/validation.md](docs/validation.md).
Après une modification de code, lancer les tests et régénérer les exports destinés à l’ingestion.

Les consommations brutes restent en **kWh par intervalle horaire**. Les timestamps
restent locaux (`US/Central`), avec des ambiguïtés DST à résoudre avant un usage
en temps réel. L’imputation météo par défaut (`retrospective`) utilise des valeurs
futures ; le mode `causal` utilise uniquement le passé. L’occupation et la température
intérieure sont **simulées avec des hypothèses de démonstration**, sans validation
sur le bâtiment réel.
