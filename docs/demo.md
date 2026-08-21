# Script de la démo vidéo — 5 minutes

> L'énoncé accorde **5 minutes maximum** à la démo. Ce script en fait 4 min 40
> avec de la marge. Chaque durée d'exécution a été chronométrée sur la machine
> de développement le 21/08/2026 — rien ici ne se lance « en espérant ».

## Version courte — 3 écrans, 3 minutes

C'est celle à tourner. La version détaillée plus bas sert si l'on veut aller
jusqu'à 5 minutes.

| | Ce qu'on fait | Ce qu'on dit |
|---|---|---|
| **1. Le jeu** (1 min) | `pacman-server`, ouvrir http://127.0.0.1:8000, jouer 30 s, `Ctrl+C` | « Le serveur Python calcule tout ; le navigateur ne fait qu'afficher. » |
| **2. L'IA joue** (1 min) | dans le navigateur, ouvrir **http://127.0.0.1:8000/?ia=appris** (la partie démarre seule), laisser jouer 40 s ; puis `?ia=recherche` 20 s | « Là, c'est le modèle que j'ai entraîné qui joue, en direct — le serveur décide à chaque croisement, je ne touche à rien. Il bat les règles écrites à la main sur le score, mais il gagne rarement : douze poids ne planifient pas la fin du niveau. L'agent de recherche, qui simule les coups, gagne 94 % — la différence, c'est l'anticipation. » |
| **3. L'IA réfléchit** (1 min) | ouvrir `docs/decisions.html`, lecture 20 s, pause sur un croisement | « On rejoue une partie de l'IA. À chaque croisement, on voit ce qu'elle a envisagé et pourquoi elle a choisi. » |

Rien d'autre à lancer. Une hésitation ne se recommence pas.

## Avant d'appuyer sur REC

```powershell
cd C:\Users\marwy\Documents\MasterTRIED\IA_PO\Projet
.venv\Scripts\activate            # SANS ça, pacman-rl et pacman-server n'existent pas
```

- Terminal en **plein écran, police 18+** (les chiffres doivent se lire en 720p).
- Navigateur : deux onglets **déjà ouverts** — `docs/decisions.html` et
  `docs/documentation.html` (défilé jusqu'au §5.7). On ne cherche pas un fichier
  à l'écran.
- Notifications Windows coupées (Paramètres → Système → Notifications, ou mode
  « Ne pas déranger »).
- Enregistreur : l'**Outil Capture d'écran** de Windows 11 (`Win + Maj + S`,
  puis le bouton caméra), en sélectionnant **tout l'écran**, micro activé. Il
  filme l'écran entier, donc les passages du terminal au navigateur. **Pas la
  Game Bar (`Win + G`)** : elle n'enregistre qu'une seule fenêtre et perd le
  navigateur au premier changement. Tester 10 secondes avant, vérifier que le
  micro capte.
- Une prise d'essai complète avant la vraie : la première est toujours trop
  longue.

## Le fil — une phrase par séquence

| Séquence | Durée | Ce qu'on voit | Ce qu'on dit |
|---|---:|---|---|
| 1. Le jeu | 0:40 | Une partie jouée au clavier | « Un moteur déterministe, le client n'a aucune règle » |
| 2. Les quatre agents | 1:10 | `pacman-rl compare` en direct | « Plancher, plafond, appris — et la recherche » |
| 3. Voir l'agent décider | 1:00 | `decisions.html`, une intersection | « Douze poids, on lit la politique » |
| 4. Les résultats négatifs | 1:10 | `documentation.html` §5.6 et §5.7 | « Trois hypothèses plausibles testées, trois fausses » |
| 5. Usage de l'IA | 0:40 | README, section « Usage IA » | « Déclaré, et ce que j'ai refusé » |

---

## 1. Le jeu — 0:40

```powershell
pacman-server
```

Démarre en **4 s**. Ouvrir http://127.0.0.1:8000 et jouer **20 secondes** —
manger un power pellet, manger un fantôme, c'est tout ce qu'il faut montrer.

**Dire :** « Le moteur est déterministe : aucune horloge, un générateur par
fantôme. Le client envoie des intentions et dessine ce qu'on lui diffuse — il
ne contient aucune règle de jeu, donc il ne peut pas tricher. Ces deux
propriétés sont ce qui a rendu tout le reste possible. »

`Ctrl+C` pour arrêter le serveur. Ne pas s'attarder : le jeu n'est pas le sujet.

## 2. Les quatre agents — 1:10

```powershell
pacman-rl compare --ghosts 4 --games 30 --weights results/poids_4fantomes.json
```

Tourne en **6 s**. Trois lignes s'affichent : aléatoire, heuristique, q-approximé.

**Dire pendant que ça tourne :** « 89 % du labyrinthe est un couloir sans
choix. L'agent ne décide qu'aux 34 intersections : l'horizon passe de 2 500
pas à une centaine, gratuitement. Trente parties, graines jamais vues à
l'entraînement, zéro exploration. »

**Dire quand les chiffres tombent :** « L'aléatoire est le plancher,
l'heuristique écrite à la main le plafond raisonnable. L'agent appris — douze
poids — dépasse l'heuristique. Sur 100 parties dans le rendu : 2 895 contre
2 340. »

> ⚠️ Sur 30 parties les médianes diffèrent des chiffres publiés (2 770 au lieu de
> 2 895 pour l'agent appris). C'est normal et c'est **à dire** : « le rendu est
> sur 100 parties, ici 30 pour tenir dans la démo ».

**Enchaîner sans commande :** « Le quatrième agent, la recherche en ligne,
clone la partie à chaque intersection et simule trois coups. Médiane 4 990,
94 % de victoires. Il met 4 minutes pour 100 parties, je ne le lance pas ici —
mais c'est lui la discussion centrale : il écrase l'apprentissage **parce
qu'il a un simulateur exact et gratuit**. Un robot, un patient, un marché n'en
ont pas. »

## 3. Voir l'agent décider — 1:00

Onglet `docs/decisions.html`, déjà ouvert. Lancer la lecture, laisser défiler
**10 secondes**, puis mettre en pause sur une intersection où un fantôme est
proche.

**Dire :** « C'est une partie rejouée tick par tick. À chaque intersection, la
page montre les directions envisagées, ce que chacune valait, et la
décomposition poids × descripteur qui a tranché. Ici — *montrer* — la
proximité du chasseur pèse négativement, la pastille positivement, et c'est
l'écart entre les deux qui décide. »

**Dire :** « C'est la raison d'avoir préféré douze poids lisibles à un réseau
de neurones : c'est le seul agent dont on puisse faire ça. »

## 4. Les résultats négatifs — 1:10

Onglet `docs/documentation.html`, défiler du §5.6 au §5.7.

**Dire, §5.6 :** « J'ai voulu donner à l'agent la position de chaque fantôme
et de la nourriture. Résultat : **moins bon**, −18 %. Deux fois plus de poids
sur le même budget d'épisodes, et un modèle linéaire ne peut qu'additionner
ces informations, jamais les croiser. Publié tel quel. »

**Dire, §5.7 :** « Un angle mort trouvé en comptant, pas en relisant le code :
les fantômes partaient toujours des quatre mêmes cases, à l'entraînement
comme à l'évaluation. La garde sur les graines protégeait contre la
mémorisation d'une partie, pas contre la dépendance à une configuration. »

*Montrer le tableau.* « Mêmes poids, fantômes dispersés : +130 points,
intervalle à 95 % de −300 à +440. Il contient zéro : l'écart est du bruit.
**La politique tient.** Elle est topologique, pas un plan de maison mémorisé.
Et mon hypothèse de départ était fausse — je l'attendais plus dure, elle est
plus facile. C'est dans le rendu aussi. »

## 5. Usage de l'IA — 0:40

README, section « Usage IA ».

**Dire :** « L'IA générative a été utilisée sur ce projet, et c'est déclaré :
pourquoi, sur quoi, avec des exemples de demandes réelles. Et ce que j'ai
décidé, corrigé ou refusé côté humain — le choix du renforcement, le périmètre,
la décision d'évaluer aux intersections. Les résultats négatifs ci-dessus sont
des questions que j'ai posées ; les mesures, c'est le code qui les a faites, et
elles sont reproductibles par une commande. »

**Fermer :** « Quatre agents, un protocole qui refuse le meilleur run, trois
résultats négatifs publiés, un angle mort levé. Merci. »

---

## Si quelque chose casse en direct

| Problème | Réflexe |
|---|---|
| `pacman-rl : commande introuvable` | Le venv n'est pas activé → `.venv\Scripts\activate` |
| Le serveur ne répond pas | Port 8000 occupé → `pacman-server` encore ouvert dans un autre terminal, le fermer |
| `compare` trop lent | Machine chargée → `--games 10`, dire « dix parties » |
| `decisions.html` vide | Le relancer : `python scripts/exporter_decisions.py` — il rejoue une partie et réécrit la page |

Le montage n'est pas interdit : une coupe entre deux séquences vaut mieux
qu'une hésitation de vingt secondes.

## Après l'enregistrement

1. Regarder la vidéo une fois en entier : durée ≤ 5 min, son audible, texte
   lisible en plein écran.
2. La mettre en ligne — **YouTube en « non répertorié »** (le lien suffit, la
   vidéo n'apparaît pas dans les recherches) ou Google Drive en partage par
   lien. Ne pas la commiter dans le dépôt : un MP4 de cinq minutes dépasse vite
   la limite de taille de GitHub.
3. Coller le lien dans le README, section « Exemples d'utilisation », et dans
   le courriel au professeur.
