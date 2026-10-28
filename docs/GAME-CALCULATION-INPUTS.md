# Slayer Legend — entrées de calcul à lire dans le jeu

Ce document décrit le contrat de lecture à construire, à partir des sources du
plugin. Il ne certifie aucun état actuel du téléphone et n'autorise aucun geste.
L'inventaire couvre toutes les branches du catalogue local ; les branches non
explorées restent explicitement inconnues. Il serait inexact d'affirmer que tous
les paramètres du jeu, ou sa formule complète de dégâts, sont déjà connus.

## Nature des preuves et couverture

- **L** : lecteur de pixels présent. Sa portée est celle de ses captures de
  calibration et de ses tests, pas celle de tous les écrans du jeu.
- **S** : transcription statique d'une capture dans `screen_snapshots*.json` ou
  `screen_inventory.json`. Ce n'est ni un lecteur ni une mesure actuelle.
- **C** : entrée du catalogue/navigation ou besoin explicitement décrit dans
  `docs/TODO.md`. Écran ou champ restant à calibrer.
- **R** : champ requis pour un futur calcul, à relever avec son libellé exact ;
  son existence précise ou son effet mathématique reste à confirmer.
- **W** : donnée communautaire importée dans `engravings.json`/`stages.json` ;
  conserver sa provenance et son niveau de confiance, sans la convertir en L.

Sources locales (chemins relatifs au dépôt) :

| Référence | Source et contenu exploitable |
|---|---|
| G | `05-plugins/slayer-legend/features/game_rules.py` : SCHEMA, READERS, faits datés, invalidation, plus haut stage comme borne inférieure |
| P | `05-plugins/slayer-legend/features/game.py` : `reader_table`, sorties réellement publiées par chaque lecteur |
| T | `05-plugins/slayer-legend/screen_registry.json` : arbre, accès, exemples, défilements et inconnues |
| N | `05-plugins/slayer-legend/navigation.json` : écrans, reconnaissances, accès permis/interdits |
| S | `05-plugins/slayer-legend/screen_snapshots.json` : transcriptions Character, Skill, Equipment, Companion, Beast |
| V | `05-plugins/slayer-legend/screen_snapshots_world.json` : Adventure, Dungeon, Guild, Shop, Quest, régions |
| I | `05-plugins/slayer-legend/screen_inventory.json` : inventaires statiques d'équipement et leurs limites |
| E | `05-plugins/slayer-legend/engraving_screen.py` et `test_engraving_screen.py` : grille, huit cartes, popup, preview |
| A | `05-plugins/slayer-legend/features/engraving_setup_rules.py` : `choose`, `next_step`, `check` |
| W | `05-plugins/slayer-legend/engravings.json`, `stages.json`, README du plugin : données et provenance |
| F | `05-plugins/slayer-legend/features/gold_rules.py`, `features/gold.py` : taux effectivement calculés |
| U | `05-plugins/slayer-legend/resources.json` : registre de soldes, champs pending |
| D | `docs/TODO.md`, notamment « Character EXP » et « Companion » : trous de lecture reconnus |

Le chemin « Character → Promotion → Class » désigne la promotion du personnage.
Il ne prouve pas l'existence d'un lecteur pour toutes les classes d'équipement.
Un nom de menu ou un portrait identifié ne constitue pas une entrée numérique.

## Calculs réellement présents et leurs dépendances

| Calcul | Entrées minimales et unités | Limite / preuve |
|---|---|---|
| Débit de gold, âmes par couleur, cubes, armes/accessoires L3 | `(instant de capture en secondes, solde numérique, texte brut, résolution du dernier chiffre)` ; stage/contexte ; dépenses observables | Régression linéaire des soldes, pente tronquée à zéro : `max(0, Σ((t−moy(t))(v−moy(v)))/Σ((t−moy(t))²))`. Deux instants distincts minimum. F : `rate`, `counted`, `where`. L'affichage horaire multiplie le taux par 3600 ; aucun modèle de dégâts requis. |
| Traitement des dépenses | Baisse du solde, ressource, temps, contexte | Gold : recommence la fenêtre ; âmes : compense une baisse avec un offset. Une baisse masquant simultanément un gain ne révèle pas le gain réel. F. |
| Choix des stages mpw4/mpw18 | Stage atteint observé ; table stage → monstres/vague, couleur d'âme, type et grade de drop | `screen_rules.stage_list` filtre le nombre de monstres/vague et la borne atteinte ; ne calcule pas le rendement réel du stage. |
| Validité d'une gravure | Masque actif, cellules de chaque pièce placée | `engraving_rules.check` : manquantes, hors masque, chevauchements ; complet si aucune erreur. |
| Faisabilité d'une variante | Formes, orientations autorisées, nombre de cartes disponibles par forme/orientation | `engraving_rules.needed`, `feasible`, `fit_gold_*`. Recettes statiques ≠ pièces possédées. |
| Choix des meilleures cartes de la recette | Forme, niveau entier, option Gold, E, index 0–7 | A : niveau décroissant d'abord ; à égalité seulement, Gold pour variante Gold, puis déjà placée, puis index. Ce n'est pas une optimisation numérique du gain Gold ou des dégâts. |
| Gravure prête | Arme lue, masque lu identique à la recette, meilleures cartes effectivement placées, huit cadenas fermés | A et exécuteur `features/engraving_setup.py`. Un nom d'arme ou une grille occupée ne suffit pas. |

La formule générale de dégâts, la composition additive/multiplicative des bonus,
les courbes de coûts/améliorations et les probabilités de drop ne sont pas
implémentées dans ces modules. Les dépendances de calcul ci-dessous décrivent
les données à conserver pour les établir ; elles ne prétendent pas établir ces
formules. Un débit mesuré reste utilisable avant qu'un modèle théorique existe.

## Battle et réglages de combat

| Accès | Champs à scanner ; unité | Calcul / rôle | Couverture et preuve |
|---|---|---|---|
| Battle / Power Saving Mode | Numéro de stage, nom et suffixe romain ; identifiants | Joindre la table de stages, distinguer les fenêtres de mesure | L : `stage.py`, `stage_select.py`, P/G ; plus haut stage = borne inférieure observée, pas dernier stage déverrouillé exact |
| Battle | Progression du stage ; fraction/% et horodatage | Durée d'un cycle, détection de blocage ; futur débit de vagues | L : barre/progression ; un passage à zéro doit être distingué d'une interruption avant d'en déduire des vagues |
| Battle, équipement, Soul Weapon | Soldes Gold, cubes, diamants, émeraudes ; nombres, notation abrégée et résolution | Taux, budget d'amélioration, variation de ressources | L : `gold.py`, `cube_balance.py`, `top_currencies.py`, G/P/U |
| Soul Weapon | Âmes green/blue/red/white ; nombres, résolution | Taux par couleur, budget de fabrication | L : `soul_counters.py`, G/P/U |
| Battle → Battle settings | Preset I–V ; identifiant | Contexte nécessaire à toute comparaison de rendement | L pour preset : `battle_controls.py` ; le preset seul ne décrit pas son contenu |
| Battle settings | Skills to use, Accompanying Spirit, Skill Stone, Beast Skill, Familiar Skill, Slayer Promotion : identité de chaque slot actif et niveaux/effets associés ; unités telles qu'affichées | Reconstituer les modificateurs réellement actifs | C : N et catalogue screens ; pas de lecteur numérique complet de loadout |
| Battle | AUTO lu, états actifs/cooldowns et buffs temporaires, scroll/blessing et durée restante si visibles | Rendre les essais comparables, expliquer un débit | AUTO est contexte/état, pas une statistique ; lecteurs spécialisés partiels. Buffs/durées R ; ne pas ouvrir Scroll pour les obtenir |

## Character

| Accès | Champs précis à scanner ; unité | Calcul / rôle | Couverture et preuve |
|---|---|---|---|
| Character → Enhance (et Growth) | Level ; entier. EXP actuel **et** EXP requis ; deux entiers, pas seulement un % | EXP/s, temps avant niveau, franchissements de niveau | S pour Level ; EXP C/pending malgré deux fixtures réelles, chiffres trop petits/touchants : T/G/D |
| Enhance | ATK, HP, HP Recovery : niveau d'amélioration, valeur affichée, max éventuel et coût du prochain achat ; entier/valeur/unité affichée/gold | Décrire la base, comparer gain/coût d'amélioration | S pour les trois noms, niveaux et valeurs ; coûts/courbes R ; aucun lecteur de ces stats |
| Enhance → toutes les lignes par défilement | Chaque autre libellé de statistique, valeur, unité (% ou absolue), niveau, limite et coût | Compléter la base de combat ; CRIT/Death Strike/etc. seulement si libellés réellement observés | R : aucune liste exhaustive de ces lignes dans les transcriptions ; ne pas inventer leur présence ni leur formule |
| Growth | STAT POINT disponibles ; STR, HP, VIT : niveau actuel et Max Lv ; entiers | Budget de points et limites de progression | S ; aucun lecteur de niveaux. Effet numérique par point R |
| Growth → premier/deuxième sous-onglet | Libellés et valeurs de chaque champ ; unité affichée | Statistiques ou progression supplémentaires éventuelles | C : T dit non exploré, fonction inconnue ; pas de nom de statistique certifiable |
| Promotion | Rang/promotion actuel, chaque rang Complete/Challenge/verrouillé, Recommended Lv ; identifiants/entiers | Conditions d'accès, limites et contexte de bonus | S : rangs jusqu'au dernier listé ; aucun lecteur de progression complet |
| Promotion → Class | Classe sélectionnée/possédée, niveau, effets possédés/équipés et coûts si l'écran les distingue | Bonus de classe, budget ; distinction possession/équipement | R/C : accès actuellement interdit, non exploré (T/N), détails non vérifiés |
| Promotion → Slayer Promotion Additional Ability | Page active ; chaque ligne : libellé exact, valeur, unité, qualité, actif/inactif ; total éventuel | Bonus effectifs du preset et comparaison de pages | C/R : écran connu mais accès interdit ; aucune liste numérique certifiée ; dés jamais utilisés pour scanner |
| Fiche/statistiques détaillées, si un accès existe | Toutes les valeurs finales, libellé et unité, en particulier toute valeur permettant de vérifier les effets ci-dessus | Validation du modèle par rapport aux totaux affichés | R : accès à cette fiche non établi dans T ; ne pas assimiler les valeurs Enhance aux totaux finaux |

## Equipment

| Accès | Champs précis à scanner ; unité | Calcul / rôle | Couverture et preuve |
|---|---|---|---|
| Equipment → Weapon → chaque carte, toutes les lignes | Identité, grade, rareté textuelle, niveau +N, fraction affichée numérateur/dénominateur, E, possession explicitement établie | Inventaire, matériaux disponibles, bonus d'équipement, progression | I/S : grilles transcrites ; **une fraction 0/5 ne prouve pas que l'objet n'est pas possédé**, une couleur ne prouve pas la rareté. L uniquement compteur Legendary Grade 3 via `equipment_l3.py` |
| Weapon → détail de chaque arme | Nom/grade/rareté ; effets possédés et équipés séparés, chaque valeur/unité ; niveau/max ; coût d'amélioration, quantité possédée quand explicitement affichée | ATK réel et marginal, coût/gain ; effets permanents de collection éventuels | C/R : lecteur `weapon_detail` reconnaît la carte ; cubes lisibles ; autres valeurs non lues |
| Equipment → Accessories → grille et détails | Même inventaire complet ; chaque effet avec son libellé exact et unité, distinction possédé/équipé | HP/récupération ou autres effets effectivement affichés ; budget | I/S ; L pour Legendary Grade 3 uniquement. Pas de lecteur général de bonus |
| Equipment → Weapon → icône diamant | Tout champ apparaissant après identification de la fonction | Classes d'équipement ou autre système éventuel | C : T « fonction inconnue » ; aucune association classe↔icône certifiée |
| Equipment → Relic → toutes les lignes | Nom, niveau actuel/max, effet exact, valeur et unité ; coût, taux de succès si affiché | Bonus de reliques et coût/gain attendu | S : Extra Dmg, CRIT Dmg, Extra HP, Extra HP Recovery, ATK SPD observés ; liste défile jusqu'à Crown of the Great Mountain. Pas de lecteur numérique ; liste complète des noms/effets restant à transcrire |
| Relic → icônes diamant/temple | Tous libellés/valeurs après identification | Progression additionnelle éventuelle | C : deux fonctions non explorées T |
| Equipment → Spirit | Trois Partner Spirits : identités, niveaux, rangs/évolution, actifs ; collection possédée ; chaque effet équipé/possédé et compétence, valeurs/unités/conditions | Bonus actifs, synergies de compétences, budget d'évolution | S : trois niveaux, preset, collection ; noms et effets non transcrits exhaustivement ; aucun lecteur numérique |
| Spirit → chaque fiche / toutes les lignes | Niveau/max, effet exact, compétence, déclenchement, durée et cooldown si affichés, coût et matériaux | Calcul de contribution et progression de chaque spirit | R ; accès aux fiches et défilement sûr non calibrés (T : grille +/− interdite) |
| Equipment → Accessories → Black Orb | Niveau/progression de l'orbe ; compteur sous l'orbe avec unité à identifier ; chaque accessoire élémentaire, rareté, niveau, équipé/possédé | Progression, budget et bonus élémentaires | S ; quatre accessoires Mythic visibles ; aucun lecteur numérique ; compteur sous orbe non identifié comme monnaie certaine |
| Black Orb → chacun des quatre accessoires → carte | Identité/élément, niveau/rareté, effet principal et **chacune des quatre lignes** de bonus, Bonus Effect : libellé exact/valeur/unité, actif et verrou éventuel | Distinguer Dmg et **Amplify** ; appliquer seulement les bonus actifs et les bonnes portées | S : Bracelet of Freedom, Wind Dmg, trois Amplify All Attributes Dmg, Amplify Fire Dmg ; pas de lecteur. Préserver les lignes identiques distinctement, ne pas les fusionner en un multiplicateur sans preuve |
| Black Orb → Obtain | Nombre de plumes noires et conditions/coûts affichés éventuels | Budget/débit d'entrée du contenu correspondant | C : aucun exemple Obtain ; accès interdit car dépense possible ; U feather_black pending |

## Equipment → Weapon → Soul Weapon → Engraving

| Niveau d'accès | Champs précis à scanner ; unité | Calcul / rôle | Couverture et preuve |
|---|---|---|---|
| Soul Weapon → toute la liste | Identité stable, nom réellement affiché, sélection, E/Equip/Unequip, Owned entier ; disponibilité, couleur d'âme, prix de fabrication et conditions si affichés | Arme réellement équipée, faisabilité/budget ; différencier sélection et équipement | L : `soul_weapon.name/tag/owned/rows/equipped_badge` partiels ; G publie sélection et équipée seulement ; noms non uniques possibles. Couleurs et conditions W/C à vérifier |
| Carte Soul Weapon | Chaque Equip Effect avec libellé exact/valeur/unité (ATK affiché), Eliminate monster actuel/requis ; récompense Harvest et coûts si affichés | Bonus effectif, progression de récolte et gain attendu | S pour Owned et compteur de monstres ; pas de lecteur numérique général d'Equip Effect ou récolte ; ne pas Harvest pour mesurer |
| Engraving → en-tête/grille | Nom d'arme ; taille 4×4/5×5 ; masque des cellules actives ; pour chaque cellule : vide/pièce/hors masque ; liens formant chaque pièce placée | Joindre recette, vérifier couverture/chevauchement et complétion | L : E, G/P ; grille **5×5 seulement** calibrée. Les recettes 4×4 W ne rendent pas leur lecteur disponible |
| Engraving → Completion Effect | ATK % et HP % tels qu'affichés ; activation de la complétion à vérifier par état de grille ; autres effets si observés | Bonus conditionnels de remplissage complet | S pour les deux lignes ; valeurs W en table, aucun lecteur numérique de ces deux bonus |
| Engraving → barre/niveau global | Niveau entier, progression actuel/requis ou % avec unité exacte | Progression des pièces/options et futur temps d'amélioration | S : niveau global transcrit ; un `level` sur une carte n'est pas ce niveau ; pas de lecteur global |
| Engraving → **les 8 cartes indexées 0–7** | Forme, dessin/cellules, orientation, niveau entier, cadenas ouvert/fermé/inconnu, E présent/absent, icône Additional Option, luminosité | Faisabilité et sélection des meilleures pièces, vérification des verrous et placements | L : E `cards` pour ces attributs. Sous popup ou carte déverrouillée brillante, certaines valeurs restent inconnues ; sous 480×1040 les lecteurs fins refusent les valeurs. G ne persiste que la grille, pas cet inventaire complet |
| Engraving → popup de **chaque carte** | Niveau ; **Engraving Effect** : chaque libellé et valeur/unité ; **Additional Options** : chaque libellé et valeur/unité ; cadenas ; identité de carte liée à son index | Calcul réel de ATK/Gold/etc. apporté par chaque pièce ; comparaison quantitative | L seulement présence popup, cadenas, présence du mot Gold. **Aucun lecteur des valeurs numériques des effets/options**. Relever le texte entier est indispensable |
| Engraving → placement | Orientation et cellules visées, carte source, preview valide/invalide | Validation géométrique et association carte↔pièce | L : E preview. La carte peut dessiner la forme de base ; ne pas déduire sa rotation placée du seul dessin miniature |

**Piège de données connu :** `engravings.json.shapes` contient une association
communautaire forme→stat, et l'ancien commentaire de `engraving_screen.py` la
reprend. A indique explicitement que l'icône est l'**Additional Option de la
pièce**, pas sa forme. Un I ne prouve donc pas Monster Gold ; un L ne prouve
pas ATK. Conserver séparément forme, niveau, Engraving Effect et chaque
Additional Option. Le lecteur `kind` ne connaît que les apparences coin/épée
calibrées ; ses autres sorties inconnues ne signifient pas « aucun effet ».
Les couleurs de pièces des recettes sont des repères de la feuille source,
pas des propriétés de bonus des cartes.

La table W cite le dépôt communautaire
[SlayerLegendWiki](https://github.com/BenDol/SlayerLegendWiki), révision
`c99f223c05efe9bb6cdcf58add982961b782fd9b`, et une feuille de solutions.
Ses `verified_in_game: false`, `colour_deduced`, `wiki_check` et ambiguïtés
restent à conserver. Des recettes complètes et le maximum de barres ne prouvent
pas le meilleur rendement mesuré : les niveaux et options des cartes comptent.

## Companion → chaque compagnon, Advancement, Beast

| Accès | Champs précis à scanner ; unité | Calcul / rôle | Couverture et preuve |
|---|---|---|---|
| Companion → Ellie / Zeke / Miho / Luna | Identité, niveau/max, progression actuel/requis, effet(s) affiché(s), actif/possédé et coûts d'amélioration si présents | Bonus de compagnon, budget de progression | C/R : portraits catalogués, aucun lecteur de leurs valeurs ; ne pas traiter la capture `companion.png` comme preuve des pages individuelles |
| Chaque compagnon → PASSIVE | Trois passifs : pour chacun identité/libellé exact, niveau actuel/max, effet/valeur/unité, coût du prochain niveau et condition d'activation si affichés | Contribution passive et gain/coût | D confirme structure des niveaux ; aucun exemple identifié ni lecteur |
| Chaque compagnon → PASSIVE II | Les trois mêmes ensembles de champs pour les trois passifs de ce deuxième onglet | Même dépendance, identité distincte par onglet | C/D ; aucun lecteur |
| Chaque compagnon → PASSIVE III | Les trois mêmes ensembles de champs pour les trois passifs de ce troisième onglet | Même dépendance, identité distincte par onglet | C/D ; aucun lecteur |
| Companion → Advancement → I / II / III / IV / V → toutes les lignes | Pour chaque entrée et compagnon : identité, tier, niveau/étoiles/rang si affichés, actif/débloqué, conditions, **chaque bonus chiffré et sa portée**, coût | Modificateurs d'Advancement ; comparaison de progression | S : cinq tiers et noms de la première rangée ; défilement mesuré jusqu'aux silhouettes tier V. Les noms seuls ne sont pas des coefficients ; aucun lecteur de bonus |
| Companion → Beast → chaque fiche | Identité/type, rareté/étoiles/niveau si affichés, équipé/possédé ; compétence/effets/valeurs/unités, durée/cooldown/conditions ; coûts | Contribution Beast et synergies | C/R : écran connu, détails de bonus non inventoriés ; aucun lecteur |
| Beast → Mount | Monture active, type, Affection niveau + actuel/requis, capacité utilisée/max ; chaque bonus avec unité | Effets actifs, progression d'affection | S : Stone Rune Golem, Magic, Affection, Mount ; aucun lecteur de valeurs |
| Beast → Scouting → chacune des trois régions | Région, temps restant/fin, durée, Scout Reward, état disponible/en cours/terminé, Bonus Beast et étoiles de la sélection | Rendement par expédition/temps, calendrier et choix des beasts | S : trois régions, durées/récompenses ; S instructions : étoiles et Bonus Beast augmentent la récompense, une expédition/jour/région, rotation hebdomadaire. Aucun coefficient mathématique établi |

Il faut **36 passifs** : 4 compagnons × 3 onglets × 3 passifs, donc 12 écrans,
9 niveaux par compagnon. Conserver la clé `(compagnon, onglet, position)` même
avant que tous les noms/effets aient été lus. Les noms et unités exacts de ces
36 effets sont **inconnus dans les preuves locales** ; une liste prétendant les
nommer tous serait inventée. Voir D, paragraphe « Companion → … PASSIVE ».

## Skill et ses sous-écrans

| Accès | Champs précis à scanner ; unité | Calcul / rôle | Couverture et preuve |
|---|---|---|---|
| Skill → grille complète | Identité de chaque skill, élément/type, niveau/max, cartes actuel/requis, équipement/slot actif, coûts | Définition du loadout, budget et effets au niveau courant | S : quelques fractions de cartes ; défilement de toute la grille non calibré, pas de lecteur complet |
| Skill → fiche de chaque skill | Chaque description/effet : coefficient de dégâts et unité, hits/cibles, durée, cooldown, coût de mana, conditions/proc et passif/actif si affichés | DPS théorique, couverture et cycle de compétences | R : ces champs sont à confirmer sur fiches, aucune formule ou valeur précise prouvée localement |
| Skill Proficiency | Niveau, progression actuel/requis ; All Attributes Dmg et chaque autre effet | Modificateur élémentaire et progression | S pour ces champs, aucun lecteur numérique |
| Skill → Familiar | Attribute/Battle/Weapon Familiar : identité par slot, niveau/rang, chaque compétence/bonus, valeurs/unités/conditions, preset | Modificateurs actifs du preset | S pour trois types de slot et preset ; détails R, pas de lecteur |
| Skill → Skill Refinement Grounds | Skill par slot, verrou des slots, temps restant/requis, progression/charges, résultat/effet affiché | Budget/temps de raffinement et effet sur skill | S : trois slots Hellfire Slash dont deux verrouillés, temps/compteur ; pas de lecteur, pas de raffinement pour scanner |
| Skill → Skill Mastery → chaque branche/nœud | Identité, acquis/niveau/max, effet exact/unité, prérequis/coût ; monnaie et EXP actuel/requis | Bonus de mastery, budget d'allocation | S pour quelques niveaux de nœuds, compteur et EXP ; arbre complet/défilement non calibré, pas de lecteur |
| Skill → Rave / Mantra → fiches | Niveau, acquis/actif ; tous effets chiffrés, durée/cooldown/conditions, coûts si affichés | Compétences spéciales, cycle de combat | S pour noms seulement ; valeurs et fonctionnement R |

## Adventure, Select Region, Dungeon

| Accès | Champs précis à scanner ; unité | Calcul / rôle | Couverture et preuve |
|---|---|---|---|
| Battle → Select Region → chaque région/stage | Région ; numéro/nom de stage, verrou/déverrouillage/clear explicite ; monstres/vague ; drop type/grade ; couleur d'âme ; information `i` si disponible | Choix du stage, jonction au rendement mesuré et plafond d'accès | L pour région et stage observé ; W pour caractéristiques de table. **Move visible ne prouve pas clear**, ni le maximum atteint ; future lecture d'accès explicite requise |
| Select Region / combat | HP/défenses/résistances des ennemis, récompenses gold/EXP, probabilités/quantités de drops, vitesse des vagues si affichées | Modèle théorique de rendement et seuil de kill | R : non prouvé dans le catalogue ; ne pas déduire ces quantités du seul mpw |
| Adventure → carte → chaque région → quêtes I–X | Quête/état, récompenses séparées par ressource, quantités ; coût d'entrée et difficulté si affichés | Budget des ressources et récompenses disponibles | S : quêtes/récompenses/Reward Claimed ; aucun lecteur numérique. Carte Adventure différente de Select Region |
| Adventure → Story → Main Easy/Normal/Hard et Sub | Épisode, complétion/verrou, récompense/bonus et conditions s'ils sont affichés | Conditions d'accès et bonus éventuels | S : noms et Complete sur certaines branches ; aucun bonus permanent déduit d'une histoire terminée |
| Dungeon → Closed Mine → floor → area → plumes | Étage, area, coût 1/2/3 plumes blanches, solde, Repeat entry actuel/max, progression/temps et récompenses ; état Gold scroll | Rendement par entrée/plume/heure, autonomie, arrêt à épuisement | Lecteurs de navigation spécialisés `mine.py`, état limité G ; soldes/plumes U pending. S pour propositions et absence de scroll ; récompenses/durée R |
| Dungeon → Shelter of Sleeping flame | Choix Dragon Power/Dragon Spark, difficulté, coût d'entrée, solde de plumes, gains affichés | Budget de progression dragon, rendement par entrée | S pour ressources proposées/solde ; coûts/gains détaillés R ; U pending |
| Dungeon → Dimensional Rift | Boss, difficulté, bonus %, coût en plume violette, solde ; récompenses et temps si affichés | Rendement et comparaison de difficulté | S pour difficulté/bonus/coût/solde ; aucun lecteur ; bonus 55% observé ne définit pas sa formule |
| Dungeon → Forest of Circulation | Niveau choisi, cleared/unlocked, dernière entrée, coût/plumes, récompenses | Rendement de ressources et plafond d'accès | S pour niveaux/clear ; coût/gains R |
| Dungeon → Kingdom of Aslan | Square, état Normal/Smooth, niveau/difficulté et gains/coûts si affichés | Progression et rendement du contenu | S pour Square 1–20 et états ; effet mathématique des états inconnu |
| Dungeon → Training Cave | Area, précédente entrée, Max Clear ; coûts, gains EXP/ressources, durée si affichés | EXP par entrée/temps et limite d'accès | S pour areas/Max Clear ; gains/coûts R |
| Dungeon → Dragon Valley | Destination réellement reconnue ; champs du contenu réellement ouvert | Éviter de joindre les mauvaises récompenses | T : l'entrée connue mène à Airfield ; Raid camp historique sans entrée actuelle connue, aucune statistique de Raid supposée disponible |

## Guild, Airfield, Shop, Quest, autres branches

| Accès | Champs utiles à relever ; unité | Calcul / rôle | Couverture et preuve |
|---|---|---|---|
| Adventure → Guild → Divine Beast | Niveau, Connection actuel/max ; chaque bonus et condition active, valeur/unité | Modificateurs de guilde actifs | S pour niveau/connection ; bonus R et pas de lecteur |
| Guild → Airfield → recettes Appetizer/Main Dish/Dessert | Recette/ingrédients, quantités/coûts, résultat, chaque bonus et durée s'ils sont affichés | Budget de cuisine et bonus temporaires | S pour noms de recettes ; aucun lecteur de bonus, aucune recette réalisée pour scanner |
| Airfield → Boarding Status | Destination, durée/fin d'embarquement, coût et récompenses si affichés | Calendrier et rendement d'envoi | S pour destinations/temps ; coûts/gains R |
| Guild → Request | Objectif actuel/requis, récompenses disponibles/prises, cycle et limites | Budget de récompenses | S pour progression et WANTED I–VI ; pas de lecteur |
| Guild Shop Normal/Appearance | Soldes concernés, prix, quantité par lot, limites et reset ; effets d'apparence possédée/équipée si explicitement affichés | Budget/échange et bonus éventuels | S pour catégories/articles ; aucun bonus de skin présumé, pas de lecteur complet |
| Shop → Summon Equipment/Relic | Niveau de summon/progression, coût par lot, quantité, probabilités par rareté et garantie si un affichage existe | Coût attendu d'acquisition, budgets | S pour coûts de relic x1/x11 ; probabilités/garanties R, pas de lecteur |
| Shop → Goods/Golden Key/Event/Package | Prix dans son unité, quantités par ressource, solde Golden Keys, limite et expiration ; bonus/durée explicites | Conversion de ressources, budget d'événement | S pour certains articles/coûts/solde/états ; pas de lecteur. Pas de prix réel ni de budget d'achat inféré |
| Battle → Quest → Daily/Repeat/Achievement | Quête identifiée, actuel/requis, ressource/quantité de récompense, complétée/claimée, reset/limite | Progression et budget de récompenses | L pour titre/onglet seulement (`screens.quest_tab`) ; S pour noms, valeurs/barres/claim non calibrés |
| Character/Equipment/Skill/Adventure : ressources secondaires | Crystals, Dice, quatre Elemental Stones, White/Green/Purple/Black Feathers, Dragon Power, Dragon Spark, Black Mana : soldes exacts et unités ; coûts associés sur l'écran source | Budget de tous les systèmes ci-dessus | U : tous ces soldes pending. Le registre n'établit pas pour chacun un écran source calibré |
| Top menu → Collection/Achievements ; Event ; icônes inconnues | Identité et bonus/cumul/état actif de chaque entrée **si observés** | Bonus permanents ou temporaires potentiels | C : accès top menu interdit ; placement Collection/Achievements non mesuré ; Event non exploré. Ne pas prétendre en connaître les coefficients |

Ne sont pas des entrées de formule en elles-mêmes : coordonnées des boutons,
flèches, X, couleurs d'onglet, identité de comptes, chat, classement, membres de
guilde, annonces, page de connexion/sauvegarde, offres, maintenance et dialogue
de sortie. Elles servent à reconnaître/naviguer ou interrompre le scan. Un
compteur de membres n'entre pas dans les dégâts sans règle de bonus observée.

## Contrat minimal pour une donnée de calcul exploitable

Chaque observation garde le chemin d'accès, l'identité stable de l'objet et du
slot, le libellé affiché, le texte brut, la valeur normalisée sans perte,
l'unité (%/points/ratio/secondes/monnaie), l'instant **de capture**, la résolution
numérique, l'état actif/possédé/équipé, le preset/contexte, la source et la preuve
de calibration. Garder `inconnu` distinct de zéro, niveau maximal, non possédé,
inactif et illisible. Les bonus portant des noms proches (Dmg, Extra Dmg,
Amplify Dmg, All Attributes Dmg) restent distincts tant que leur combinaison
n'est pas démontrée. Le même effet affiché plusieurs fois conserve ses lignes.

Pour les futurs calculs d'amélioration, relever l'avant, l'aperçu du prochain
niveau et le coût lorsqu'ils sont consultables sans achat. Pour les calculs de
dégâts/rendement théoriques, exiger une preuve des opérations (addition,
multiplication, plafonds, proc) et des conditions avant de coder une formule.
Pour les débits mesurés, conserver les changements de stage/loadout/buffs et
les dépenses afin de ne pas comparer des contextes incompatibles.

La prochaine complétion documentaire porte sur les champs R/C : nommer chaque
ligne à partir d'une vraie capture, puis rattacher un lecteur et ses tests à
chacune. Le simple fait d'ajouter un écran à l'arbre ne complète aucun de ces
champs numériques. Ce document ne modifie pas les autorisations de navigation.
