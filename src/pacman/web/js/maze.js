/**
 * Peinture du labyrinthe.
 *
 * Le plan est immuable : le serveur ne l'envoie qu'une fois. On le peint donc
 * une seule fois dans un canvas hors ecran, recopie tel quel a chaque image.
 * Redessiner 868 cases soixante fois par seconde n'apporterait rien.
 *
 * Les murs sont creux, comme sur la borne : un trait bleu suit la frontiere
 * entre le mur et le couloir. On l'obtient en deux passes : on remplit la case
 * en bleu, puis on recreuse l'interieur en noir en ne reculant que des cotes
 * qui donnent sur un couloir. Les cotes partages entre deux murs ne reculent
 * pas : les cases voisines fusionnent, et le trait ne court que sur le bord
 * exterieur du bloc.
 */

export const TILE = 16;

const MUR = "#";
const PORTE = "-";

const COULEUR_MUR = "#2121de";
const COULEUR_PORTE = "#ffb8ff";
const COULEUR_FOND = "#000000";

/** Epaisseur du trait de mur, et rayon des angles saillants. */
const TRAIT = 2;
const RAYON = 6;

/** Le plan vu comme une grille de caracteres, avec les bords hors grille ouverts. */
class Grille {
  constructor(rows) {
    this.rows = rows;
    this.height = rows.length;
    this.width = rows[0].length;
  }

  at(x, y) {
    if (y < 0 || y >= this.height || x < 0 || x >= this.width) return " ";
    return this.rows[y][x];
  }

  /** Hors grille compte comme couloir : sans quoi la bordure exterieure du
   *  labyrinthe, epaisse d'une seule case, serait entierement recreusee. */
  estMur(x, y) {
    return this.at(x, y) === MUR;
  }
}

/**
 * Peint le plan statique et renvoie le canvas hors ecran.
 * Les pastilles n'y sont pas : elles se mangent, donc elles bougent.
 */
export function paintMaze(maze) {
  const grille = new Grille(maze.rows);
  const canvas = document.createElement("canvas");
  canvas.width = grille.width * TILE;
  canvas.height = grille.height * TILE;
  const ctx = canvas.getContext("2d");

  ctx.fillStyle = COULEUR_FOND;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  for (let y = 0; y < grille.height; y += 1) {
    for (let x = 0; x < grille.width; x += 1) {
      if (grille.estMur(x, y)) peindreMur(ctx, grille, x, y);
      else if (grille.at(x, y) === PORTE) peindrePorte(ctx, x, y);
    }
  }

  return canvas;
}

function peindreMur(ctx, grille, x, y) {
  const haut = !grille.estMur(x, y - 1);
  const bas = !grille.estMur(x, y + 1);
  const gauche = !grille.estMur(x - 1, y);
  const droite = !grille.estMur(x + 1, y);

  const X = x * TILE;
  const Y = y * TILE;

  // Passe 1 : la case entiere en bleu, arrondie a ses angles saillants :
  // ceux dont les deux cotes donnent sur un couloir.
  ctx.fillStyle = COULEUR_MUR;
  ctx.beginPath();
  ctx.roundRect(X, Y, TILE, TILE, [
    haut && gauche ? RAYON : 0,
    haut && droite ? RAYON : 0,
    bas && droite ? RAYON : 0,
    bas && gauche ? RAYON : 0,
  ]);
  ctx.fill();

  // Passe 2 : on recreuse, en ne reculant que des cotes ouverts. Les cotes
  // partages avec un mur voisin restent a fleur de case, ce qui soude les
  // deux interieurs et evite un liseré parasite entre deux murs.
  const x0 = X + (gauche ? TRAIT : 0);
  const y0 = Y + (haut ? TRAIT : 0);
  const x1 = X + TILE - (droite ? TRAIT : 0);
  const y1 = Y + TILE - (bas ? TRAIT : 0);
  const interne = Math.max(0, RAYON - TRAIT);

  ctx.fillStyle = COULEUR_FOND;
  ctx.beginPath();
  ctx.roundRect(x0, y0, x1 - x0, y1 - y0, [
    haut && gauche ? interne : 0,
    haut && droite ? interne : 0,
    bas && droite ? interne : 0,
    bas && gauche ? interne : 0,
  ]);
  ctx.fill();
}

/** La porte de la maison : une barre fine, franchissable par les seuls fantomes. */
function peindrePorte(ctx, x, y) {
  ctx.fillStyle = COULEUR_PORTE;
  ctx.fillRect(x * TILE, y * TILE + TILE / 2 - 1, TILE, 2);
}
