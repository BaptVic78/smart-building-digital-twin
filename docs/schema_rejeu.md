# Mesures et suivi des rejeux

## État de cette évolution

Le code et les exports locaux utilisent désormais `measurements` (format 3).
Le 26 octobre 2026, l'utilisateur a exécuté le script ponctuel d'application dans
le SQL Editor et signalé la présence des quatre tables. Le renommage n'est pas
à refaire sur ce projet. Les contrôles SQL de la section 6 du README permettent
de vérifier les effectifs et RLS.

`sql/schema.sql` est la référence unique du schéma complet, à modifier directement.
Pour une autre base utilisant encore l'ancien nom, vérifier d'abord que seule
`training_measurements` existe,
puis effectuer le renommage et créer les tables de suivi dans une transaction :

```sql
begin;
alter table public.training_measurements rename to measurements;
-- Exécuter ici le contenu de schema.sql, sans ses lignes begin/commit.
commit;
```

Ne pas effectuer le renommage si les deux tables existent : il faut alors
réconcilier leur contenu. Si seule `measurements` existe, exécuter directement
`schema.sql`. Une installation neuve utilise également `schema.sql`.
Le renommage conserve les données et les index existants ; le schéma actif crée
ses index nommés `measurements_time_idx` et `measurements_split_idx`.
Pour éviter les index équivalents en double sur la base existante, renommer aussi
`training_time_idx` en `measurements_time_idx` et `training_split_idx` en
`measurements_split_idx` avant d'exécuter le schéma.

- Les exports dataset SQL/SQLite ne contiennent que `measurements` ; les tables
  de suivi restent indépendantes des exports et de la préparation des données.

## Contrat des tables

`measurements` conserve les 25 colonnes existantes et la clé
`(building_id, timestamp_local)`. Les trois retards de contexte sont toujours
calculés dans `prepare_data`. Les partitions et les paramètres du modèle ne
changent pas. Le schéma conserve toutes les mesures, même non exploitables.

`replay_runs` identifie une expérience sur un bâtiment, sa période et son curseur
`last_processed_at`. Il conserve la version et l'empreinte du modèle, l'empreinte
du dataset, l'ordre des variables et les règles d'alerte. Le curseur désigne la
dernière heure traitée, y compris lorsqu'aucune prédiction n'était possible.

`predictions` est identifiée par `(run_id, building_id, timestamp_local)` et
référence le rejeu et la mesure cible. Sa création précède la révélation de la
mesure : `actual_kwh`, `residual_kwh` et `evaluated_at` sont alors NULL.
Ces trois champs sont renseignés ensemble après réception ; le résidu doit être
égal à réel moins prédit. Une mesure peut ne correspondre à aucune prédiction.

`alerts` référence une prédiction et conserve le sens du dépassement, le seuil,
le contexte et les hypothèses. Une ligne correspond à une heure où la règle
persistante est active, au maximum une par prédiction. Ce n'est pas encore un
regroupement en épisodes. Les hypothèses ne confirment pas une panne.

La base impose les clés, types, valeurs finies et la cohérence du résidu.
Le futur code de rejeu devra contrôler la période, la disponibilité causale des
variables et l'application effective de la règle persistante avant toute alerte.
La présence de l'historique complet en base ne doit pas permettre au dashboard
de révéler des mesures postérieures au curseur du rejeu.

## Historique insuffisant et continuité horaire

Les 168 premières heures restent en base pour constituer l'historique ; elles
n'ont pas toutes les variables requises pour entraîner ou prédire. La première
cible exploitable du dataset actuel est le 8 janvier 2016 à 00 h.
`is_training_ready` désigne la disponibilité technique, pas la normalité.

Un rejeu débutant en juillet peut utiliser les mesures de juin : elles sont
antérieures à la cible. Il charge l'historique requis avant sa première cible,
puis avance chronologiquement. Une absence, un changement d'heure problématique
ou une variable requise indisponible suspend la prédiction ; cette heure doit
aussi interrompre la persistance des dépassements. Les horodatages du dataset
restent des heures locales US/Central sans conversion UTC inventée ; les dates
d'exécution utilisent `timestamptz`.

## Accès

RLS est activé sur les quatre tables. Aucune politique publique n'est ajoutée.
Le rôle serveur `service_role` dispose de SELECT/INSERT/UPDATE. Sa clé reste
strictement côté Python serveur. Aucun envoi distant n'a été fait pendant les tests.

## Vérifications locales

Sur PostgreSQL 16 temporaire : installation neuve répétée, migration répétée,
égalité des empreintes des lignes avant/après renommage, refus si les deux noms
existent, clés étrangères, doublons, évaluation partielle, valeurs NaN, alertes
orphelines et RLS. Le jeu de test SQL conserve ses 168 heures d'amorçage sans
prédiction. La suite Python vérifie également la synchronisation de `schema.sql`
avec le générateur et la lecture des exports.
