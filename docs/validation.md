# Vérifications locales du pipeline

Exécution sur les fichiers réels du projet, avec Python 3.12 et les dépendances
figées dans `requirements.txt` (installation isolée dans /tmp).

- Préparation : 17544 heures, 0 heures électriques absentes.
- Consommation : aucune valeur absente, nulle, négative ou infinie; 24 mois complets.
- Plus longue séquence électrique constante : 3 heures.
- Météo : 2 heures sans ligne, 2 lignes avec température absente.
- Températures absentes au total : 4; différence avec le notebook : 0.
- Mode rétrospectif, trou maximal 3 heures : 4 imputations, 0 températures non résolues.
- Fuseau des métadonnées : US/Central; 4 étiquettes locales DST ambiguës/inexistantes, conservées sans conversion UTC.
- Diagnostic exécuté sur 296 bureaux, dont 34 satisfont le filtre strict du notebook.
- États simulés : 17544; température intérieure de 19.959 à 25.031 °C avec les hypothèses de démonstration.
- Dry-run : 1 bâtiment, 17 544 mesures historiques, 1 exécution, 17 544 états; lots de 500.
- 12 tests unitaires/intégration passent, y compris préparation synthétique répétée à l'identique et détection d'exports modifiés.
- Compilation Python et `git diff --check` réussis; notebook inchangé.

Le SQL est préparé mais n'a pas été exécuté sur une base. L'idempotence REST et
les comptages sont testés sur une API simulée. Aucun accès Supabase, aucune
ressource distante ni aucun chargement réel. Restent à confirmer les paramètres
physiques et l'occupation réelle, la sémantique début/fin de l'intervalle compteur
et le traitement temporel opérationnel autour des changements d'heure.

## Contrôle avant commits

La suite actuelle comporte 14 tests, y compris les diagnostics HTTP sans secrets
et les en-têtes des clés serveur modernes/legacy. Les sorties enregistrées du
notebook ont été actualisées par le contributeur ; le code des cellules est identique.
Le chargement réel a été réalisé par le contributeur avec une clé sb_secret_….
L'agent ne lance aucun chargement distant lors de ce contrôle.
