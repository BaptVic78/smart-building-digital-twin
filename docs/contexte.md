# Contexte du projet PFE

Dernière mise à jour : 2 octobre 2026.

Ce fichier permet à un agent de reprendre le projet sans accéder aux conversations précédentes. Il décrit l'état connu à cette date. Les instructions explicites de l'utilisateur et les fichiers actuels du dépôt priment sur ce résumé. Une proposition n'est pas une décision validée et une sortie de notebook n'est pas une vérification indépendante des données.

## 1. Définition du projet

**Titre : Digital Twin augmenté par l’IA pour la résilience énergétique des bâtiments intelligents.**

Projet de fin d'études à l'ECE Paris, année universitaire 2026–2027. Le prototype s'adresse aux gestionnaires et exploitants de bâtiments tertiaires de bureaux. Il doit représenter l'état énergétique d'un bâtiment, anticiper sa consommation, détecter les dérives et proposer des actions qui tiennent compte du confort, du coût et de la sécurité.

Nous n'avons pas accès à un bâtiment instrumenté. Le démonstrateur exploite des mesures historiques ouvertes, rejouées comme un flux, et des variables ou perturbations simulées. Le jumeau numérique désigne ici une représentation dynamique du comportement énergétique, pas une maquette 3D. Le prototype ne commande pas un bâtiment réel.

### Problématique proposée par le coach le 1er octobre

Comment concevoir un jumeau numérique augmenté par l’IA capable d’anticiper, de détecter et d’atténuer des perturbations énergétiques affectant un bâtiment tertiaire, tout en respectant des contraintes de confort, de coût et de sécurité, à partir de données ouvertes et simulées ?

Cette reformulation est à intégrer au cadrage. Son ajout au compte rendu ne signifie pas que toutes les sections du portfolio ont déjà été actualisées.

### Questions de recherche à formaliser

1. Le modèle de prévision à une heure améliore-t-il les performances par rapport à une baseline simple ?
2. Les recommandations améliorent-elles les résultats face aux perturbations par rapport à une stratégie sans adaptation, sous contraintes de confort et de coût ?
3. L'analyse des résidus de prévision permet-elle de détecter les anomalies de fonctionnement en limitant les fausses alertes, notamment lorsque la consommation augmente à cause de la météo ?

## 2. Équipe et interlocuteurs

| Personne | Rôle organisationnel indiqué dans le portfolio |
|---|---|
| Victor ROULEAU | Garant ; contribution data/IA dans le travail actuel |
| Melchior GERRIER | Intégrateur |
| Kamil BENJELLOUN | Investigateur |
| Matthis NANTAS | Facilitateur |
| Rayan GAAD | Scribe |
| Yvan Bonival FEUGANG KATCHESSIPO | Investigateur |

Coach : Badr TAJINI. Auteur du sujet : M. Jassri. Les rôles peuvent tourner selon les jalons ; vérifier les affectations actuelles avant d'assigner du travail. Ne pas déduire une répartition technique complète de ces seuls rôles.

## 3. Périmètre du MVP

Le MVP recommandé comprend :

- un simulateur de flux historiques avec injection de perturbations ;
- une prévision de consommation à une heure ;
- une détection d'anomalies fondée sur les résidus ;
- des recommandations explicables ;
- un dashboard minimal de quatre à cinq écrans, dont le contenu reste à spécifier.

Deux scénarios prioritaires : **surconsommation HVAC** et **vague de chaleur**. HVAC/CVC désigne le chauffage, la ventilation et la climatisation. Une hausse explicable par la météo doit pouvoir être distinguée d'une dérive de fonctionnement.

Pas de modélisation 3D. Hébergement cloud optionnel ; démonstration locale privilégiée. Transformer en bonus uniquement. Production solaire, batterie, coupure réseau et scénarios d'attaque ont été évoqués, mais ne constituent pas des exigences supplémentaires acquises du MVP.

## 4. Décisions et trajectoire des réunions

### 16 septembre 2026 — Kick-off

Prise en main du sujet et du portfolio, rédaction de l'accord d'équipe, notes individuelles, premiers travaux d'état de l'art.

### 23 septembre 2026 — Cadrage avec l'auteur

Orientation vers un prototype virtuel avec données réelles ouvertes ou simulation, tableau de bord énergétique, critères de résilience, météo et prise en compte des contraintes énergétiques et de coût.

### 30 septembre 2026 — Données et architecture

- BDG2 retenu comme dataset de référence, sur un bâtiment de bureaux.
- Simulateur IoT envisagé sous forme de script Python asynchrone à cadence configurable.
- TimescaleDB/PostgreSQL choisi dans le compte rendu comme base de données unifiée.
- LightGBM/XGBoost envisagés pour la prévision.
- Docker Compose prévu pour la reproductibilité locale.
- Streamlit favorisé pour la rapidité ; React/Vue restent des alternatives à arbitrer.
- Des ratios fixes de ventilation des usages ont été évoqués : 45–50 % CVC, 25–30 % informatique, 15–20 % éclairage et un résiduel. Ils sont des hypothèses historiques, pas des sous-mesures de Miriam ni une ventilation finale validée. Ils doivent totaliser 100 % si utilisés.

### 1er octobre 2026 — Recommandations du coach

- Unifier prévision, détection et recommandation autour de l'écart observé/prévu.
- Prévision à une heure avec baseline et évaluation MAE/RMSE.
- Détection possible par seuil statistique, enveloppe prédictive, conformal prediction ou Isolation Forest sur les résidus ; méthode finale non choisie.
- Variables envisagées : température extérieure, température intérieure, occupation, consommation globale et consommation HVAC.
- Occupation encore à arbitrer ; variables absentes à simuler ou à étudier dans d'autres sources.
- Réduire le périmètre aux deux scénarios prioritaires.
- Prévoir deux à trois semaines de marge pour fiabiliser les démonstrations.
- Soutenance intermédiaire pouvant présenter le cadrage et une trajectoire crédible sans produit fonctionnel. Date évoquée : **21 octobre 2026, à confirmer**.

Le compte rendu de cette réunion a été ajouté à l'annexe A du portfolio original. Le fichier original est un DOCX stocké dans Google Drive, pas un Google Doc natif.

## 5. Architecture cible et état d'implémentation

Flux cible : données historiques et scénario simulé → simulateur → ingestion et stockage → prévision → résidu observé moins prévu → détection → recommandation → dashboard.

Une prévision doit être produite avant de connaître la consommation cible. Le résidu est calculé une fois cette consommation observée. Le moteur de recommandation utilise l'alerte et le contexte météo, thermique et d'occupation disponible.

| Composant | Orientation | État connu au 2 octobre |
|---|---|---|
| Exploration et sélection du bâtiment | Python, pandas, matplotlib | Notebook réalisé avec sorties enregistrées |
| Prévision | Baselines puis LightGBM ou XGBoost | Pas de résultats de prévision fournis |
| Détection | Résidus du modèle | Méthode et seuils à définir |
| Recommandations | Règles, éventuellement optimisation sous contraintes | À formaliser |
| Flux IoT | Rejeu Python ; MQTT/API à préciser | Implémentation non vérifiée |
| Stockage | TimescaleDB/PostgreSQL | Choix indiqué ; déploiement non vérifié |
| Dashboard | Streamlit favorisé | Arbitrage final et implémentation non vérifiés |
| Reproductibilité | Docker Compose | Prévu ; fonctionnement non vérifié |
| Simulation thermique et occupation | Approches discutées ci-dessous | Pas encore implémentées dans le notebook fourni |

Ne pas présenter une orientation d'architecture comme un composant déjà fonctionnel. Inspecter le dépôt avant de créer une structure, d'installer des dépendances ou de remplacer un outil.

## 6. Données et avancement actuel

### Source et structure locale utilisée

Dataset : Building Data Genome 2, BUDS Lab. Les chemins relatifs utilisés par le notebook sont :

```text
data/metadata/metadata.csv
data/meters/raw/electricity.csv
data/meters/cleaned/electricity_cleaned.csv
data/weather/weather.csv
```

Le notebook actuel utilise **l'électricité brute**, pas le fichier cleaned. Les CSV étaient présents dans l'environnement de l'utilisateur mais n'ont pas été fournis avec le notebook pour une réexécution indépendante.

### Notebook de référence

**`Miriam_2016-2017.ipynb`** remplace les explorations antérieures `test.ipynb` et `test(1).ipynb` pour la sélection du bâtiment. Toutes ses cellules de code possèdent des compteurs d'exécution et aucune erreur n'est enregistrée dans la version examinée.

L'exploration initiale portait sur `Panther_office_Karla`. Le choix actuel est **`Hog_office_Miriam`**, site **`Hog`**, sur les deux années complètes 2016–2017.

### Résultats enregistrés dans le notebook

| Indicateur | Résultat |
|---|---:|
| Bâtiments dans les métadonnées | 1 636 |
| Bâtiments Office | 307 |
| Bâtiments Office avec colonne électricité | 296 |
| Candidats satisfaisant le filtre strict de couverture | 34 |
| Période de Miriam | 01/01/2016 00 h à 31/12/2017 23 h |
| Mesures horaires attendues et présentes | 17 544 |
| Mois complets | 24 |
| Consommations manquantes, nulles, négatives ou infinies | 0 |
| Plus longue séquence constante | 3 heures |
| Consommation moyenne | 23,048 kWh par intervalle horaire, selon le libellé du notebook |
| Minimum / maximum | 6,9685 / 44,405 |
| Rapport des médianes mensuelles extrêmes | 1,404 |
| Rapport consommation moyenne week-end/semaine | 0,774 |
| Heures sans ligne météo | 2 |
| Températures extérieures manquantes après fusion | 4 |
| Corrélation linéaire consommation/température | 0,328 |

Les unités et la convention des timestamps doivent être confirmées dans la documentation de la source avant de figer le schéma final. Les statistiques ci-dessus sont issues des sorties sauvegardées, pas d'un nouveau calcul sur les CSV.

### Ce que fait le notebook

- Vérification des timestamps manquants et dupliqués.
- Grille horaire fixe de 2016–2017 et réindexation pour révéler les heures absentes.
- Filtre conservateur : chaque consommation doit être positive et finie sur toute la période.
- Comparaison détaillée de Miriam, Napoleon, Myles, Antonina et Karla.
- Inspection de la couverture, des séquences constantes et des niveaux mensuels.
- Contrôle de la couverture météo de chaque candidat étudié.
- Fusion par `left join` avec `validate="one_to_one"`, sans perte de lignes de consommation.
- Variables calendaires : heure, jour de semaine, mois et indicateur week-end.
- Graphiques temporels, profils semaine/week-end et relation température/consommation.
- Conclusion explicite motivant le choix de Miriam.

Les graphiques montrent un profil d'activité diurne marqué et une saisonnalité. La relation météo semble non linéaire ; la corrélation seule ne prouve pas un effet causal ni la consommation spécifique de climatisation.

### Pourquoi Karla a été écarté

Sur le périmètre complet : 3 377 heures à zéro, dont une séquence de 2 923 heures, 11 valeurs manquantes et seulement 16 mois entièrement valides selon le filtre. Ce choix ne signifie pas que tous ses zéros sont nécessairement des erreurs de mesure ; il signifie que Karla ne convient pas au périmètre complet retenu avec ce filtre.

### Limites et petites améliorations restantes

- Le tableau général est trié principalement par éligibilité/couverture puis par nom : ce n'est pas un classement final de stabilité.
- Le filtre sans zéro est une règle pratique de sélection, pas une règle universelle de qualité des compteurs.
- Documenter le fuseau horaire et la gestion de l'heure d'été avant d'interpréter les profils.
- Définir le traitement des quatre températures absentes.
- Ne pas imputer aveuglément toutes les variables météo : `cloudCoverage` a 8 640 valeurs manquantes et `precipDepth6HR` en a 16 815 ; certaines précipitations affichent -1, dont la signification doit être vérifiée avant usage.
- La sélection a utilisé les deux années pour un contrôle exploratoire. Le signaler et ne pas choisir ensuite le bâtiment en fonction des scores du jeu de test.

L'exploration est suffisamment avancée pour passer à la prévision. Ne pas relancer indéfiniment la sélection du bâtiment sans nouvelle raison concrète.

## 7. Occupation, température intérieure et HVAC

### Données réellement disponibles dans l'expérimentation actuelle

Consommation électrique globale de Miriam et météo extérieure du site Hog. Aucune série horaire d'occupation, de température intérieure ou de consommation électrique HVAC n'a été identifiée dans les fichiers exploités. La présence éventuelle d'un champ statique `occupants` dans les métadonnées ne fournirait pas à elle seule une série de présence horaire ; sa valeur pour Miriam reste à vérifier.

### Approches discutées, non encore validées par l'équipe

1. Obtenir des mesures du même bâtiment : meilleure correspondance, mais disponibilité non établie.
2. Simuler un planning d'occupation et un modèle thermique simple : proposition adaptée au MVP.
3. Utiliser EnergyPlus : simulation plus détaillée mais nécessitant des paramètres de bâtiment et de HVAC, avec un coût de mise en œuvre supérieur.

### Proposition de simulation d'occupation

Planning de bureaux selon heure/jour, arrivées et départs progressifs, baisse à midi, faible présence le week-end, variations entre jours et événements ponctuels. Utiliser un taux entre 0 et 1 si la capacité réelle est inconnue. Tout nombre de personnes ou capacité supposée doit être explicite et configurable. Les vacances et jours fériés doivent correspondre au lieu et aux années simulées, si intégrés.

Ne pas reconstruire l'occupation à partir de la consommation cible puis utiliser cette occupation pour prédire la même consommation : ce serait circulaire. Une occupation simulée uniquement à partir du calendrier n'est pas une nouvelle mesure indépendante d'activité.

### Proposition de simulation thermique

Modèle thermique simplifié, éventuellement de type résistance-capacité :

```text
C × dT_int/dt = (T_ext − T_int)/R
               + Q_occupants + Q_equipements + Q_solaire + Q_HVAC
```

`R` représente la résistance thermique, `C` la capacité thermique, et les `Q` des puissances thermiques. Le HVAC agit selon une consigne et une puissance limitée ; le refroidissement est négatif. Distinguer la puissance thermique délivrée et la consommation électrique du HVAC, reliées par un rendement/COP hypothétique documenté. Vérifier les unités, le pas d'intégration et la stabilité numérique ; un flux horaire n'impose pas un pas d'intégration thermique d'une heure.

Sans mesures intérieures, le modèle thermique n'est pas calibré ni validé sur Miriam. Il représente un bâtiment de bureaux hypothétique alimenté par sa météo, pas une reconstitution exacte de son état intérieur.

### Séparer les preuves expérimentales

- **Prévision réelle** : consommation de Miriam, météo, calendrier et historique ; comparaison baselines/modèle.
- **Résilience simulée** : occupation, état thermique et HVAC cohérents ; scénarios, recommandations et effets sur confort/consommation.

Ces deux expérimentations peuvent partager une interface et un pipeline, mais leurs résultats doivent rester identifiables. Ajouter une température synthétique à une ligne BDG2 ne la transforme pas en observation réelle. Ne pas joindre arbitrairement des observations d'un autre bâtiment comme si elles provenaient de Miriam.

Si une consommation totale perturbée est construite, expliciter la référence, la composante HVAC et son incrément afin d'éviter de compter deux fois le HVAC déjà inclus dans le compteur global. Une vague de chaleur simulée doit modifier de façon cohérente la charge thermique et la consommation, pas seulement la colonne météo.

## 8. Prochaine étape : prévision à une heure

Aucun modèle n'a encore été évalué dans les fichiers fournis. La prochaine étape est un notebook de prévision dédié, en conservant le notebook d'exploration comme justification du choix.

1. Fixer la convention : à l'instant t, prévoir la consommation de l'intervalle cible à t+1 h ; documenter si le timestamp des mesures désigne le début ou la fin de l'intervalle et quand la mesure devient disponible.
2. Construire un dataset horaire avec uniquement les données disponibles au moment de la prévision.
3. Fixer une séparation chronologique entraînement/validation/test. Les dates restent à décider. Couvrir les saisons et justifier le découpage ; ne pas effectuer de split aléatoire.
4. Définir un traitement causal des rares valeurs météo absentes. Ne pas interpoler avec des valeurs futures dans une évaluation simulant le temps réel.
5. Évaluer des baselines : même heure la veille et même heure la semaine précédente ; persistance dernière observation éventuellement utile à une heure.
6. Ajouter des variables historiques et calendaires, puis entraîner LightGBM ou XGBoost.
7. Comparer MAE/RMSE sur exactement les mêmes heures et examiner les erreurs par période, heure et conditions météo.
8. Sauvegarder prédictions, observations, timestamps et résidus hors entraînement pour préparer la détection.

Pour une ligne indexée par l'heure cible s, les baselines veille et semaine correspondent à y(s−24 h) et y(s−168 h). Adapter les décalages si les lignes sont indexées par l'instant d'émission plutôt que par la cible. Les moyennes glissantes doivent exclure la consommation cible.

La météo observée à t+1 n'est normalement pas disponible à t. Utiliser la météo connue à t, une prévision météo disponible à t, ou déclarer clairement une expérimentation utilisant la météo future observée comme hypothèse idéale. Les paramètres d'imputation et autres transformations apprises sont ajustés sur l'entraînement uniquement. Les consommations du test peuvent servir d'historique une fois observées dans une évaluation roulante à une heure, sans réentraîner ni régler le modèle sur les résultats du test.

## 9. Détection et scénarios à construire ensuite

### Résidus

Définir `résidu = consommation observée − consommation prévue`. Un résidu positif élevé peut signaler une surconsommation, mais également une erreur de modèle ou une donnée de mauvaise qualité. Définir et calibrer les seuils sur des données séparées de l'entraînement ; conserver un jeu de test final.

La détection sur consommation globale peut signaler une surconsommation, mais ne permet pas à elle seule de prouver que le HVAC en est la cause. Cette attribution repose sur la vérité du scénario injecté ou sur des variables additionnelles.

### Surconsommation HVAC

Définir un mécanisme d'injection, une amplitude, une durée, un début/fin et une vérité terrain. Mesurer faux positifs, rappel/précision, délai de détection et énergie excédentaire. Ces métriques sont proposées ; les seuils d'acceptation restent à décider.

### Vague de chaleur

Définir un profil météo perturbé et une réponse thermique/HVAC cohérente. Distinguer hausse attendue de consommation, saturation HVAC et dépassement de confort. Comparer stratégie sans adaptation et stratégie recommandée dans le même scénario avec les mêmes conditions initiales.

### Recommandations et validation

Exemples à définir : inspection HVAC, ajustement de consigne, décalage ou limitation de charges. Documenter les contraintes de confort, coût et sécurité avant d'affirmer qu'une action améliore la résilience. Si aucun prix de l'électricité n'est fourni, utiliser une hypothèse tarifaire explicite ; ne pas annoncer un gain économique réel sans modèle de coût.

Ne pas évaluer une économie d'énergie en retranchant simplement un pourcentage arbitraire : simuler les conséquences de l'action, y compris sur la température. Tester plusieurs paramètres/scénarios pour éviter qu'une conclusion dépende d'un seul jeu d'hypothèses favorable.

## 10. Cybersécurité

Pistes évoquées : sécurisation MQTT/API, scénario d'attaque, contrôle d'intégrité par hachage et contribution à la détection. Périmètre final à préciser par le pôle cybersécurité.

Un hachage seul ne prouve pas l'authenticité d'un message si un attaquant peut modifier le contenu et recalculer le hash. Choisir les mécanismes selon le modèle de menace : authentification, contrôle d'accès, chiffrement des échanges, HMAC/signature et gestion des secrets si nécessaires. Une anomalie énergétique n'est pas automatiquement une cyberattaque.

## 11. Calendrier et démonstrations

Fenêtre de réalisation indiquée dans le portfolio : fin septembre à mi-décembre 2026, avec quatre jalons. Dates exactes et livrables des jalons à vérifier dans les documents de l'équipe.

Actions historiques indiquées pour le jalon 2 : extraction/analyse exploratoire le 5 octobre ; simulateur, règles et environnement technique autour du 8 octobre. Ces échéances ne prouvent pas que les tâches ont été achevées. Le choix de Miriam a depuis remplacé celui de Karla dans le travail data.

Deux démonstrations clés recommandées par le coach :

1. Prévision et détection opérationnelles sur le flux.
2. Perturbation injectée, détectée et suivie d'une recommandation compréhensible.

Prévoir deux à trois semaines avant les échéances pour l'intégration et la validation. Date de soutenance intermédiaire évoquée : 21 octobre, non confirmée dans le contexte disponible.

## 12. Points à arbitrer

- Découpage temporel exact de l'évaluation et disponibilité des variables à une heure.
- Unités et convention temporelle des données.
- Inclusion de l'occupation dans le MVP et capacité hypothétique.
- Paramètres du modèle thermique, consignes et limites de confort.
- Construction cohérente de la consommation HVAC simulée et son lien à la consommation totale.
- Méthode de détection, calibration et critères d'acceptation.
- Règles de recommandation, tarif et stratégie de référence.
- Interface définitive, transport des flux et périmètre cybersécurité.
- Confirmation des échéances et mise à jour du cadrage/planning du portfolio.

## 13. Consignes de reprise pour les agents

- Lire ce fichier puis inspecter le dépôt et le notebook de référence avant d'agir.
- Conserver Miriam comme bâtiment retenu, sauf problème nouveau documenté ou instruction de l'équipe.
- Préserver les données brutes et les sorties utiles ; produire les données dérivées séparément.
- Distinguer systématiquement mesures réelles, estimations, simulations et hypothèses.
- Ne pas inventer de résultats d'exécution, de métriques ou de données manquantes. Sans CSV, vérifier le code et les sorties enregistrées en signalant la limite.
- Commencer par les baselines et la prévision avant d'ajouter des modèles complexes.
- Éviter toute fuite temporelle, tout réglage sur le test final et toute validation circulaire.
- Garder un MVP réaliste : deux scénarios, pas de 3D, cloud et Transformer optionnels.
- Documenter les décisions nouvelles et les changements d'état dans ce fichier, avec date et preuve succincte.
- Ne pas affirmer que le projet constitue une nouveauté scientifique démontrée ni que les références de l'état de l'art ont été vérifiées indépendamment.

## 14. Sources de ce contexte

- Portfolio PFE 2026–2027 et comptes rendus des réunions 1 à 4.
- Notebook `Miriam_2016-2017.ipynb`, code, sorties enregistrées et graphiques examinés le 2 octobre 2026.
- Échanges de cadrage concernant les prochaines étapes et les approches de simulation. Les recommandations issues de ces échanges sont indiquées comme propositions, pas comme décisions d'équipe acquises.

Ce fichier est un document de contexte destiné aux agents. Il ne remplace pas les consignes du coach, les données sources, le portfolio officiel ni la validation expérimentale du prototype.
