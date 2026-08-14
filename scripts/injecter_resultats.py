"""Injecte les mesures de `results/campagne.json` dans les documents du rendu.

Aucun chiffre du README, de la documentation ou du support oral n'est recopie
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
DOCUMENTATION = RACINE / "docs" / "documentation.md"
PRESENTATION = RACINE / "docs" / "presentation.html"

DEBUT = "<!-- RESULTATS -->"
FIN = "<!-- FIN RESULTATS -->"

#: Ce que chaque poids veut dire, une fois son signe connu. Le texte est fixe,
#: la valeur vient du run : c'est la lecture qui est humaine, pas le chiffre.
LECTURES = {
    "biais": ("valeur moyenne d'un coup", "valeur moyenne d'un coup"),
    "mange_pastille": ("va chercher la pastille", "evite la pastille (anormal)"),
    "mange_super_pastille": ("va chercher la super-pastille", "se mefie de la super-pastille"),
    "mange_fruit": ("va chercher le fruit", "ignore le fruit"),
    "proximite_pastille": ("se rapproche des pastilles", "s'en eloigne (anormal)"),
    "proximite_chasseur": ("s'approche des chasseurs (anormal)", "**fuit les chasseurs**"),
    "chasseurs_proches": ("tolere l'encerclement (anormal)", "**fuit l'encerclement**"),
    "proximite_proie": ("**chasse les fantomes effrayes**", "fuit meme les proies"),
    "proximite_super_pastille": ("garde les super-pastilles a portee", "s'eloigne des super-pastilles"),
    "issues": ("**prefere les cases qui ont des sorties**", "prefere les impasses (anormal)"),
    "demi_tour": ("aime revenir en arriere", "evite le demi-tour"),
    "avancement": ("joue plus franc en fin de partie", "se replie en fin de partie"),
}


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

### 5.1 Un fantôme — l'agent atteint-il le plafond ?

{tableau(etapes["baselines_1f"] + [appris_1f])}

### 5.2 Quatre fantômes — le jeu complet

{tableau(etapes["comparatif_4f"])}

Et le témoin, entraîné directement à quatre fantômes sans passer par un :

{tableau([direct_4f])}

### 5.3 Ce que l'agent a appris, poids par poids

Les douze poids du modèle entraîné à quatre fantômes, du plus fort au plus
faible. C'est l'intérêt d'un modèle linéaire : **on lit la politique**.

| Descripteur | Poids | Lecture |
|---|---:|---|
{chr(10).join(f"| `{nom}` | {valeur:+.2f} | {lecture_de(nom, valeur)} |" for nom, valeur in ordonnes)}

### 5.4 La courbe d'apprentissage (1 fantôme)

Score médian par fenêtre de 500 épisodes, pendant l'entraînement — donc avec
l'exploration encore active, ce qui explique qu'il reste sous le score final.

| Épisode | ε | Score médian |
|---:|---:|---:|
{courbe}

{FIN}"""


DEBIT_MESURES = """Toutes les mesures ci-dessous viennent d'une seule commande
(`python scripts/campagne_rl.py`), sur **{parties} parties par agent**, à
**ε = 0**, sur des graines de la plage d'évaluation — jamais vues pendant les
{episodes} épisodes d'entraînement. Elles sont reproductibles à l'identique.

*Ces tableaux sont générés par `scripts/injecter_resultats.py` depuis
`results/campagne.json` : aucun chiffre n'est recopié à la main.*"""


def javascript(campagne: dict) -> str:
    etapes = campagne["etapes"]
    poids = etapes["train_4f_curriculum"]["poids"]
    ordonnes = sorted(poids.items(), key=lambda item: -abs(item[1]))

    def bloc(mesure: dict) -> dict:
        return {
            "agent": mesure["agent"],
            "score_median": f"{mesure['score_median']:.0f}",
            "score_ecart_type": f"{mesure['score_ecart_type']:.0f}",
            "victoires": round(mesure["taux_victoire"] * 100),
            "morts": round(mesure["taux_mort"] * 100),
        }

    appris_1f = etapes["train_1f"]["evaluation"]
    quatre = etapes["comparatif_4f"]
    un = etapes["baselines_1f"] + [appris_1f]

    facteur = appris_1f["score_median"] / max(1, etapes["baselines_1f"][0]["score_median"])
    facteur_4 = quatre[2]["score_median"] / max(1, quatre[0]["score_median"])

    donnees = {
        "un_fantome": [bloc(m) for m in un],
        "quatre_fantomes": [bloc(m) for m in quatre],
        "commentaire": (
            f"L'agent appris fait <b>{facteur:.1f} ×</b> le hasard à un fantôme, "
            f"<b>{facteur_4:.1f} ×</b> à quatre. 100 parties, graines jamais vues, ε = 0."
        ),
        "poids": [
            {
                "nom": nom,
                "valeur": f"{valeur:+.2f}",
                "lecture": lecture_de(nom, valeur).replace("**", ""),
            }
            for nom, valeur in ordonnes
        ],
        "commentaire_poids": (
            "Aucun de ces poids n'a été écrit : ils sortent de "
            f"{campagne['episodes']} épisodes. C'est ce qu'un réseau profond "
            "n'aurait pas permis de montrer."
        ),
    }
    return "const RESULTATS = " + json.dumps(donnees, ensure_ascii=False, indent=2) + ";"


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

    html = PRESENTATION.read_text(encoding="utf-8")
    html, nombre = re.subn(
        r"const RESULTATS = .*?;\n(?=\n?function rendreResultats)",
        lambda _: javascript(campagne) + "\n",
        html,
        count=1,
        flags=re.S,
    )
    if not nombre:
        print(f"declaration RESULTATS introuvable dans {PRESENTATION.name}")
        return 1
    PRESENTATION.write_text(html, encoding="utf-8")

    print(f"{DOCUMENTATION.name} et {PRESENTATION.name} mis a jour depuis {CAMPAGNE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
