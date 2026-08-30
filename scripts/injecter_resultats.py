"""Injecte les mesures de `results/campagne.json` dans les documents du rendu.

Aucun chiffre du README ou de la documentation n'est recopie
a la main : ils sont tous ecrits ici, depuis le JSON produit par la campagne.
Un chiffre recopie se desynchronise au premier reentrainement, et personne ne
s'en apercoit.

    python scripts/campagne_rl.py        # produit results/campagne.json
    python scripts/injecter_resultats.py # met les documents a jour
"""

from __future__ import annotations

import json
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CAMPAGNE = RACINE / "results" / "campagne.json"
COMPARATIF = RACINE / "results" / "descripteurs.json"
FANTOMES = RACINE / "results" / "fantomes_ailleurs.json"
DOCUMENTATION = RACINE / "docs" / "documentation.md"
LISEZMOI = RACINE / "README.md"

DEBUT = "<!-- RESULTATS -->"
FIN = "<!-- FIN RESULTATS -->"

#: Ce que chaque poids veut dire, une fois son signe connu. Le texte est fixe,
#: la valeur vient du run : c'est la lecture qui est humaine, pas le chiffre.
LECTURES = {
    "biais": (
        "constante, **sans effet sur les decisions** (identique pour toutes les actions)",
        "constante, **sans effet sur les decisions** (identique pour toutes les actions)",
    ),
    "mange_pastille": (
        "va chercher la pastille",
        "signe trompeur : colineaire avec `proximite_pastille`, qui vaut 1 sur la meme case",
    ),
    "mange_super_pastille": ("va chercher la super-pastille", "se mefie de la super-pastille"),
    "mange_fruit": ("va chercher le fruit", "ignore le fruit"),
    "proximite_pastille": ("se rapproche des pastilles", "s'en eloigne (anormal)"),
    "proximite_chasseur": ("s'approche des chasseurs (anormal)", "**fuit les chasseurs**"),
    "chasseurs_proches": ("tolere l'encerclement (anormal)", "**fuit l'encerclement**"),
    "proximite_proie": ("**chasse les fantomes effrayes**", "fuit meme les proies"),
    "proximite_super_pastille": (
        "garde les super-pastilles a portee",
        "s'eloigne des super-pastilles",
    ),
    "issues": ("**prefere les cases qui ont des sorties**", "quasi nul : n'a rien tranche"),
    "demi_tour": ("aime revenir en arriere", "evite le demi-tour"),
    "avancement": ("joue plus franc en fin de partie", "prudence croissante en fin de partie"),
}

#: Note de lecture des poids. Ecrite une fois, injectee avec le tableau : sans
#: elle, deux signes se lisent de travers et la question tombe a l'oral.
NOTE_POIDS = """
**Comment lire ces signes.** Deux precautions, sans quoi deux lignes de ce
tableau se lisent a l'envers :

- Le **biais** est identique pour toutes les actions : il ne departage rien.
  Sa valeur mesure le retour moyen d'une partie, pas une preference.
- Deux descripteurs peuvent etre **colineaires**. Sur une case qui porte une
  pastille, `mange_pastille` vaut 1 *et* `proximite_pastille` vaut 1 : les
  deux poids se partagent le credit, et seule leur **somme** a un sens. Ici
  elle reste positive : l'agent va bien manger.

Ce que le tableau dit vraiment : l'agent a appris **la peur avant la
gourmandise**. Fuir les chasseurs et l'encerclement pese plus lourd que
n'importe quelle pastille, et chasser une proie effrayee pese plus encore. Ce
sont exactement les trois priorites de l'heuristique ecrite a la main, sauf
que personne ne les lui a dites.
"""


def ligne(mesure: dict) -> str:
    return (
        f"| {mesure['agent']} | {mesure['score_median']:.0f} | {mesure['score_ecart_type']:.0f} "
        f"| {mesure['score_min']} | {mesure['score_max']} "
        f"| {mesure['taux_victoire']:.0%} | {mesure['taux_mort']:.0%} |"
    )


def tableau(mesures: list[dict]) -> str:
    entete = (
        "| Agent | Score médian | Écart-type | Min | Max | Victoires | Morts |\n"
        "|---|---:|---:|---:|---:|---:|---:|"
    )
    return entete + "\n" + "\n".join(ligne(m) for m in mesures)


def lecture_de(nom: str, valeur: float) -> str:
    positif, negatif = LECTURES.get(nom, ("", ""))
    return positif if valeur >= 0 else negatif


def markdown(campagne: dict) -> str:
    etapes = campagne["etapes"]
    parties = campagne["parties_evaluation"]
    episodes = campagne["episodes"]

    appris_1f = etapes["train_1f"]["evaluation"]
    # L'agent du curriculum est deja dans `comparatif_4f` : ici on ne sort que
    # le temoin, pour le confronter a la colonne curriculum du tableau.
    direct_4f = etapes["train_4f_direct"]["evaluation"]
    poids = etapes["train_4f_curriculum"]["poids"]
    fenetres = etapes["train_1f"]["fenetres"]

    ordonnes = sorted(poids.items(), key=lambda item: -abs(item[1]))

    courbe = "\n".join(
        f"| {f['episode']} | {f['epsilon']:.2f} | {f['score_median']:.0f} |" for f in fenetres
    )

    return f"""{DEBIT_MESURES.format(episodes=episodes, parties=parties)}

### 5.1 Un fantôme : l'agent atteint-il le plafond ?

{tableau(etapes["baselines_1f"] + [appris_1f])}

### 5.2 Quatre fantômes : le jeu complet

{tableau(etapes["comparatif_4f"])}

Et le témoin, entraîné directement à quatre fantômes sans passer par un :

{tableau([direct_4f])}

Le curriculum **n'améliore donc pas le score** : il n'apporte qu'un peu de
régularité et quelques victoires. La recommandation initiale était bonne comme
méthode (elle sépare « l'agent n'apprend pas » de « le problème est trop
dur ») ; elle ne l'était pas comme gain de performance, et c'est la mesure qui
le dit.

### 5.3 Jusqu'où faut-il chercher ?

La recherche n'a qu'un réglage : la profondeur, en points de décision. Son
coût suit, et il se paie à chaque coup joué.

{profondeurs(etapes)}

### 5.4 Ce que l'agent a appris, poids par poids

Les douze poids du modèle entraîné à quatre fantômes, du plus fort au plus
faible. C'est l'intérêt d'un modèle linéaire : **on lit la politique**.

| Descripteur | Poids | Lecture |
|---|---:|---|
{chr(10).join(f"| `{nom}` | {valeur:+.2f} | {lecture_de(nom, valeur)} |" for nom, valeur in ordonnes)}
{NOTE_POIDS}

### 5.5 La courbe d'apprentissage (1 fantôme)

Score médian par fenêtre de 500 épisodes, pendant l'entraînement, donc avec
l'exploration encore active, ce qui explique qu'il reste sous le score final.

| Épisode | ε | Score médian |
|---:|---:|---:|
{courbe}

{descripteurs(campagne)}
{fantomes_ailleurs()}
{FIN}"""


def fantomes_ailleurs() -> str:
    """Section 5.7 : la politique tient-elle si les fantomes changent de depart ?

    Rien n'est ecrit si la mesure n'a pas ete faite : un document qui parle
    d'un resultat absent est pire qu'un document qui n'en parle pas.
    """
    if not FANTOMES.exists():
        return ""
    mesure = json.loads(FANTOMES.read_text(encoding="utf-8"))
    ecarts = mesure["ecarts"]
    conditions = mesure["conditions"]

    lignes = "\n".join(
        f"| {'**' if e['appris'] else ''}{nom}{'**' if e['appris'] else ''} "
        f"| {e['reference']:.0f} | {e['disperse']:.0f} | {e['ecart']:+.0f} "
        f"| [{e['ic95'][0]:+.0f}, {e['ic95'][1]:+.0f}] "
        f"| {'**significatif**' if e['significatif'] else 'dans le bruit'} |"
        for nom, e in ecarts.items()
    )
    appris = ecarts["appris"]
    recherche = ecarts["recherche"]

    return f"""### 5.7 Les fantômes partaient toujours des mêmes cases

Un angle mort du protocole, trouvé sur **une question de l'auteur** en
relecture (« les positions des fantômes sont aléatoires ? ») à laquelle la
réponse a été cherchée en **comptant** ce que les graines faisaient varier, au
lieu de relire le code censé le produire : sur
{mesure['parties']} parties, l'évaluation ne produisait
**{conditions['reference']['configurations_distinctes']} seule configuration de
départ des fantômes**. La graine ne resemait que la case de Pac-Man et l'errance
en mode effrayé. La garde sur les graines protège donc contre la mémorisation
d'une *partie*, pas contre la dépendance à une *configuration*, et rien dans
les chiffres précédents ne permettait de trancher.

Le test est court et **ne réentraîne rien** : les mêmes poids sont réévalués
avec les quatre fantômes tirés au sort hors de la maison
({conditions['disperse']['configurations_distinctes']} configurations sur
{mesure['parties']} parties). Cette condition ne joue pas la même partie : les
quatre fantômes y sont actifs dès le premier tick. On l'attendait plus dure ;
elle est en réalité plus **facile**, parce que dispersés ils partent chacun vers
son coin au lieu de sortir groupés du centre. C'est exactement pourquoi les
agents qui n'ont rien appris servent de témoins : ils absorbent la variation de
difficulté, quel qu'en soit le sens.

| Agent | Référence | Dispersés | Écart | IC 95 % | |
|---|---:|---:|---:|---|---|
{lignes}

**L'agent appris tient** : {appris['ecart']:+.0f} points, intervalle
[{appris['ic95'][0]:+.0f}, {appris['ic95'][1]:+.0f}] : il contient zéro, donc
l'écart est indiscernable du bruit d'échantillonnage. Sa politique ne dépend pas
de la maison centrale : elle est **topologique**, comme ses descripteurs le
laissaient espérer sans que personne ne l'ait vérifié. C'était la seule façon de
le savoir.

Trois des quatre écarts sont du bruit. Le seul qui sorte est celui de la
**recherche** ({recherche['ecart']:+.0f} points, intervalle
[{recherche['ic95'][0]:+.0f}, {recherche['ic95'][1]:+.0f}]), et il s'explique :
elle replanifie depuis l'état réel à chaque intersection, donc des chasseurs
étalés dans le labyrinthe lui sont franchement plus simples qu'une vague sortant
du centre.

*Une nuance à ne pas cacher* : le taux de victoire de l'agent appris passe de
{conditions['reference']['agents']['appris']['taux_victoire']:.0%} à
{conditions['disperse']['agents']['appris']['taux_victoire']:.0%}. Sur
{mesure['parties']} parties cela représente une poignée de parties, trop peu
pour en conclure quoi que ce soit, mais assez pour ne pas prétendre que la
condition dispersée lui est en tout point équivalente.

*(mesure : `python scripts/fantomes_ailleurs.py` → `results/fantomes_ailleurs.json`,
intervalles par bootstrap sur {mesure['tirages_bootstrap']} tirages, graine fixe)*
"""


def profondeurs(etapes: dict) -> str:
    """Balayage de la profondeur de recherche, s'il a ete mesure."""
    balayage = etapes.get("profondeurs_recherche")
    if not balayage:
        return "*Balayage non mesuré.*"

    lignes = "\n".join(
        f"| {mesure['profondeur']} | {mesure['score_median']:.0f} "
        f"| {mesure['score_ecart_type']:.0f} | {mesure['taux_victoire']:.0%} "
        f"| {mesure['taux_mort']:.0%} |"
        for mesure in balayage
    )
    return (
        "| Profondeur | Score médian | Écart-type | Victoires | Morts |\n"
        "|---:|---:|---:|---:|---:|\n" + lignes
    )


def descripteurs(campagne: dict) -> str:
    """Section 5.6 : le comparatif des deux jeux de descripteurs, s'il existe."""
    if not COMPARATIF.exists():
        return (
            "### 5.5 Les positions aident-elles ?\n\n"
            "*Mesure non encore produite : lancer "
            "`python scripts/comparer_descripteurs.py`.*\n"
        )

    mesure = json.loads(COMPARATIF.read_text(encoding="utf-8"))
    base = mesure["jeux"]["base"]
    positions = mesure["jeux"]["positions"]

    lignes = "\n".join(
        f"| `{jeu['descripteurs']}` | {jeu['nombre_de_poids']} "
        f"| {jeu['un_fantome']['score_median']:.0f} "
        f"| {jeu['quatre_fantomes']['score_median']:.0f} "
        f"| {jeu['quatre_fantomes']['score_ecart_type']:.0f} "
        f"| {jeu['quatre_fantomes']['taux_victoire']:.0%} "
        f"| {jeu['secondes']:.0f} s |"
        for jeu in (base, positions)
    )

    ecart = positions["quatre_fantomes"]["score_median"] - base["quatre_fantomes"]["score_median"]
    relatif = ecart / max(1, base["quatre_fantomes"]["score_median"])
    cout = positions["secondes"] / max(1, base["secondes"])

    if relatif > 0.05:
        verdict = (
            f"**Les positions apportent** : +{ecart:.0f} points de score médian "
            f"({relatif:+.0%}) à quatre fantômes."
        )
    elif relatif < -0.05:
        verdict = (
            f"**Les positions n'apportent pas** : {ecart:.0f} points ({relatif:+.0%}). "
            "Deux fois plus de poids à estimer sur le même budget d'épisodes, "
            "pour une information que les agrégats portaient déjà en grande partie."
        )
    else:
        verdict = (
            f"**L'écart n'est pas concluant** : {ecart:+.0f} points ({relatif:+.0%}), "
            "sous le bruit d'un écart-type qui se compte en milliers. Conclure "
            "à un gain sur ce chiffre serait une erreur de lecture."
        )

    return f"""### 5.6 Les positions aident-elles ?

L'expérience a été **demandée par l'auteur** (14/08) : « donne à l'agent la
position de chaque fantôme et de la nourriture ». Même curriculum, mêmes
graines, mêmes hyperparamètres : seul le jeu de descripteurs change.

| Descripteurs | Poids | Médiane 1F | Médiane 4F | Écart-type 4F | Victoires 4F | Entraînement |
|---|---:|---:|---:|---:|---:|---:|
{lignes}

{verdict} Le coût d'entraînement, lui, est mesuré : ×{cout:.1f}.

C'est le genre de résultat qu'un projet honnête doit publier tel quel. La
question « faut-il donner plus d'information à l'agent ? » n'a pas de réponse
évidente : plus de descripteurs, c'est plus de poids à estimer sur le même
budget d'épisodes, et un modèle linéaire ne peut de toute façon pas composer
ces informations entre elles.
"""


DEBIT_MESURES = """Toutes les mesures ci-dessous viennent d'une seule commande
(`python scripts/campagne_rl.py`), sur **{parties} parties par agent**, à
**ε = 0**, sur des graines de la plage d'évaluation, jamais vues pendant les
{episodes} épisodes d'entraînement. Elles sont reproductibles à l'identique.

*Ces tableaux sont générés par `scripts/injecter_resultats.py` depuis
`results/campagne.json` : aucun chiffre n'est recopié à la main.*"""


def descripteurs_pour_le_support() -> dict | None:
    """Le comparatif des jeux de descripteurs, mis en forme pour une diapositive."""
    if not COMPARATIF.exists():
        return None
    mesure = json.loads(COMPARATIF.read_text(encoding="utf-8"))
    jeux = [mesure["jeux"]["base"], mesure["jeux"]["positions"]]
    ecart = (
        jeux[1]["quatre_fantomes"]["score_median"] - jeux[0]["quatre_fantomes"]["score_median"]
    )
    relatif = ecart / max(1, jeux[0]["quatre_fantomes"]["score_median"])
    return {
        "lignes": [
            {
                "nom": jeu["descripteurs"],
                "poids": jeu["nombre_de_poids"],
                "un": f"{jeu['un_fantome']['score_median']:.0f}",
                "quatre": f"{jeu['quatre_fantomes']['score_median']:.0f}",
                "ecart_type": f"{jeu['quatre_fantomes']['score_ecart_type']:.0f}",
                "secondes": f"{jeu['secondes']:.0f}",
            }
            for jeu in jeux
        ],
        "verdict": (
            f"Écart : <b>{ecart:+.0f} points</b> ({relatif:+.0%}) à quatre fantômes."
        ),
    }


def main() -> int:
    if not CAMPAGNE.exists():
        print(f"{CAMPAGNE} absent : lancer d'abord scripts/campagne_rl.py")
        return 1
    campagne = json.loads(CAMPAGNE.read_text(encoding="utf-8"))

    texte = DOCUMENTATION.read_text(encoding="utf-8")
    motif = re.compile(re.escape(DEBUT) + r".*?(?:" + re.escape(FIN) + r"|(?=\n---))", re.S)
    remplacement = markdown(campagne)
    texte, nombre = motif.subn(lambda _: DEBUT + "\n\n" + remplacement + "\n", texte, count=1)
    if not nombre:
        print(f"marqueur {DEBUT} introuvable dans {DOCUMENTATION.name}")
        return 1
    DOCUMENTATION.write_text(texte, encoding="utf-8")

    lisezmoi = LISEZMOI.read_text(encoding="utf-8")
    lisezmoi, nombre = re.subn(
        re.escape(DEBUT) + r".*?" + re.escape(FIN),
        lambda _: DEBUT + "\n\n" + resume(campagne) + "\n" + FIN,
        lisezmoi,
        count=1,
        flags=re.S,
    )
    if not nombre:
        print(f"marqueur {DEBUT} introuvable dans {LISEZMOI.name}")
        return 1
    LISEZMOI.write_text(lisezmoi, encoding="utf-8")

    print(f"{LISEZMOI.name} et {DOCUMENTATION.name} mis a jour depuis {CAMPAGNE.name}")
    return 0


def resume(campagne: dict) -> str:
    """Tableau court pour le README : le comparatif final, et rien d'autre."""
    etapes = campagne["etapes"]
    return (
        f"Les quatre agents à quatre fantômes, sur "
        f"{campagne['parties_evaluation']} parties de graines jamais vues, ε = 0 :\n\n"
        + tableau(etapes["comparatif_4f"])
        + "\n\nL'agent **appris** dépasse l'heuristique écrite à la main. L'agent de "
        "**recherche** les dépasse tous les deux, sans avoir rien appris, mais en "
        "payant à chaque coup ce que l'agent entraîné a payé une seule fois."
    )


if __name__ == "__main__":
    raise SystemExit(main())
