# Méthodologie du dataset horaire

Les commandes et fichiers produits sont décrits dans le [README](../README.md).
Le schéma final est **une table `training_measurements`**, commune à SQLite et
PostgreSQL. Les paramètres et la provenance sont dans `dataset_metadata.json` ;
le rapport qualité et le manifeste sont des fichiers, pas des tables supplémentaires.

## Sources et conservation

Deux chemins de préparation conduisent au même contrat de table :

- Les trois CSV BDG2 de la configuration, sans passer par le notebook.
- Un dump PostgreSQL COPY contenant les anciennes tables `public.buildings` et
  `public.historical_measurements` (`prepare --from-dump`). Le parseur décode les
  cellules COPY sans exécuter de SQL et ignore les autres tables, notamment auth/storage.

Les identifiants et les timestamps sont validés : doublons, valeurs temporelles
invalides et heures non entières bloquent la préparation. La grille fixe conserve
toutes les heures demandées. Une heure électrique absente devient NULL avec
`electricity_row_present=false`. Un relevé présent mais vide reste distingué d’une
ligne absente. La jointure météo gauche conserve exactement la grille électrique.

Les sources restent intactes et leurs empreintes SHA-256 sont conservées dans
les métadonnées. L’import du dump utilise la température **originale**, pas la
valeur précédemment interpolée. Il régénère l’occupation et le modèle RC avec la
configuration courante ; il ne fusionne pas les différentes anciennes exécutions
de simulation. Les hypothèses et empreintes du code sont enregistrées avec un
identifiant de simulation déterministe.

## Unités et temps

La [publication BDG2](https://pmc.ncbi.nlm.nih.gov/articles/PMC7591488/) décrit des
énergies par intervalle horaire, en kWh, avec des horodatages locaux. La convention
exacte début/fin de l’intervalle compteur et sa disponibilité restent à confirmer
avant une prévision opérationnelle.

Miriam porte le fuseau **US/Central**. Les timestamps restent locaux naïfs :
`timestamp without time zone` en PostgreSQL, texte ISO en SQLite. Aucun suffixe Z
ni instant UTC n’est inventé. Le fuseau est conservé dans les métadonnées.

La grille nominale comporte quatre étiquettes DST ambiguës/inexistantes sur
2016–2017. `dst_time_issue` les signale. La consommation brute reste présente ;
ces heures sont écartées des cibles exploitables et masquées avant de construire
les décalages et moyennes. Avec une fenêtre stricte de 168 heures, chaque événement
rend indisponibles son heure et les 168 suivantes. Les quatre fenêtres ne se
recouvrent pas dans ce périmètre. Ce choix conservateur évite de considérer les
artefacts horaires comme des mesures normales d’entraînement. Il ne résout pas
la reconstruction des instants physiques manquants dans la source.

## Température et données manquantes

Par défaut, `weather_mode=causal` reporte la dernière température connue pendant
au plus trois heures. Le drapeau `temperature_imputed` indique une complétion ;
`weather_row_present` distingue absence de ligne et absence de mesure.

Les modes `none` et `retrospective` restent disponibles pour le contexte thermique :
le premier n’impute rien ; le second interpole uniquement les trous bornés d’au
plus `max_gap` heures, avec des valeurs futures. Les valeurs originales non finies
sont traitées comme indisponibles. Un trou non résolu bloque le simulateur RC.

La variable prédictive `outdoor_temperature_lag_1h_c` est **toujours** reconstruite
avec le traitement causal de l’original, puis décalée d’une heure. Elle n’hérite
jamais d’un contexte météo rétrospectif. La météo de l’heure cible est conservée
pour l’analyse et la simulation, mais exclue des entrées du premier modèle.

La consommation brute n’est jamais imputée, écrêtée ou modifiée. Les valeurs
négatives/non finies sont masquées uniquement dans les entrées prédictives. Un zéro
reste admissible, car il peut représenter un arrêt réel ; ce choix diffère du
filtre exploratoire conservateur de sélection du bâtiment.

## Contrat d’entraînement à une heure

La ligne d’étiquette cible **s** porte `y(s) = consumption_kwh`. Les mesures
utilisées comme entrées sont disponibles sous l’hypothèse d’un relevé connu à
**s−1 ou avant**. Les dates calendaires de s sont connues à l’avance.

Les dix entrées initiales, listées dans `feature_columns`, sont :

- `hour`, `dayofweek`, `month`, `is_weekend` ;
- `consumption_lag_1h_kwh`, `consumption_lag_24h_kwh`, `consumption_lag_168h_kwh` ;
- `consumption_mean_24h_kwh`, `consumption_mean_168h_kwh` ;
- `outdoor_temperature_lag_1h_c`.

Une moyenne de longueur n utilise y(s−n), …, y(s−1), avec n valeurs valides
obligatoires : décalage avant fenêtre, sans consommation cible ni futur. Aucun
scaler ou autre transformation apprise n’est ajusté sur la période complète.

`is_training_ready=true` exige une cible finie et non négative, un relevé électrique
présent, une heure cible sans ambiguïté DST et les dix entrées complètes et finies.
Les premières 168 heures et les fenêtres affectées par une valeur manquante ou
un événement DST restent conservées avec `false`. Cet indicateur n’atteste pas
de l’absence de panne ou d’anomalie.

La séparation est définie par l’heure cible : 2016 pour `train`, janvier–juin
2017 pour `validation`, juillet–décembre 2017 pour `test`. Les bornes sont
configurables dans `config.json`. Les observations précédentes peuvent entrer
dans l’historique d’une prévision à une heure, y compris au sein du test, seulement
après leur observation. Cela correspond à une évaluation roulante ; pas à une
prévision de toute la période en une seule émission.

## Annotations et contexte simulé

`anomaly_label` vaut NULL pour toutes les lignes importées : aucune vérité terrain
normal/anormal n’est fournie. Les valeurs futures 0 et 1 sont réservées à des
annotations confirmées. Aucune injection ni classification n’est effectuée par
`prepare`. La qualité et les scores prédictifs devront être évalués séparément
de la détection des scénarios futurs.

`context_is_simulated=true` couvre `occupants`, `indoor_temperature_c` et
`hvac_thermal_energy_kwh`. Ces variables ne figurent pas dans `feature_columns`.
Le taux d’occupation, redondant avec occupants/capacité, est calculé à l’affichage
et n’est pas stocké. Site, usage et surface constants restent dans les métadonnées.

L’occupation dépend uniquement du calendrier, d’un profil de bureaux, d’une
variation journalière et de tirages binomiaux reproductibles. La capacité de 100
personnes est une hypothèse ; aucune consommation cible n’entre dans la simulation.
Les jours fériés et congés ne sont pas modélisés.

Le modèle thermique monozone suit
`C dT/dt = (T_ext − T)/R + Q_personnes + Q_base + Q_HVAC`.
R est en K/kW, C en kWh/K et les apports en kW. La configuration fixe R=2,
C=40, T initiale=21 °C, consignes 20/25 °C, HVAC maximal ±30 kW, apports
0,1 kW/personne et 2 kW de base. Une solution exponentielle exacte est calculée
par sous-pas de cinq minutes. L’état exporté correspond à la fin de l’intervalle
nominal. L’énergie thermique HVAC est positive en chauffage et négative en
refroidissement ; elle ne représente pas la consommation électrique HVAC et
ne s’ajoute pas au compteur global. Pas de COP ni de calibration implicite.

## Exports, intégrité et chargement

Les fichiers sont préparés dans un dossier temporaire puis remplacés ; le manifeste
SHA-256 est écrit en dernier. Il couvre SQLite, SQL, CSV, JSON, métadonnées et
rapport qualité. Une préparation échouée invalide l’ensemble pour le chargeur et
le dashboard. Les empreintes détectent les modifications accidentelles ; elles
ne constituent pas une signature d’authenticité.

SQLite possède exactement une table et la clé `(building_id, timestamp_local)`.
Le SQL PostgreSQL autonome utilise la même définition que `sql/schema.sql`, avec
une transaction et des upserts. Il ne supprime aucune table existante.

Le chargeur REST lit les mêmes lignes vérifiées, utilise une clé serveur, des lots
et des upserts. Il vérifie ensuite les comptages par bâtiment et période. Une
interruption peut être reprise ; les lots REST ne forment pas une transaction
globale. RLS est activé sans politique publique. Les clés et réponses sensibles
ne sont pas journalisées. Le dry-run n’effectue aucune requête et ne lit pas les
secrets.

Le dashboard utilise les exports de cette table unique et les métadonnées. Il
présente les historiques et la simulation, pas un flux temps réel. La suppression
des anciennes tables d’un projet Supabase existant n’est pas incluse dans ce
changement : les données sources sont préservées.
