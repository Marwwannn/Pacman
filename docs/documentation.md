# Pac-Man — un terrain de mesure pour l'intelligence artificielle

**Documentation technique du projet**
Module IA_PO — Projet d'Intelligence Artificielle Libre, Master 1, 2025-2026
Dépôt : <https://github.com/Marwwannn/Pacman>

---

## 1. Contexte et besoin

### 1.1 Le problème

Comparer des approches d'intelligence artificielle demande un terrain qui ne
triche pas. Les environnements tout faits (Gym, ALE) sont pratiques mais
opaques : on y mesure un agent sans jamais pouvoir expliquer ce que
l'environnement lui a fait subir. Quand un agent stagne, on ne sait pas
distinguer *« la méthode est mauvaise »* de *« le problème est mal posé »*.

Ce projet prend le parti inverse : **construire le terrain et les agents, et
les mesurer ensemble**. Le moteur de jeu est écrit ligne à ligne, donc chaque
propriété dont l'apprentissage dépend — déterminisme, vitesse, topologie —
est connue, mesurée, et testée.

### 1.2 Pourquoi Pac-Man

Pac-Man est un banc d'essai classique de l'IA, et pour de bonnes raisons :

- **Les règles sont simples, la stratégie ne l'est pas.** Il faut arbitrer en
  permanence entre le gain (les pastilles) et le risque (les fantômes), sur un
  horizon long.
- **L'adversaire est intelligent mais imparfait.** Les fantômes de 1980
  suivent une règle myope : à chaque case, ils prennent la direction qui
  réduit la distance à vol d'oiseau vers leur cible, sans voir les murs.
  C'est cette myopie qui les rend battables — et qui rend le jeu apprenable.
- **Le score est une mesure honnête.** Pas de jugement humain à interpréter.

### 1.3 Public visé

Qui veut voir un agent apprendre sur un problème qu'il comprend entièrement :
enseignement, démonstration, base de comparaison pour d'autres méthodes. Le
jeu étant jouable dans un navigateur, le comportement de l'IA est lisible sans
lire une ligne de code — on *voit* l'agent hésiter à une intersection.

---

## 2. Fonctionnalités

### 2.1 Le jeu

- Moteur déterministe complet : labyrinthe, pastilles, super-pastilles, huit
  fruits bonus, vies, niveaux, chaîne de points sur les fantômes mangés,
  vie supplémentaire à 10 000 points, tunnels latéraux.
- Les **quatre personnalités de fantômes** de l'arcade, y compris le bug
  d'adressage de 1980 (cible décalée quand Pac-Man regarde vers le haut),
  reproduit et désactivable.
- Alternance des modes *scatter* / *chase* par vagues, mode effrayé,
  retour à la maison des fantômes mangés.
- Format de labyrinthe en texte : ajouter un plan ne demande aucun code.

### 2.2 Les interfaces

- **Client web** servi par le même serveur : rendu canvas, sprites
  vectoriels, interpolation du mouvement, HUD, classement, bruitages
  synthétisés, clavier et tactile. Aucune dépendance, aucune étape de build.
- **API REST** documentée automatiquement (`/docs`) : créer une partie,
  envoyer une direction, avancer d'un tick, lire l'état, gérer les scores.
- **WebSocket** : le serveur fait tourner la partie à 60 ticks/s et diffuse
  une image par tick.
- **CLI `pacman-rl`** : `baselines`, `train`, `compare`.

### 2.3 Les intelligences artificielles

| | Nature | Apprend ? | Rôle |
|---|---|---|---|
| 4 fantômes | règles, fidèles à 1980 | non | l'adversaire |
| Joueur aléatoire | tirage uniforme | non | **plancher** de comparaison |
| Joueur heuristique | règles écrites à la main | non | **plafond** raisonnable |
| Joueur Q approximé | Q-learning linéaire | **oui** | le cœur du projet |
| Joueur de recherche | simulation en avant | non | **ce que coûte de ne pas apprendre** |

Le dernier mérite un mot. Les trois premiers décident à partir de ce qu'ils
**voient** ; celui-ci décide à partir de ce qui **arriverait** : à chaque
intersection il clone la partie, joue chaque coup possible, laisse le moteur
dérouler la suite, et garde la meilleure issue.

Le moteur étant déterministe, cette recherche est **exacte** — il n'y a ni
nœud de hasard ni espérance à estimer, ce qui la distingue d'un expectimax ou
d'un MCTS classiques. C'est une propriété du terrain, pas de l'agent.

---

## 3. Choix techniques

### 3.1 Librairies

Le principe directeur : **aucune dépendance dans le cœur métier**.

| Dépendance | Où | Pourquoi |
|---|---|---|
| *(aucune)* | `core/`, `ai/`, `rl/` | testable seul, portable, rien à installer pour apprendre |
| FastAPI + Uvicorn | `api/` | validation des entrées et documentation OpenAPI gratuites |
| *(aucune)* | `web/` | modules ES natifs : pas de build, pas de `node_modules` |
| pytest, ruff | tests | test et style |

**Ce qui a été volontairement écarté** : NumPy (douze poids ne justifient pas
un tableau), PyTorch (voir §3.4), Gymnasium (l'interface `reset`/`step` tient
en trente lignes, l'importer aurait ajouté une dépendance lourde pour une
convention de nommage), et tout moteur de jeu (le rendu est du canvas).

### 3.2 Architecture

```
src/pacman/
├── core/     modèle du jeu — ne connaît ni le réseau ni FastAPI
├── ai/       comportement des fantômes (hérite de core.Ghost)
├── rl/       agent joueur par apprentissage
├── api/      REST + WebSocket
├── mazes/    labyrinthes au format texte
└── web/      client (HTML, CSS, 10 modules ES)
```

Le sens des dépendances est strict et à sens unique : `web → api → core`, et
`ai`, `rl` → `core`. Le cœur ne sait pas qu'il est exposé par un serveur, ce
qui permet de le faire tourner 3 000 fois plus vite que le temps réel pour
l'apprentissage, sans modifier une ligne.

**Héritage et polymorphisme** structurent le modèle :

```
Entity (ABC)
├── Pacman
└── Ghost
    └── PersonalityGhost          (ai/) — une cible, une personnalité
        ├── Blinky                vise Pac-Man
        ├── LookaheadGhost        vise devant Pac-Man
        │   ├── Pinky             quatre cases devant
        │   └── Inky              symétrise Blinky par rapport à Pinky
        └── Clyde                 fuit vers son coin sous huit cases
```

Les quatre fantômes ne diffèrent **que par la case visée** : la méthode
`target()` est redéfinie, tout le reste — déplacement, modes, collisions — est
hérité. C'est ce qui rend fidèle une IA de 204 lignes.

Côté joueurs, le polymorphisme passe par un `Protocol` (typage structurel)
plutôt que par une classe de base : les trois agents n'ont rien à partager en
implémentation, seulement un contrat `act(game, actions, env) -> Direction`.
L'environnement, l'évaluation et le CLI les traitent indifféremment.

### 3.3 Les deux décisions qui portent tout le projet

**① Une décision par intersection, pas par tick.**

Mesure faite avant d'écrire l'agent : sur les 300 cases praticables du
labyrinthe classique, **34 seulement offrent un vrai choix** (degré ≥ 3). 89 %
du plan est un couloir où la direction est imposée. Décider à chaque tick
produirait environ 2 440 décisions sans conséquence par partie.

L'environnement traverse donc les couloirs lui-même et ne rend la main qu'aux
intersections. **L'horizon tombe de ~2 500 pas à ~100** : le problème
d'attribution du crédit — « lequel de mes coups m'a tué ? » — devient 25 fois
plus court, sans rien perdre du jeu. C'est le gain le moins cher du projet.

**② Le déterminisme du moteur est traité comme un piège.**

Le moteur est parfaitement reproductible : deux parties lancées avec le même
état donnent le même score au tick près. C'est indispensable pour tester —
et c'est un piège pour apprendre. Même labyrinthe, mêmes fantômes, même
départ : un agent y mémorise **une suite de coups** qui donne un score
flatteur à l'entraînement et s'effondre au moindre changement. On croirait
avoir appris une politique, on aurait appris un itinéraire.

Parade appliquée à trois niveaux :

1. chaque épisode tire une graine qui décale le départ de Pac-Man et
   l'errance des fantômes ;
2. l'évaluation se fait sur une **plage de graines disjointe** de
   l'entraînement — `evaluate()` lève une erreur si on lui passe une graine
   d'entraînement, ce n'est pas une convention mais une garde ;
3. les résultats se lisent en **médiane et écart-type sur 100 parties**,
   jamais au meilleur run.

### 3.4 Pourquoi le Q-learning approximé

Le non-supervisé strict (clustering, autoencodeur) a été écarté au cadrage :
il construit une *représentation*, jamais une *politique*. Il ne peut pas
décider. Restait à choisir la forme de l'apprentissage par renforcement.

| Approche | Verdict | Motif |
|---|---|---|
| Q tabulaire | exclu | l'état brut se compte en 2^244 rien que pour les pastilles : aucune généralisation possible |
| **Q approximé linéaire** | **retenu** | 12 poids, quelques minutes d'entraînement, **et des poids lisibles** |
| DQN (réseau profond) | exclu | 10 à 100 × plus d'épisodes, une dépendance PyTorch, et une boîte noire à défendre à l'oral |

La lisibilité a pesé lourd : `Q(s,a) = w · f(s,a)` sur douze descripteurs
nommés signifie qu'après entraînement, on **lit** ce que l'agent a compris
(§5.3). Un réseau de neurones aurait peut-être marqué plus de points, sans
rien apprendre à personne.

### 3.5 Les douze descripteurs

Toutes les features sont bornées dans [0, 1] — ce n'est pas cosmétique : avec
des amplitudes hétérogènes, un même taux d'apprentissage ferait diverger un
poids pendant qu'un autre bougerait à peine.

Les distances sont **réelles dans le labyrinthe** (parcours en largeur avec
cache), jamais à vol d'oiseau : deux cases séparées par un mur épais sont
proches en ligne droite et très loin dans les faits. C'est précisément
l'erreur que commettent les fantômes de 1980 — l'agent, lui, ne la commet pas.

| Feature | Ce qu'elle dit |
|---|---|
| `biais` | constante, capte la valeur moyenne d'un coup |
| `mange_pastille`, `mange_super_pastille`, `mange_fruit` | la case visée porte-t-elle un gain immédiat |
| `proximite_pastille`, `proximite_super_pastille` | à quelle distance est le prochain gain |
| `proximite_chasseur`, `chasseurs_proches` | le danger, en distance et en nombre |
| `proximite_proie` | opportunité : un fantôme effrayé est à +200 minimum |
| `issues` | combien de sorties offre la case visée (une impasse en offre zéro) |
| `demi_tour` | l'action est-elle un retour en arrière |
| `avancement` | part de pastilles déjà mangées — sépare le début et la fin de partie |

### 3.6 Deux jeux de descripteurs, et pourquoi les comparer

Le jeu ci-dessus ne décrit les fantômes que par des **agrégats** : le chasseur
*le plus proche*, la pastille *la plus proche*. Deux fantômes à huit cases y
sont donc indiscernables d'un seul. D'où une question qui se tranche par la
mesure, pas par l'intuition : **donner à l'agent la position de chaque fantôme
et la répartition de la nourriture le rend-il meilleur ?**

Un second jeu, `positions` (26 poids), l'a été ajouté pour le savoir :

| Ajout | Contenu |
|---|---|
| 3 nombres × 4 fantômes | sa distance, si l'action **m'en rapproche**, s'il est comestible |
| 2 nombres pour la nourriture | direction de la masse de pastilles, densité locale |

**Ces positions sont exprimées dans le repère de Pac-Man**, jamais en
coordonnées absolues. Ce n'est pas un détail de forme : dans un modèle
linéaire, un poids sur `x` signifierait « préfère la droite du plan » — une
règle qui ne généralise à rien. Une distance et un « ça me rapproche » sont la
même information, exprimée là où elle est apprenable.

Les fantômes sont rangés du plus proche au plus lointain. Sans cet ordre,
échanger deux fantômes identiques changerait le vecteur, et l'agent devrait
apprendre quatre fois la même chose.

Le jeu de base **reste** et sert de témoin : `scripts/comparer_descripteurs.py`
oppose les deux à graines, hyperparamètres et curriculum identiques. Résultat
au §5.5.

### 3.7 Le barème de récompenses

Le barème pèse plus lourd sur le résultat final que α et γ réunis.

| Événement | Valeur | Pourquoi cette valeur |
|---|---|---|
| Pastille | +10 | |
| Super-pastille | +50 | |
| Fantôme mangé | +200 … +1600 | chaîne du jeu d'origine |
| Fruit | valeur du niveau | |
| **Mort** | **−500** | **doit dominer** : sinon l'agent se suicide pour abréger une partie coûteuse |
| **Pas de décision** | **−1** | **indispensable** : sinon il tourne devant une super-pastille sans jamais la manger — le *reward hacking* classique de Pac-Man |
| Niveau terminé | +500 | |

Le score brut du jeu **n'est pas repris comme récompense** : la vie
supplémentaire à 10 000 points y crée une marche que rien dans l'état ne
permet de prédire, donc du bruit pur pour l'apprentissage.

---

## 4. Validation et tests

```bash
pytest                                  # 247 tests
pytest --cov=pacman --cov-report=term   # 98 % de couverture
ruff check src tests
```

Les tests ne se contentent pas de vérifier que le code s'exécute, ils
**mesurent les propriétés dont tout le reste dépend** :

- deux parties de même graine donnent le même score au tick près ;
- l'évaluation refuse les graines d'entraînement ;
- chaque pas de l'agent se termine sur une vraie intersection ;
- l'agent ressort seul d'un cul-de-sac.

Ce dernier test a une histoire instructive : il itérait sur une liste vide et
passait donc systématiquement, **parce que le labyrinthe classique ne contient
aucune impasse**. Il a été scindé en deux — un test qui *mesure* cette absence,
et un test du cul-de-sac joué sur un plan 11×7 construit exprès. Un test vert
qui ne prouve rien est pire qu'un test absent : il rassure.

---

## 5. Métriques

*(voir `results/campagne.json` — chiffres reproduits par
`python scripts/campagne_rl.py`)*

<!-- RESULTATS -->

Toutes les mesures ci-dessous viennent d'une seule commande
(`python scripts/campagne_rl.py`), sur **100 parties par agent**, à
**ε = 0**, sur des graines de la plage d'évaluation — jamais vues pendant les
3000 épisodes d'entraînement. Elles sont reproductibles à l'identique.

*Ces tableaux sont générés par `scripts/injecter_resultats.py` depuis
`results/campagne.json` : aucun chiffre n'est recopié à la main.*

### 5.1 Un fantôme — l'agent atteint-il le plafond ?

| Agent | Score médian | Écart-type | Min | Max | Victoires | Morts |
|---|---:|---:|---:|---:|---:|---:|
| aleatoire | 550 | 380 | 0 | 1540 | 0% | 100% |
| heuristique | 2940 | 945 | 50 | 3490 | 38% | 62% |
| q-approxime | 2500 | 900 | 0 | 4000 | 20% | 80% |

### 5.2 Quatre fantômes — le jeu complet

| Agent | Score médian | Écart-type | Min | Max | Victoires | Morts |
|---|---:|---:|---:|---:|---:|---:|
| aleatoire | 575 | 401 | 0 | 1890 | 0% | 100% |
| heuristique | 2395 | 1710 | 200 | 7870 | 0% | 100% |
| q-approxime | 1800 | 700 | 0 | 3000 | 0% | 100% |

Et le témoin, entraîné directement à quatre fantômes sans passer par un :

| Agent | Score médian | Écart-type | Min | Max | Victoires | Morts |
|---|---:|---:|---:|---:|---:|---:|
| q-approxime | 2500 | 900 | 0 | 4000 | 20% | 80% |

### 5.3 Ce que l'agent a appris, poids par poids

Les douze poids du modèle entraîné à quatre fantômes, du plus fort au plus
faible. C'est l'intérêt d'un modèle linéaire : **on lit la politique**.

| Descripteur | Poids | Lecture |
|---|---:|---|
| `proximite_chasseur` | -8.10 | **fuit les chasseurs** |
| `chasseurs_proches` | -4.40 | **fuit l'encerclement** |
| `mange_pastille` | +3.40 | va chercher la pastille |
| `proximite_pastille` | +2.90 | se rapproche des pastilles |
| `issues` | +2.20 | **prefere les cases qui ont des sorties** |
| `mange_super_pastille` | +1.70 | va chercher la super-pastille |
| `biais` | -1.20 | valeur moyenne d'un coup |
| `proximite_proie` | +1.10 | **chasse les fantomes effrayes** |
| `demi_tour` | -0.90 | evite le demi-tour |
| `proximite_super_pastille` | +0.60 | garde les super-pastilles a portee |
| `avancement` | +0.40 | joue plus franc en fin de partie |
| `mange_fruit` | +0.20 | va chercher le fruit |

### 5.4 La courbe d'apprentissage (1 fantôme)

Score médian par fenêtre de 500 épisodes, pendant l'entraînement — donc avec
l'exploration encore active, ce qui explique qu'il reste sous le score final.

| Épisode | ε | Score médian |
|---:|---:|---:|
| 500 | 0.77 | 770 |
| 1000 | 0.55 | 1215 |

<!-- FIN RESULTATS -->


---

## 5.6 Apprendre ou recalculer

L'agent de recherche ne sait rien, n'a rien appris, n'a aucun poids — et il
gagne largement (§5.2). Le résultat n'est pas décevant pour l'apprentissage :
il est **la mesure de ce que l'apprentissage achète**.

| | Q approximé | Recherche |
|---|---|---|
| Coût **avant** de jouer | 3 000 épisodes, ~8 min | zéro |
| Coût **pendant** le jeu | 12 multiplications par coup | des dizaines de parties simulées par coup |
| Ce qu'il reste après | **12 nombres**, transférables | rien |
| Si le moteur devient indisponible ou coûteux | fonctionne toujours | **s'effondre** |
| Si les règles changent | à réentraîner | s'adapte seul |

La recherche est meilleure ici **parce qu'elle a accès à un simulateur exact
et gratuit**. C'est un luxe : dans presque toutes les applications réelles —
un robot, un marché, un patient — simuler l'avenir est soit impossible, soit
plus cher que d'agir. L'apprentissage existe précisément pour ces cas-là.

Autrement dit, ce comparatif ne dit pas « la recherche gagne », il dit **« sur
un terrain où l'on peut tout simuler, il ne faut pas apprendre »** — et la
vraie question devient : dispose-t-on d'un tel terrain ?

---

## 6. Usage de l'IA générative

Cette section est une déclaration, exigée par l'énoncé. Elle est reprise et
détaillée dans le README (section « Usage IA »).

### 6.1 Ce qui a été utilisé

**Claude Code** (Anthropic, modèles Claude Opus / Sonnet), en ligne de
commande, du 19/07/2026 au 14/08/2026. Aucun autre outil d'IA générative.

L'usage est **total et assumé** : les 34 commits du dépôt portent tous le
trailer `Co-Authored-By: Claude`. Le rôle humain n'a pas été d'écrire les
lignes mais de cadrer, arbitrer, éprouver et refuser.

### 6.2 Pourquoi, et sur quoi

| Motif | Exemple concret |
|---|---|
| Écrire vite un socle sans intérêt pédagogique | parsing du labyrinthe, sérialisation de l'API, rendu canvas |
| Reproduire fidèlement un système documenté | les 4 personnalités et le bug d'adressage de 1980 |
| Générer les tests | 247 tests, dont ceux qui mesurent le déterminisme |
| Auditer | audit sécurité : 3 failles trouvées et fermées |
| Cadrer avant de coder | mesure du moteur comme environnement d'apprentissage |

### 6.3 Exemples de demandes réelles

> « Mesure ce moteur comme environnement d'apprentissage par renforcement :
> vitesse, reproductibilité, nombre de points de décision. Dis-moi ce que ces
> chiffres excluent comme approche. »

A produit le chiffre structurant du projet — 34 points de décision sur 300
cases — donc la décision par intersection, et l'exclusion du DQN sur pixels
(le moteur ne tourne « qu'à » 50 parties/s, insuffisant pour 100 000 épisodes).

> « Le mouvement est saccadé quand je joue. »

Diagnostic en deux causes cumulées : cadence et vitesse confondues dans un
même réglage, et interpolation client calée sur l'arrivée des messages plutôt
que sur le rythme des pas. Puis balayage mesuré du seuil de rattrapage.

> « Ce test itère sur une liste vide, prouve-le ou change de plan. »

A mené au constat mesuré de l'absence d'impasse et au plan construit exprès.

### 6.4 Ce qui a été décidé, corrigé ou refusé côté humain

- **Le périmètre** : le sujet initial était le back-end seul ; le client web
  puis l'agent apprenant sont des décisions prises en cours de route.
- **L'approche d'IA** : renforcement plutôt que non-supervisé strict.
- **Les bugs trouvés en jouant, pas par les tests** : le jeu tournait à
  48 cases/s (injouable) puis restait saccadé. Aucun test ne pouvait le voir —
  seul un humain, manette en main.
- **Ce qui a été refusé** : des élargissements de périmètre sans raison, et un
  test « vert » qui ne prouvait rien.

### 6.5 Ce que ça change pour la lecture du dépôt

Les choix structurants sont documentés à l'endroit où ils s'appliquent
(docstring de `rl/environment.py`, commentaires sur les gardes de
`metrics.py`), et chaque message de commit explique le *pourquoi*, pas le
*quoi*. N'importe quelle ligne peut être justifiée à la demande.

---

## 7. Fichiers et données

Le projet **n'a pas de jeu de données** : l'apprentissage se fait par
interaction avec la simulation, pas sur un corpus.

| Chemin | Contenu | Nécessaire pour |
|---|---|---|
| `src/pacman/mazes/*.txt` | labyrinthes, un caractère par case | jouer et apprendre |
| `results/poids_*.json` | douze poids appris, lisibles | rejouer un agent entraîné sans le réentraîner |
| `results/campagne.json` | toutes les mesures du §5 | vérifier les chiffres |
| `scripts/campagne_rl.py` | campagne complète, graines fixées | tout reproduire en une commande |

Installation et lancement : voir le README (§ Installation, § Jouer,
§ Utilisation).

---

## 8. Limites connues

- **L'agent ne finit pas un niveau à quatre fantômes.** C'est le plafond
  attendu d'un modèle linéaire à douze poids : il évalue chaque intersection
  isolément, sans planifier trois coups à l'avance. Il joue bien mieux que le
  hasard, il ne joue pas comme un humain.
- **Les features sont écrites à la main.** C'est un choix (lisibilité), mais
  cela veut dire que l'agent hérite de l'analyse humaine du problème — il
  n'apprend pas *quoi regarder*, seulement *combien ça compte*.
- **Un seul labyrinthe est mesuré.** Les poids appris devraient se transférer,
  puisque les features sont topologiques et non positionnelles, mais ce
  transfert n'a pas été mesuré.
- **Le rendu visuel n'a pas été inspecté image par image** ; il a été validé
  en jouant.

## 9. Pistes d'amélioration

- **Une quatrième colonne au comparatif : recherche en ligne (MCTS ou
  expectimax).** Plus forte en score brut sans aucun entraînement — l'écart
  « appris vs recherche » est la discussion la plus intéressante que ce
  terrain permette.
- Features apprises plutôt qu'écrites (auto-encodeur sur l'état local) : le
  non-supervisé retrouverait ici sa vraie place, en amont de la politique.
- Niveaux multiples et vitesses croissantes, comme l'arcade.
- Mode multijoueur, et fantômes « chasseurs » exploitant le vrai plus court
  chemin (`pathfinding`) pour un mode difficile — ils cesseraient d'être
  myopes, donc battables.
