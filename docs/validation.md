# Vérifications du dataset final — 14 octobre 2026

Exécution locale sous Python 3.12.7. L’installation complète de `requirements.txt`
a réussi après correction de `packaging==26.3` en `packaging==25.0` : Streamlit
1.51.0 exige une version inférieure à 26.

## Génération sur le dump fourni

Commande : `python -m twin prepare --from-dump data/imports/supabase/donnees.sql`, avec `config.json`.
Les CSV BDG2 complets ne sont pas présents dans ce checkout ; ils n’ont pas été
retéléchargés. Le dump sert de source réelle à cette vérification.

- Une seule table `training_measurements`, 25 colonnes, 17 544 lignes.
- Période : 1er janvier 2016 à 00 h — 31 décembre 2017 à 23 h.
- Consommation conservée : aucune valeur absente, à zéro, négative ou infinie.
- Deux heures sans ligne météo et quatre températures originales absentes.
- Traitement causal, report maximal de trois heures : quatre imputations et
  aucune température non résolue.
- Occupation et états thermiques régénérés avec les hypothèses de démonstration.
- Quatre étiquettes locales DST ambiguës/inexistantes, signalées sans conversion UTC.
- Les 168 premières heures et 676 heures liées aux événements DST sont exclues
  de l’entraînement, mais restent dans la table : 16 700 heures exploitables.
- Partitions : train 8 784 / 8 278 exploitables ; validation 4 344 / 4 175 ;
  test 4 416 / 4 247.
- `anomaly_label` : 17 544 NULL ; aucune annotation normale ou anormale inventée.
- Base SQLite : une seule table utilisateur et `PRAGMA integrity_check = ok`.
- Dry-run REST : une table, 17 544 lignes, 36 lots maximum de 500.

## Vérification PostgreSQL

Un serveur PostgreSQL 16.14 temporaire, accessible uniquement par socket local,
a été créé pour ce contrôle puis arrêté et supprimé.

- Exécution de `sql/schema.sql`, puis de l’export SQL rempli.
- Second import du même fichier : toujours 17 544 lignes, aucun doublon.
- Une seule table dans le schéma public, RLS activé.
- Même nombre d’annotations NULL et d’heures exploitables que SQLite.
- Comparaison des 17 544 lignes entre SQLite et PostgreSQL : consommation,
  décalage d’une heure, moyenne de 168 heures, météo décalée, disponibilité et
  partition identiques (tolérance numérique 1e-10).

## Tests et tableau de bord

Les **30 tests** de `python -m unittest discover -s tests -v` passent. Ils couvrent :

- l’exclusion de la cible et du futur des décalages et moyennes ;
- une modification de la cible/météo future qui laisse les entrées antérieures inchangées ;
- les frontières temporelles, les doublons, les heures absentes et les masques DST ;
- les annotations inconnues, les contraintes SQLite et l’intégrité des fichiers ;
- la parité de préparation CSV/COPY sur un jeu synthétique, l’échappement COPY,
  le rejet de dumps incomplets et l’exclusion des tables auth/storage ;
- la reproductibilité et la stabilité du simulateur, les modes météo et leur causalité ;
- le chargement REST idempotent par lots sur une API simulée et les erreurs sans secrets ;
- la lecture du format unique et le rejet des anciens exports ou métadonnées incohérentes ;
- Streamlit : ouverture, onglet d’entraînement, filtre des sept derniers jours et
  écran des dernières observations, sans exception.

La compilation Python, le contrôle statique des imports et `git diff --check`
réussissent. Le code de sélection du notebook est conservé ; son fichier a été déplacé dans
`notebooks/01_selection_batiment.ipynb` et ses chemins de données adaptés. Les
sorties historiques sont conservées, sans réexécution complète faute de CSV BDG2.

## Chargement réel dans Supabase — 14 octobre 2026

La session CLI Supabase existante a permis de retrouver le projet
`iiubijthccrphoprbiaq` et d’installer le schéma. Le SQL rempli d’environ 4 Mo a été
refusé par l’API de gestion (HTTP 413) ; le chargement a donc utilisé le chargeur
REST existant, en 36 lots de 500 lignes au maximum. La clé serveur a été utilisée
en mémoire, sans création de fichier `.env` ni publication de secret.

- Une seule table active dans `public` : `training_measurements`.
- 17 544 lignes, 25 colonnes et 16 700 lignes techniquement exploitables.
- 17 544 annotations d’anomalie NULL et RLS activé.
- Comparaison paginée des 17 544 lignes et de toutes leurs colonnes à l’export
  local : concordance à tolérance numérique 1e-12 ; écart maximal observé
  4,98e-14 dans la représentation numérique REST.
- Migration `sql/archive_legacy_tables.sql` exécutée après vérification : les
  quatre sources sont conservées dans `archive` avec les mêmes comptages
  (1 bâtiment, 17 544 historiques, 1 exécution, 17 544 états simulés).
- Les relations de clés étrangères des archives restent validées.
- Rapport local : `outputs/deployment/supabase_validation.json`.

## Limites restantes

Aucun modèle prédictif ou détecteur n’est entraîné. Les paramètres thermiques et
l’occupation réelle ne sont pas validés, et la convention opérationnelle des
intervalles compteur reste à confirmer. Les heures exploitables sont un critère
de disponibilité, pas une preuve d’absence d’anomalies.
