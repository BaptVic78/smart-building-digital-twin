# Notebooks d’exploration

`01_selection_batiment.ipynb`, anciennement `test.ipynb`, conserve la comparaison
des bâtiments Office BDG2 et la justification du choix de Hog_office_Miriam.

Le premier bloc retrouve la racine du dépôt ; le notebook peut être ouvert depuis
la racine ou depuis ce dossier. Les trois CSV BDG2 sont attendus dans `data/`,
comme indiqué dans le README principal. L’export SQL Supabase ne suffit pas à
refaire la comparaison de tous les bâtiments du dataset.

Les sorties historiques sont conservées. Lors du rangement, les chemins ont été
adaptés sans réexécuter l’ensemble des cellules, faute des trois CSV complets.
Les tests automatisés restent dans `tests/` et n’exigent pas ces fichiers.
