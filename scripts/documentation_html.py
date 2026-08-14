"""Rend `docs/documentation.md` en un HTML autonome, pret a imprimer en PDF.

L'enonce demande une documentation au format PDF. Plutot que d'ajouter une
dependance lourde (WeasyPrint et sa chaine GTK, LaTeX...), on produit un HTML
mis en page pour l'impression : le navigateur fait le PDF en deux clics, avec
un rendu identique partout.

    python scripts/documentation_html.py
    # puis ouvrir docs/documentation.html et Ctrl+P -> « Enregistrer en PDF »

Seule dependance : `markdown`, deja disponible.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import markdown
except ModuleNotFoundError:  # pragma: no cover - message d'aide
    print("module `markdown` absent : pip install markdown")
    raise SystemExit(1) from None

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "docs" / "documentation.md"
CIBLE = RACINE / "docs" / "documentation.html"

STYLE = """
@page { size: A4; margin: 18mm 16mm; }
:root {
  --encre: #16181d;
  --doux: #5a6070;
  --trait: #dcdfe6;
  --accent: #b8860b;
  --fond-code: #f6f7f9;
}
* { box-sizing: border-box; }
body {
  max-width: 190mm;
  margin: 0 auto;
  padding: 12mm 8mm;
  color: var(--encre);
  font: 400 10.5pt/1.6 "Segoe UI", system-ui, sans-serif;
  background: #fff;
}
h1 { font-size: 21pt; line-height: 1.15; letter-spacing: -.02em; margin: 0 0 .4em; }
h2 { font-size: 15pt; margin: 2.2em 0 .7em; padding-bottom: .25em;
     border-bottom: 2px solid var(--accent); letter-spacing: -.01em; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin: 1.8em 0 .5em; color: var(--accent); page-break-after: avoid; }
p, li { margin-bottom: .65em; }
ul, ol { padding-left: 1.3em; margin-bottom: 1em; }
strong { font-weight: 600; }
em { color: var(--doux); }
hr { border: none; border-top: 1px solid var(--trait); margin: 2.5em 0; }
blockquote { margin: 1em 0; padding: .2em 0 .2em 1em; border-left: 3px solid var(--accent);
             color: var(--encre); font-style: italic; }
code { font-family: Consolas, "Cascadia Code", monospace; font-size: .88em;
       background: var(--fond-code); padding: .1em .35em; border-radius: 3px; }
pre { background: var(--fond-code); border: 1px solid var(--trait); border-left: 3px solid var(--accent);
      border-radius: 4px; padding: .8em 1em; overflow-x: auto; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: .82em; line-height: 1.45; }
table { border-collapse: collapse; width: 100%; margin: 1em 0 1.4em; font-size: .92em;
        page-break-inside: avoid; }
th, td { text-align: left; padding: .45em .6em; border-bottom: 1px solid var(--trait); }
th { border-bottom: 2px solid var(--accent); font-size: .85em; text-transform: uppercase;
     letter-spacing: .05em; color: var(--doux); }
td[align="right"], th[align="right"] { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr:nth-child(even) { background: #fafbfc; }
a { color: var(--encre); text-decoration: underline; text-decoration-color: var(--accent); }
@media print { body { padding: 0; } a { text-decoration: none; } }
"""

GABARIT = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{titre}</title>
<style>{style}</style>
</head>
<body>
{corps}
</body>
</html>
"""


def main() -> int:
    if not SOURCE.exists():
        print(f"{SOURCE} introuvable")
        return 1

    texte = SOURCE.read_text(encoding="utf-8")
    corps = markdown.markdown(texte, extensions=["tables", "fenced_code", "toc", "sane_lists"])
    CIBLE.write_text(
        GABARIT.format(
            titre="Pac-Man — documentation technique",
            style=STYLE,
            corps=corps,
        ),
        encoding="utf-8",
    )
    print(f"{CIBLE.relative_to(RACINE)} ecrit — ouvrir puis Ctrl+P > « Enregistrer en PDF »")
    return 0


if __name__ == "__main__":
    sys.exit(main())
