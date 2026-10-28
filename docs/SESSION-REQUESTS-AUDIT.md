# Audit des demandes de la session

Cet inventaire reconstitue les exigences exprimées pendant la session, y compris
les corrections successives. Il complète [TODO.md](TODO.md) ; il ne constitue pas
une déclaration de réussite en production. Les répétitions d'une demande signalent
une régression ou une absence de résultat visible, pas une nouvelle fonctionnalité.

L'inspection porte sur les sources et les modifications en cours. Une fonction
présente dans le code, une capture archivée, une compilation ou un test unitaire
ne prouvent pas son bon fonctionnement dans la partie réelle. La clôture d'une
ligne exige une observation en production correspondant à **toute** la demande.
Les preuves de déploiements historiques consignées dans TODO.md ne ferment pas
automatiquement une régression signalée ensuite.

## Priorité et règles de clôture

1. Finir et éprouver Soul Weapon / Engraving en jeu : identité correcte, variante
   correcte, meilleures pièces, retrait et pose, huit verrous fermés, reprise.
2. Rétablir les éléments visibles signalés comme cassés : mode, cubes, débits.
3. Enregistrer honnêtement la navigation utilisateur et lire les écrans visités.
4. Compléter les données nécessaires aux calculs et la cartographie autorisée.
5. Résoudre les incidents de flux et valider l'ensemble de l'interface réelle.

L'agent principal reste concentré sur Soul Weapon / Engraving ; les autres sujets
sont délégués ou explicitement laissés en TODO. Agent mode autorise le pilotage
direct par l'agent. Les contrôles en production sont la preuve attendue ; les
tests automatiques servent de garde-fous et ne s'y substituent pas.

Chaque preuve de clôture doit identifier la demande, la version livrée, l'écran
et la résolution observés, la séquence effectuée, le résultat réel et la capture
ou le journal privé associé. Conserver séparément les cases « code », « livré »
et « vérifié en jeu ». Ne publier ni secrets, ni adresses, ni captures brutes dans
ce document.

## Corrections ultérieures qui font foi

| Sujet | Exigence finale à conserver | Ancienne demande remplacée |
|---|---|---|
| Débits | Tous les débits affichés par **heure**. | Les variantes `/sec`, `/s` et la demande du `s` minuscule ne sont plus l'unité finale. |
| Débits visibles | Gold, cubes, âmes vertes/bleues/rouges, armes L3 et accessoires L3. | Les compteurs de pierres ont été retirés à la demande de l'utilisateur ; aucune âme blanche/h. |
| Équipement/h | Arme/h uniquement sur un stage donnant des armes ; accessoire/h uniquement sur un stage donnant des accessoires. | Afficher simultanément les deux sans tenir compte du stage observé. |
| Format | Valeurs des ressources et débits abrégés dans les options ; solde de cubes de l'overlay en entier avec séparateurs. | La formulation demandant des valeurs non abrégées dans les options a été corrigée immédiatement par l'utilisateur. |
| Position des cubes | Position fixe entre les deux positions du gold, alignement du nombre sur le début **moyen** du nombre de gold. | Alignement dynamique qui suit les petits déplacements du gold ; position à droite des diamants. |
| Cubes estimés | Mise à jour chaque seconde d'après un débit réellement mesuré, resynchronisation sur lecture réelle. | Attendre chaque nouvelle lecture visuelle pour changer le nombre. |
| Pause utilisateur | Cinq secondes renouvelées à chaque input ; observation maintenue. | Dix secondes. |
| Couleurs du mode | Stable : nom blanc, timer/défaut vert ; input : bleu ; retour/recalcul : orange ; véritable blocage : rouge. | Ancienne répartition bleu/vert/orange et overlay systématiquement rouge. |
| Fraîcheur | Donnée fraîche blanche, puis bleu clair avec l'âge ; horodatage gris à droite. | Valeur toujours blanche sans indication de fraîcheur. |
| Battle | Écran de combat non grisé avec huit compétences en bas ; le combat réduit ne crée pas un menu Battle. | Reconnaître Battle parce qu'un morceau du combat est visible derrière une fenêtre. |
| Enregistrement debug | Actions distinctes pour navigation autorisée/interdite, élément scannable rectangulaire et sliders vertical/horizontal ; capture manuelle et correction d'écran. | Un unique bouton ambigu « record a tap ». |
| Historique | Exemples persistants des écrans distincts, positions de scroll et transitions ; limite de graphe portée à 2 000 nœuds. | Compter dix captures ou 500 signatures comme preuve d'exhaustivité. |
| Accès réseau historique | Le VPS se connecte au dédié via WireGuard ; vérifier le sens et la clé du bon pair. | Configurer par erreur le sens inverse ou une autre relation VPS/Cloud Phone. |

## Soul Weapon et Engraving

| ID | Demande à satisfaire | Éléments existants inspectés | Reste à établir en production |
|---|---|---|---|
| SW01 | Changer automatiquement de Soul Weapon selon la configuration du mode. | `features/soul_weapon.py`, `features/stage_change.py`, `features/engraving.py`. | Atteindre l'arme demandée, la sélectionner et l'équiper si nécessaire ; confirmer son nom et Unequip sur une capture fraîche. |
| SW02 | Appliquer automatiquement la bonne variante d'Engraving. | `features/engraving_setup.py`, `features/engraving_setup_rules.py`, `engravings.json`. | Exécuter la transformation réelle et comparer chaque pièce/cellule au patron cible ; une cible enregistrée n'est pas une cible appliquée. |
| SW03 | Ne jamais montrer le patron d'une autre arme, notamment Relax/Ecstasy. | Lecture du nom et liaison de la grille à l'identité ; règles de présentation dans `page_engraving.js`. | Vérifier les variantes de l'arme réellement ouverte, puis changer d'arme et constater l'invalidation des anciennes données. |
| SW04 | Choisir toujours la pièce admissible de niveau le plus élevé entre deux pièces de même forme. | `choose()` trie d'abord le niveau, puis seulement le bonus et les autres critères. | Cas réel avec deux niveaux différents, y compris une pièce inférieure déjà posée ; niveau illisible ne vaut pas meilleur choix. |
| SW05 | Reverrouiller immédiatement une pièce retirée. | Séquence `remove()` puis `lock()` et état de récupération persistant. | Retrait réel, perte du marqueur de pose, fermeture du cadenas et lecture de confirmation. |
| SW06 | Vérifier le verrou après chaque pose et les huit verrous avant de sortir. | Vérifications fraîches/stables et refus de sortie non confirmée. | Huit cadenas réellement fermés à la fin ; conserver la capture et l'état final. |
| SW07 | Reprendre de façon robuste après input, interruption ou erreur. | Bail exclusif, annulation drainée, `recovery`, contrôles d'identité avant les gestes. | Interruption réelle maîtrisée, aucun clic résiduel, état de récupération correct et reprise sans déverrouillage accidentel. |
| SW08 | Garder la même identité tout au long de l'opération. | Contrôles du nom sur les lectures, popups, previews, gestes et retour final. | Vérifier qu'un changement d'écran/arme arrête l'opération et n'autorise aucun geste sur la mauvaise cible. |
| SW09 | Soul Weapon « prête » uniquement après preuve complète. | Lecture finale du nom, Unequip, grille, niveaux et verrous ; résultat lié à la révision. | Observer un résultat réel complet ; ne pas utiliser un badge rouge, un cache, une santé farming ou une réponse HTTP comme preuve. |
| SW10 | Pouvoir retenter une configuration inchangée après échec. | Modification en cours : `POST /mode/setup` et action dans la ligne État. | Retenter la cible courante sans modifier artificiellement le mode ou l'arme ; gérer double clic, cible modifiée et refus réels. |
| SW11 | Options utilisables, sans champs techniques inutiles. | Brouillon, cible acceptée, variante, applicabilité et résultat sont séparés. | Faire le parcours complet de choix/application/échec/reprise dans la vraie webapp ; retirer les doublons réellement inutiles. |
| SW12 | Piloter en Agent mode pour examiner et tester le jeu. | Le mode existe dans `page_mode.js` et les règles de mode ; pilotage agent distinct de Free play. | Utiliser réellement ce mode pour les vérifications autorisées, puis observer le retour au mode demandé. |
| SW13 | Finir le setup, pas seulement les lecteurs ou les tests. | TODO distingue calibration Equip/Unequip et première opération réelle. | Consigner le premier setup complet réel et ses résultats. Cette ligne reste ouverte tant que SW01–SW09 ne sont pas prouvés ensemble. |

## Consigne, statut, intention, notifications

| ID | Demande à satisfaire | Éléments existants inspectés | Reste à faire ou prouver |
|---|---|---|---|
| M01 | Le plugin respecte continuellement la consigne ; l'ancien terme « watchdog » ne doit pas masquer le moteur principal. | Mode, surveillance, navigation et refresh restent des modules distincts. | Présenter une architecture cohérente et un comportement continu compréhensible, pas une collection de « repairs ». |
| M02 | Cinq modes, Free play en premier, Agent mode en dernier. | Ordre explicite des cinq dialogues dans `page_mode.js`. | Vérifier les cinq choix dans la version réellement chargée par le navigateur. |
| M03 | Free play observe l'utilisateur sans reprendre la main automatiquement. | Règles de mode et scan passif présents. | Observer une session réelle, y compris plusieurs transitions rapides ; aucune action de farming ne doit intervenir. |
| M04 | Après chaque input, attendre cinq secondes tout en observant ; chaque nouvel input remet le délai à cinq. | `INPUT_PAUSE_MS`, bail et règles de pause. | Mesurer le comportement réel lors d'inputs répétés, d'un glissement et d'une reconnexion. |
| M05 | Distinguer consigne persistante, statut et intention temporaire. | `/mode.intention`, `resource_refresh`, ligne Intention. | Une excursion de lecture doit garder le mode, indiquer le but puis revenir ; aucun statut incohérent entre page et plugin. |
| M06 | À chaque redirection, annoncer le chemin complet calculé avec tous les clics. | Les intentions observées dans les sources publient encore `route: None`, `route_known: False`. | **Manque fonctionnel** : calculer un vrai chemin applicable, le présenter et le recalculer après changement ; ne pas inventer une route complète dans la notification. |
| M07 | Overlay : uniquement le nom du mode et le timer ou « défaut » en minuscules. | Deux lignes produites par `page_mode.js`. | Vérifier placement, contenu et absence d'explication supplémentaire sur le jeu réel. |
| M08 | Respecter les couleurs finales du mode et réserver le rouge aux vrais blocages. | Tons du mode et blocage de configuration explicite. | Observer stable/input/reprise/blocage réel, puis résolution ; pas de rouge persistant pour une excursion normale. |
| M09 | Le mode reste visible lorsque les ressources ne sont pas lues. | Correctif en cours : visibilité du label séparée de Gold/âmes dans `page_gold.js`. | Vérifier le canvas réel avec ressources absentes, anciennes, erreur API et changement de menu. |
| M10 | Expliquer les causes via notifications/options, avec des mots précis. | Textes traduits et motifs par intention ; historique de déduplication. | Éliminer les notifications vagues « repair », nommer cause/destination/résultat et éviter les doublons dans une vraie séquence. |
| M11 | Vrai blocage : alerte ntfy **et** information à l'écran. | Notifications et états d'erreur existent. | Déclencher un cas contrôlé réel et vérifier les deux canaux, puis la disparition du blocage. |
| M12 | Si un overlay attendu n'apparaît pas, le front doit le signaler et ntfy doit recevoir une erreur. | Aucun circuit complet de détection d'absence de l'overlay attendu retrouvé dans les sources inspectées ; diagnostic de compteurs ne suffit pas. | **Manque à traiter** : détection observable, distinction overlay volontairement masqué/absent, message frontend et erreur ntfy avec déduplication. |
| M13 | Annoncer chaque mise en production par ntfy au nom de l'agent. | Instruction persistée dans `AGENTS.md` ; titre demandé `Agent Codex — déploiement`. | Vérifier l'envoi et la réception pour chaque release ; annoncer version et résultat réel sans prétendre avoir testé le gameplay si ce n'est pas le cas. |
| M14 | Éviter « Téléphone : libre » ambigu. | Le produit distingue des états de mode et de bail ; vocabulaire historique subsiste dans certains diagnostics. | Vérifier que le texte utilisateur dit ce qui est observé/attendu et ne confond pas absence de bail avec absence d'activité. |

## Ressources, compteurs et présentation

| ID | Demande à satisfaire | Éléments existants inspectés | Reste à faire ou prouver |
|---|---|---|---|
| R01 | Onglet Ressources distinct de l'état du jeu par menus. | `page_game.js` sépare ressources, analyse et affichage. | Vérifier le rangement réel et l'absence de ressources dupliquées dans les menus. |
| R02 | Toutes les ressources demandées, avec leur vraie icône. | `resources.json` contient 21 ressources ; voir liste précise ci-dessous. | Compléter les lecteurs et les icônes manquants, puis contrôler les valeurs réelles. |
| R03 | Une ressource par ligne, compacte, icône avant valeur et alignement vertical. | Lignes `compact` et grille de `pluginOptions.tsx`, icônes normalisées. | Vérifier en français et anglais, grande valeur, petite fenêtre et mobile ; aucun débordement. |
| R04 | Valeurs blanches quand fraîches, puis bleu clair ; horodatage toujours gris à droite. | `page_freshness.js`, métadonnées `timestamp` et `color`. | Vérifier l'évolution réelle et la séparation couleur de valeur/couleur d'horodatage. |
| R05 | Écrire simplement `never read` si la donnée ou l'écran n'a jamais été lu. | `page_game.js` applique cette chaîne aux données absentes. | Aucun « reader waiting for capture », faux zéro, détail vide ou texte « Données » sans contenu utile. |
| R06 | Supprimer AUTO des informations à lire dans les options. | Aucun champ AUTO retrouvé dans les lignes de données de `page_game.js`. | Contrôle de l'interface ; conserver les interdictions de clic indépendamment d'un lecteur interne de surveillance. |
| R07 | Ressources et débits abrégés dans les options. | `shortNumber()` utilisé pour ressources et débits ; voir règle finale en tête. | Vérifier gold énorme, ressources petites, zéro, valeurs manquantes et débits ; ne pas confondre zéro réel et erreur OCR. |
| R08 | Âmes blanches après âmes rouges. | Ordre défini dans `resources.json`. | Contrôle visuel de l'ordre, avec icônes et données réelles ; aucune âme blanche/h dans l'overlay. |
| R09 | Onglet Affichage pour émeraudes, diamants et compteurs de rendement. | Options des masques et `displayOptions` regroupées par `page_game.js`. | Vérifier chaque réglage en production, sa persistance et son effet exact. |
| R10 | Tronquer les émeraudes en lisant puis réécrivant les chiffres gardés à la bonne taille. | Masques/réécriture dans `page_counters.js` et modules associés. | Contrôle sur vraies valeurs, changements de longueur, dimming et résolutions ; pas un simple cache visuel mal aligné. |
| R11 | Gold/h calculé à partir des nombres complets du jeu, sans `~`. | Lecteur et modèle de débit dans `gold.py`, `features/gold.py`, règles de taux. | Lire plusieurs changements réels, confirmer le débit, les dépenses/remises à zéro, changements de stage et reprise de flux. |
| R12 | Gold/h : bleu clair puis blanc à mesure que la mesure devient fiable. | Couleur de taux dans `page_gold.js`. | Vérifier le démarrage et la maturation de la mesure sur la durée réelle. |
| R13 | Débits au bord droit, sous Scroll, lignes serrées et icône proche du nombre. | `RATE_TOP`, `RATE_STEP`, largeur de colonne et espacement dans `page_gold.js`. | Contrôle visuel sur combat complet/réduit, toutes les lignes visibles et grand nombre ; aucun compteur hors écran. |
| R14 | Débits Gold/h, cubes/h, âmes vertes/h, bleues/h, rouges/h, armes L3/h et accessoires L3/h. | Sept familles de taux sont définies ; valeurs issues des fenêtres de mesure. | Prouver chaque taux depuis des lectures réelles successives, pas seulement son emplacement ou une valeur simulée. |
| R15 | Afficher le taux d'armes ou d'accessoires selon ce que donne le stage réellement farmé. | Modifications en cours : `farming_stage`, `farming_drop`, `farming_read` et filtrage frontend. | Changer de stage réel W/A ; vérifier l'alternance, les données anciennes et le Free play sans inférence depuis la consigne. |
| R16 | Pas de pierres/h ni d'âmes blanches/h. | Champs exclus de `RATE_FIELDS`. | Vérifier la version servie et l'absence de lignes résiduelles. Les soldes de pierres restent dans Ressources. |
| R17 | Icônes réelles pour armes L3/h et accessoires L3/h. | `page_equipment_icons.js`. | Comparer aux icônes du jeu et vérifier taille, alignement et proximité de la valeur. |
| R18 | Cubes : police du jeu identique au nombre de gold, bonne taille, blanc et vrais bords noirs. | `page_gold_counter_font.js`, `drawText(... outline: 2)`. | Comparaison visuelle pixel à pixel dans les deux résolutions utilisées et sur les deux dispositions du combat. |
| R19 | Cubes : séparateurs et nombre non abrégé dans l'overlay. | Formatage du solde estimé par séparateurs et police comprenant la virgule. | Vérifier nombre grand/petit et changements de longueur, sans chiffres découpés. |
| R20 | Cubes : icône fixe entre les deux positions de l'icône gold ; nombre aligné en moyenne avec gold. | Ancre fixe `298 / 720`, icône à position fixe ; preuve de navigateur historique consignée dans TODO. | Vérifier à nouveau l'ensemble icône + nombre sur combat complet/réduit ; ne pas remettre le suivi dynamique. |
| R21 | Cubes : estimation chaque seconde même entre les captures. | `estimatedCubes()` et tick d'une seconde ; preuve partielle historique consignée dans TODO. | Maintenir le comportement dans une vraie session longue, synchroniser sans faux saut, ne pas prolonger indéfiniment un modèle invalide. |
| R22 | Cubes : fraîcheur blanche puis bleu clair, de la même famille que le bonus de dégâts Soul Weapon. | Couleur partagée par âge de lecture. | Comparer la couleur réelle au jeu et vérifier que l'estimation ne rend pas artificiellement la lecture fraîche. |
| R23 | Cubes et rendements visibles seulement sur Battle ou combat réduit ; grisés comme le jeu. | `combatCountersVisible()` et opacité liée au shade. | Parcourir combat complet, panneau réduit, modal grisé et écran sans combat ; confirmer toutes les transitions réelles. |
| R24 | Le plugin visite les écrans nécessaires pour garder ses ressources à jour pendant le farming. | `features/resource_refresh.py` : circuit borné cubes/L3, bail et retour Soul Weapon. | Premier circuit réel complet, déclenchement périodique, interruption par input et retour correct. Ce circuit ne couvre pas encore toutes les ressources. |

Les 21 ressources explicitement demandées sont : diamants, gold, émeraudes,
cubes, cristaux, âmes vertes, âmes bleues, âmes rouges, âmes blanches, dés,
pierres vertes, bleues, rouges et jaunes, plumes blanches, vertes, violettes et
noires, Dragon Power, Dragon Spark et Black Mana.

L'inspection de `resources.json` laisse **13 lecteurs marqués pending** :
cristaux, dés, quatre couleurs de pierres, quatre couleurs de plumes, Dragon
Power, Dragon Spark et Black Mana. Les bindings de `page_resources.js` ne
fournissent pas encore les icônes de **cristaux, dés, plumes noires et Black Mana**.
Une icône existante ne prouve pas qu'un compteur est lu ; l'inverse non plus.

## État du jeu, menus et données à scanner

| ID | Demande à satisfaire | Éléments existants inspectés | Reste à faire ou prouver |
|---|---|---|---|
| G01 | Copier fidèlement l'état du jeu et l'afficher dans la webapp. | Faits datés avec valeur, source et vérification dans `features/game_rules.py`. | Les nombreuses données de catalogue/archives doivent devenir des lectures vivantes ; conserver l'origine et la fraîcheur de chaque fait. |
| G02 | Menus imbriqués suivant le vrai chemin dans le jeu, sans prolifération de menus plats. | Arbre de `screen_registry.json`, `screen_path()` et `accessPath()`. | Parcours visuel de chaque branche, titres explicites et profondeur utile ; Battle n'est pas une rubrique de navigation artificielle. |
| G03 | Companion, Skill et Adventure présents. | Branches et exemples de catalogue. | Vérifier leurs sous-pages, champs utiles, icônes et lectures dynamiques. |
| G04 | Companion → Beasts et Companion → Advancement imbriqués correctement. | Parents et alias de `page_game.js`. | Vérifier tous les contenus et positions de scroll, pas seulement l'existence du nom du menu. |
| G05 | Ellie, Zeke, Miho et Luna : neuf passifs chacun, répartis dans PASSIVE, PASSIVE II, PASSIVE III. | Des exemples de Companion existent, mais aucun ensemble de 36 niveaux typés vivants n'a été trouvé dans le schéma inspecté. | **Manque fonctionnel** : identité du companion, onglet, trois passifs et leurs niveaux/effets par panneau ; données persistées et actualisées. |
| G06 | Character : compteur EXP complet. | Champ `exp` encore `pending` dans `game_rules.py`. | Lire actuel/requis (et niveau associé), pas seulement un pourcentage ; vérifier le passage de niveau. |
| G07 | Équipements : toutes les armes et tous les accessoires dans l'état du jeu. | Inventaires historiques dans `screen_inventory.json`, lecteur vivant limité aux L3. | Couvrir toute la liste et ses scrolls, possession/progression/grade/niveau utiles, identité sélectionnée et mise à jour réelle. |
| G08 | Classes : toutes les classes et leurs données dans l'état du jeu. | Entrée d'inventaire historique ; schéma vivant spécifique non établi. | Découvrir/identifier la page autorisée, lire chaque classe utile et ses propriétés ; distinguer catalogue d'état réellement possédé. |
| G09 | Equipment → Accessories → Black Orb → Obtain : plumes noires. | Chemin enregistré, ressource `feather_black` pending. | Capturer la bonne page puis fournir icône et lecteur du compteur réel. |
| G10 | Corriger Skill panel et son placement ; utiliser Skill. | Alias et chemin explicites dans `page_game.js`. | Vérifier nom, position et sous-pages dans la vraie interface. |
| G11 | Icônes Quest, Scroll, Select Region, Weapon, Black Orb et autres pages manquantes. | `page_screen_icons.js` fournit plusieurs crops réels. | Comparer les icônes des pages réelles, couvrir les manquantes et vérifier leur association au bon menu. |
| G12 | Highest stage reached : borne inférieure évolutive, pas certitude immuable. | `shown: lower_bound`, stages non atteints grisés mais sélectionnables. | Explorer la sélection des régions et relever une borne justifiée ; tester choix d'un stage supérieur sans faux refus. |
| G13 | Un nombre commençant par zéro doit être interprété correctement. | Lecteurs numériques et règles d'invalidation présents. | Corpus réel de chiffres/zéros/séparateurs ; distinguer zéro observé, chiffre tronqué et lecture impossible sans deviner une valeur. |
| G14 | Les débits sont de l'analyse, pas de la donnée brute des menus. | Sections ressources/analyse séparées. | Vérifier que quantités, taux, estimations et archives sont clairement distingués dans les options. |
| G15 | Exhaustivité des éléments utiles aux formules de calcul. | Inventaire dédié demandé à un autre agent. | Rattacher chaque entrée de calcul à un champ exact, unité, écran/onglet/scroll, lecteur, formule et preuve ; identifier explicitement les formules inconnues. |

## Captures, cartographie et navigation observée

| ID | Demande à satisfaire | Éléments existants inspectés | Reste à faire ou prouver |
|---|---|---|---|
| N01 | Faire une vraie passe exhaustive de screenshots, pas une poignée de captures. | Catalogue et archives historiques ; nombre de captures distinct de la couverture. | Pour chaque écran autorisé : exemple correct, identité, chemins aller/retour, scrolls et champs lus. Viser la couverture, pas un quota arbitraire. |
| N02 | Garder au moins un exemple persistant de chaque écran. | `features/screenshot_archive.py` et `features/screen_examples.py` ; images privées et manifeste. | Vérifier persistance après déploiement, accès depuis la webapp et correspondance réelle image/nom ; corriger les archives mal classées. |
| N03 | Expliquer comment le plugin lit les screenshots. | Readers sur captures fraîches ; crops de calibration séparés des PNG d'exemples ; signatures de graphe séparées. | Documentation et interface doivent distinguer image archivée, lecteur calibré, observation courante et formule calculée. |
| N04 | Dédupliquer les mêmes écrans et accepter 2 000 nœuds. | `trace.py` : signatures proches fusionnées, `MAX_NODES = 2000`. | Vérifier que l'animation du combat ne crée pas des milliers de faux écrans et que deux sous-pages utiles ne sont pas fusionnées. |
| N05 | Inclure les sliders et leurs positions dans la cartographie. | Zones de scroll dans le registre et gestes dans `navigation.json`. | Exemples avant/après par zone/direction, limites, éléments déplacés et chemin de retour. |
| N06 | Observer les clics et écrans en Free play et copier la navigation utilisateur. | Modifications en cours : frame navigateur avant input, marqueur de séquence, capture après et graphe. | Vérifier clics/swipes réels rapides, sessions multiples, retards réseau et source réellement antérieure ; ne pas attribuer un saut de plusieurs écrans à un seul clic. |
| N07 | Scanner les informations visibles au fil des déplacements. | Force des lecteurs sur changement d'écran/input et scan de fin de geste ajoutés. | Vérifier les chiffres qui changent lors de visites courtes Weapon → Accessories et autres panneaux ; les lecteurs encore absents restent à écrire. |
| N08 | Reconnaître presque instantanément l'écran ou au moins son changement. | Détection rapide frontend et scan backend ; `PLAYING_EVERY = 5`, lecteurs de 5 à 15 secondes hors forçage. | Mesurer la latence bout en bout sur transitions réelles ; dissocier reconnaissance rapide des lectures coûteuses. Aucun délai « quasi instantané » n'est encore prouvé par ces constantes. |
| N09 | Battle : huit compétences en bas, combat en haut ; distinguer le combat réduit et le dimming. | Lecteurs `plain_battle`, panneaux et overlays. | Vérifier les scènes de combat réelles et les modals ; un morceau de Battle derrière un menu ne suffit pas à donner accès aux contrôles complets. |
| N10 | Retour implicite en cliquant au milieu du combat jusqu'à Battle non grisé. | Mouvements `combat_return` dans `navigation.json`. | Enregistrer et vérifier chaque transition de retour depuis les panneaux réellement ouverts, sans clic aveugle sur une zone recouverte. |
| N11 | Flèche des Battle settings : position différente en Battle complet et réduit. | Deux rectangles mesurés dans `page_navigation_debug.js` et contrôles dédiés. | Comparer overlay et vrai triangle sur les deux dispositions ; ne jamais atteindre AUTO quand les contrôles se replient. |
| N12 | Title détecté par son titre/logo, pas par TAP TO START. | Détecteur fondé sur proportion de pixels blancs supprimé dans les modifications en cours ; négatif réel Beast Mount ajouté. | **Manque identifié** : capturer un vrai Title et calibrer le logo SLAYER LEGEND. Désactiver un faux positif ne constitue pas l'implémentation du lecteur demandé. |
| N13 | Les repères de détection peuvent être des éléments non cliquables. | Géométrie des anchors exposée distinctement des mouvements. | Vérifier les repères sur les captures réelles et empêcher qu'un rectangle de détection devienne une autorisation de navigation. |
| N14 | Utiliser les traces et annotations pour améliorer la reconnaissance et la navigation. | Les annotations sont enregistrées et affichées ; aucun consommateur trouvé qui transforme les corrections enregistrées en lecteurs/chemins validés. | **Manque fonctionnel** : boucle explicite d'examen, calibration, mise à jour du registre/graphe, validation réelle et statut de prise en compte. |
| N15 | Copier le parcours doit aider le moteur à retrouver la consigne. | Le graphe d'observation précise qu'il n'est jamais rejoué ; la navigation exécutée utilise le graphe statique gardé. | Définir et réaliser le passage d'une transition observée à une transition autorisée et fiable ; ne pas présenter l'enregistrement seul comme apprentissage du moteur. |
| N16 | Ne jamais toucher le menu ≡, Mailbox, Settings ou Rankings. | Filtres du catalogue et interdictions dans `navigation.json`. | Vérifier les retours/navigation/annotations contre cette interdiction ; une trace utilisateur ne vaut pas autorisation pour l'agent. |

## Debug de navigation

| ID | Demande à satisfaire | Éléments existants inspectés | Reste à faire ou prouver |
|---|---|---|---|
| D01 | Montrer les zones de navigation autorisée en jaune. | `page_navigation_debug.js` dessine les mouvements autorisés. | Comparer aux positions réelles, aux zones conditionnelles et aux écrans reconnus. |
| D02 | Zones de slide vertical toujours bleues, horizontal toujours violettes, avec chevrons. | Types de zone et dessin des sliders présents. | Vérifier couleur, direction et visibilité pendant/après scroll ; pas de confusion avec les boutons qu'elles contiennent. |
| D03 | Afficher le nom de l'écran détecté. | `recognisedScreen()` et en-tête debug. | Vérifier Battle, panneaux imbriqués, inconnu et identité périmée. |
| D04 | Ajouter un bouton de navigation autorisée. | Annotation `navigation`, capture avant/après. | Enregistrer un vrai clic, afficher retour visuel et préserver les preuves. |
| D05 | Déclarer un bouton interdit. | Annotation `forbidden`. | Enregistrement réel et prise en compte effective par le circuit de validation ; stockage seul ne suffit pas. |
| D06 | Marquer un élément scannable par rectangle. | Annotation `scannable` exige un drag rectangulaire. | Vérifier le rectangle choisi, les coordonnées, la capture et l'absence d'input accidentel dans le jeu. |
| D07 | Marquer un slider vertical ou horizontal. | Annotations distinctes `vertical` et `horizontal`. | Enregistrement réel avec avant/après et coordonnées/direction exploitables. |
| D08 | Feedback immédiat au choix, puis le menu laisse cliquer dans le jeu. | États armed/saving/saved/failed et panneau réduit pendant l'annotation. | Contrôle avec vrai pointeur ; aucun calque ne doit manger le clic destiné au jeu. |
| D09 | Menus debug cliquables, minimisables et déplaçables. | Gestion de pointer, déplacement et pliage présente. | Déplacer/réduire/restaurer sur la vraie page et accéder aux zones précédemment masquées. |
| D10 | Les boutons dans une zone scrollable suivent le scroll. | `page_navigation_tracking.js` et rects suivis. | Glissements réels dans les deux sens ; masquer une cible perdue au lieu de conserver son ancien rectangle. |
| D11 | Before/after capture avec masque debug et clic/rectangle/slide enregistré. | `page_navigation_preview.js`, overlays historiques et coordonnées. | Ouvrir deux captures réelles et vérifier l'annotation sur chacune, sans les coordonnées du nouvel écran courant. |
| D12 | Lancer manuellement un enregistrement/capture depuis le debug. | Modification en cours : « Enregistrer cet écran » et `POST /trace/capture`. | Vérifier capture sans geste, confirmation visible, persistance et ouverture de l'image. |
| D13 | Pouvoir déclarer que l'écran détecté est incorrect. | Modification en cours : choix de l'identité attendue, capture et identité détectée conservées. | Faire un vrai signalement, constater son historique puis sa prise en compte ; ne pas remplacer la classification automatique par une affirmation non vérifiée. |

## Architecture, performances et flux

| ID | Demande à satisfaire | Éléments existants inspectés | Reste à faire ou prouver |
|---|---|---|---|
| A01 | Expliquer l'architecture réelle du scan continu. | `features/game.py` : hook des captures, dernière image en attente, `scan_later`, `asyncio.Lock`, `ports.analyse(read_all, ...)`. | Donner une explication fidèle : le scan est en tâche de fond, mais `read_all` déroule les lecteurs séquentiellement dans un travail d'analyse. |
| A02 | Séparer acquisition, détection d'écran, lecteurs de données et moteur mode/navigation en tâches asynchrones pouvant avancer parallèlement. | Séparation de modules partielle ; capture/lectures directes existent aussi dans certaines features. | **Demande d'architecture non terminée** : concevoir puis mesurer les tâches, files bornées, priorités, annulation et budget CPU ; ne pas déclarer « parallèle » sur la seule présence d'async. |
| A03 | Garder des résultats cohérents quand plusieurs analyses travaillent en parallèle. | Temps d'acquisition, epoch et vérification de l'origine existent. | Tous les résultats doivent porter l'identifiant/temps de capture et l'identité de l'écran ; un ancien résultat ne doit jamais autoriser un clic sur le nouveau. |
| A04 | Reconnaissance rapide indépendante d'un OCR lent. | Certaines branches peuvent interroger un scan rapide ; le scan complet reste sérialisé. | Mesurer et réduire latence de reconnaissance et changement, même pendant les lectures de niveau/grille ou l'écriture d'archives. |
| A05 | Comprendre et résoudre le flux qui ne démarre pas ou se débloque après un bouton « physique » comme le volume. | `streamTelemetry.ts`, `useStreamStats.ts`, compteurs réception/décodage/présentation et gels. | Incident réel corrélé côté navigateur/gateway/Android, effet exact de l'input physique, cause identifiée, correctif puis reproduction réussie. Instrumenter n'est pas résoudre. |
| A06 | CPU et mémoire du serveur en temps réel dans les settings. | `serverInfo.ts` affiche CPU/mémoire ; `serverState.ts` demande les détails toutes les deux secondes quand ouvert. | Contrôler les valeurs réelles, leur mouvement, unité et coût ; afficher une indisponibilité honnête si la source n'arrive plus. |

## Organisation du travail, livraisons et preuves

| ID | Exigence | Application attendue |
|---|---|---|
| O01 | Ne pas oublier la moitié des demandes ; maintenir une TODO. | Chaque ID de cet audit doit être relié à une action ou preuve dans TODO.md. Une case historique cochée ne masque pas une nouvelle plainte. |
| O02 | Déléguer le maximum à des agents Sol 6.1, l'agent principal orchestre. | Missions sans fichiers concurrents, remontée des preuves et intégration ; le nombre d'agents n'est pas un résultat livré. |
| O03 | Recentrer personnellement l'agent principal sur Soul Weapon/Engraving. | Les captures, compteurs, debug, audit et inventaire de calculs peuvent être délégués ; garder la validation réelle du setup au centre. |
| O04 | Pousser et déployer les corrections demandées. | Identifier commit, artefact, contenu réellement installé et module réellement chargé par le navigateur. Ne pas confondre branche locale, serveur et onglet resté sur l'ancien JS. |
| O05 | Vérifier en production plutôt que réciter des suites unitaires. | Exécuter les scénarios réels autorisés, conserver les observations ; présenter les limites restantes. Tests simulés et captures d'une page isolée ne valident pas l'automatisation en jeu. |
| O06 | Plein accès : ne pas redemander systématiquement la permission. | Réutiliser les autorisations déjà données ; distinguer une vraie information manquante d'une demande de confirmation répétée. Agent mode et demandes explicites de test doivent guider l'action. |
| O07 | Critiquer l'architecture, les fonctionnalités et l'UI/UX, puis agir. | Relier chaque critique à un défaut observable, un changement proposé et sa vérification ; ne pas transformer l'autocritique en boucle sans livraison. |
| O08 | Agent dédié aux entrées des formules. | Produire un inventaire exact des données et dépendances de calcul, avec emplacements dans le jeu et couverture réelle. |
| O09 | Agent dédié à l'audit intégral de la session. | Présent document ; le réconcilier avec les changements livrés après son inspection avant d'annoncer la TODO définitive. |

## Historique hors chantier Cloud Phone à ne pas perdre

Ces demandes plus anciennes ne doivent pas être relancées aveuglément pendant le
setup du jeu. Leur accomplissement ne peut pas être déduit du dépôt Cloud Phone.
Retrouver les livrables/proofs d'origine avant de les considérer faites ou de les
refaire. Aucune adresse, clé, donnée privée ou transcription n'est reproduite ici.

| ID | Demande historique | Preuve à retrouver si elle reste attendue |
|---|---|---|
| H01 | Communiquer avec les agents Claude, notamment critique ; récupérer le contexte de l'agent homonyme. | Import effectivement ciblé sur le bon agent/session, provenance et limites de contexte. |
| H02 | Récupérer/déplacer les skills Claude vers Codex. | Inventaire source/destination et chargement effectif des skills utiles, sans écraser ceux d'un autre agent. |
| H03 | Conserver le setup serveur dans un skill puis refocaliser la session. | Skill dédié existant et complet ; ne pas prétendre avoir effacé/compacté un contexte sans mécanisme correspondant. |
| H04 | Expliquer accès externe/interne, WireGuard/SSH, comptes et ports des deux serveurs. | Schéma/doc opérationnelle datée et vérifications autorisées ; les runbooks système/WireGuard sont des sources de procédure, pas une preuve de configuration courante. |
| H05 | Réserver l'accès public au compte de secours et faire passer le reste dans WireGuard. | Règles SSH/pare-feu et tests d'accès depuis les deux chemins ; ne pas extrapoler d'une connexion réussie. |
| H06 | Expliquer mot de passe du compte de secours, protection SSH, brute force et rôle de fail2ban. | Réponse/documentation d'origine et règles réellement appliquées ; aucune nouvelle recommandation de sécurité n'est déduite ici. |
| H07 | Configurer le VPS comme pair client du dédié, déposer la configuration sur le bureau Windows. | Bon sens du tunnel, clé nouvellement générée si nécessaire, clé publique installée sur le dédié, handshake réel et fichier au bon endroit. |
| H08 | HANDOFF de la session sur le bureau Windows, renommé avec le nom de session, vérifier qu'il appartient au bon agent. | Chemin/fichier final et identité/provenance ; résoudre la collision entre les deux fichiers d'agents. |
| H09 | Expliquer le rôle de `agent.sock`. | Explication correspondant au socket réellement en question ; ne pas réutiliser une hypothèse d'un autre serveur/session. |

Le copier-coller de migration Hermes et le diagnostic d'URL Hermes ont été
explicitement déclarés erreurs de conversation : **annulés pour ce chantier**,
ils ne doivent pas redevenir des actions de la TODO Cloud Phone.

## Preuves insuffisantes à ne plus compter comme clôture

- Un fichier dans `screen_registry.json` ou un nom de menu n'est pas un écran reconnu.
- Un PNG historique n'est pas une valeur numérique relue actuellement.
- Une icône extraite n'est pas un compteur fonctionnel.
- Un graphe de signatures n'est pas un moteur capable de rejouer un chemin autorisé.
- Une annotation stockée n'est pas une correction de lecteur ou de navigation appliquée.
- Une réponse HTTP 200/202 n'est pas un setup réellement exécuté.
- Un test de règles avec gestes simulés n'est pas la fermeture réelle des huit cadenas.
- Un déploiement réussi n'est pas la preuve qu'un onglet ouvert a rechargé ses modules.
- Des milliers de tests ou de captures ne remplacent pas les critères de chaque demande.

