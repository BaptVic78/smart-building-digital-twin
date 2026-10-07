# Méthodologie du pipeline

Les commandes sont dans le [README](../README.md). Ce document détaille les
choix de préparation et les hypothèses de simulation.

## Données, unités et temps

Sources : les trois chemins de la configuration. Les empreintes SHA-256 sont
exportées avec la provenance. Les identifiants bâtiment doivent être uniques;
les timestamps électriques et les couples site–timestamp météo sont validés sur
les fichiers complets. Invalides, doublons et heures non entières provoquent une
erreur. La grille fixe 2016–2017 comporte **17 544 heures**; une heure absente du
fichier électrique est matérialisée par NULL et `electricity_row_present=false`.
Aucune ligne électrique de cette période n'est supprimée. Jointure météo gauche
`one_to_one`, après filtre du site. `weather_row_present` distingue absence de
ligne et absence de température dans une ligne existante.

La [publication BDG2](https://pmc.ncbi.nlm.nih.gov/articles/PMC7591488/) décrit les
horodatages locaux et l'énergie cumulée par intervalle horaire, en kWh. Une valeur
horaire n'est pas une mesure instantanée de puissance en kW. Le début ou la fin
exacte de l'intervalle et la disponibilité effective de la mesure restent à
confirmer avant une prévision opérationnelle.

Miriam porte le fuseau **US/Central**. Les timestamps restent des étiquettes
locales naïves : `timestamp without time zone` en PostgreSQL, avec le fuseau dans
`buildings`. Aucun suffixe Z ni conversion UTC inventée. La grille contient les
heures locales nominales, y compris celles inexistantes au printemps, et une
seule étiquette pour les heures ambiguës en automne. Le rapport compte ces
étiquettes par localisation diagnostique; il ne modifie pas les données. On ne
peut pas retrouver les instants physiques et les folds DST à partir de cette
grille seule. Le pas thermique est une heure nominale de démonstration.

Le rapport recalcule les quatre températures manquantes attendues du notebook
et signale la différence éventuelle. `airTemperature` est conservée dans
`outdoor_temperature_original_c`; la version traitée et le drapeau d'imputation
sont distincts. Les autres variables météo restent brutes dans `weather_original`
(JSONB); aucune imputation de ces variables très incomplètes.

Modes configurables (`max_gap`, en heures) :

- `none` : aucune imputation.
- `retrospective` : interpolation linéaire seulement dans des trous entièrement
  bornés de longueur au plus `max_gap`, sans extrapolation aux extrémités.
  Utilise des valeurs futures; réservé à un historique et à appliquer séparément
  dans les partitions d'entraînement/évaluation.
- `causal` : dernière température connue pendant au plus `max_gap` heures;
  aucune valeur future. Une longue interruption reste manquante après ce délai.

Les valeurs non finies de température deviennent indisponibles pour le
traitement, tout en restant dans la colonne originale. Si des trous demeurent,
la simulation refuse de poursuivre. La consommation n'est jamais imputée.

## Hypothèses synthétiques

L'occupation et la température intérieure sont **simulées**, sans calibration ni
validation sur le bâtiment réel. La capacité de démonstration (100 personnes)
est un paramètre et non une métadonnée observée. L'occupation utilise uniquement
le calendrier, une variation journalière uniforme, un profil progressif
(arrivées, pause déjeuner, départs) et un faible profil de week-end. Un tirage
binomial donne un entier entre zéro et la capacité; son ratio est entre 0 et 1.
Pas de jours fériés/congés dans cette première hypothèse. La graine rend les
résultats reproductibles; aucune consommation cible n'entre dans cette génération.

Le modèle monozone RC est :
`C dT/dt = (T_ext - T)/R + Q_personnes + Q_base + Q_HVAC`.
R est en K/kW, C en kWh/K, les apports en kW et le temps en heures.
Par défaut : R=2, C=40, T initiale=21 °C, consignes 20/25 °C,
HVAC thermique maximal ±30 kW, apports 0,1 kW/personne et 2 kW de base.
Les échanges avec l'extérieur et les apports sont constants par heure; le
thermostat est réévalué toutes les cinq minutes. Chaque sous-pas utilise la
solution exponentielle exacte RC, sans Euler explicite instable et sans bornage
artificiel de température. L'état exporté correspond à la **fin** de l'intervalle
nominal étiqueté. L'énergie thermique HVAC signée est positive en chauffage et
négative en refroidissement. Ce n'est ni la consommation électrique HVAC réelle,
ni une désagrégation du compteur global. Aucun COP, solaire ou modèle multizone
n'est supposé implicitement.

## Schéma et chargement Supabase

`sql/schema.sql` définit sans extension :

- `buildings` : métadonnées et provenance.
- `historical_measurements` : énergie brute et météo originale/traitée;
  clé `(building_id, timestamp_local)`.
- `simulation_runs` : paramètres, sources, versions bibliothèques et empreintes
  du code, UUID déterministe; clé `run_id`.
- `simulated_states` : occupation, température intérieure et énergie thermique
  HVAC; clé `(run_id, timestamp_local)`.

Les clés étrangères imposent l'ordre de chargement. Les contraintes protègent
les états et la grille sans interdire les valeurs électriques brutes atypiques.
Les index temporels complètent les clés composites. RLS est activé sans politique
client publique; le chargeur utilise une clé serveur sb_secret_… ou une clé legacy service_role.

Le chargeur distinct utilise l'API REST PostgreSQL de Supabase, des lots et
`on_conflict`/upserts. Une interruption se reprend avec la même commande sans
doublons. Les comptages exacts sont vérifiés par bâtiment/période ou exécution;
une différence fait échouer la commande. Les valeurs absentes deviennent NULL;
les infinis float8 sont transmis comme chaînes PostgreSQL explicites, jamais
comme JSON invalide. Les logs ne contiennent ni clés ni réponses sensibles.
Le dry-run valide les exports et affiche les nombres sans lire les secrets ni
faire de requête. Les fichiers JSON sont l'autorité pour le chargeur; les CSV
servent à l'analyse locale.

L'historique représente la version courante de la préparation : un nouveau
traitement remplace les colonnes météo traitées par upsert. Les exécutions gardent
leurs paramètres et empreintes, et les états de chaque run restent séparés.
Un changement de configuration/code/source crée un nouveau run déterministe;
relancer à l'identique conserve le même run. Un manifeste SHA-256 empêche le chargement d’exports incomplets ou modifiés.
Une préparation échouée invalide ce manifeste jusqu’à la prochaine réussite. Les lots ne constituent pas une
transaction globale; les clés permettent la reprise.

Aucune ressource distante n'a été créée et aucun chargement réel n'a été effectué
pendant le développement. La validation SQL et REST sur votre Supabase reste à
faire avec vos identifiants. Les tests couvrent la jointure, les doublons, les
modes météo, la causalité, l'occupation reproductible, la solution thermique
analytique et sa stabilité, NULL/infinis et l'idempotence du chargeur avec une API
simulée. Les modèles prédictifs, anomalies, dashboard et streaming restent hors
périmètre.

Les anciennes dépendances du notebook sont archivées dans
[requirements-notebook.txt](requirements-notebook.txt). Elles ne sont pas
nécessaires pour exécuter le pipeline.
