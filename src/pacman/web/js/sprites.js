/**
 * Dessin des personnages et des objets.
 *
 * Tout est vectoriel : aucune image a charger, et le jeu reste net a toutes
 * les tailles. Chaque fonction recoit un centre en pixels — c'est le rendu
 * qui sait convertir une case en position a l'ecran, pas les sprites.
 */

import { TILE } from "./maze.js";

const JAUNE = "#ffcc00";
const BLEU_PEUR = "#2121de";
const BLANC = "#ffffff";
const PASTILLE = "#ffb897";

const ANGLES = { right: 0, down: Math.PI / 2, left: Math.PI, up: -Math.PI / 2, none: 0 };

// ---------------------------------------------------------------- Pac-Man

/**
 * Pac-Man. `ouverture` va de 0 (bouche fermee) a 1 (grande ouverte) : c'est
 * l'animation qui donne l'impression qu'il avance, la position ne changeant
 * que d'une case a la fois.
 */
export function drawPacman(ctx, cx, cy, direction, ouverture) {
  const rayon = TILE * 0.46;
  const angle = (ouverture * Math.PI) / 4; // demi-angle de la bouche

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(ANGLES[direction] ?? 0);
  ctx.fillStyle = JAUNE;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.arc(0, 0, rayon, angle, Math.PI * 2 - angle);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

/**
 * Mort de Pac-Man : la bouche s'ouvre jusqu'a le faire disparaitre.
 * `progression` va de 0 a 1.
 */
export function drawPacmanDeath(ctx, cx, cy, progression) {
  const rayon = TILE * 0.46;
  const p = Math.min(1, Math.max(0, progression));
  const angle = (p * Math.PI) / 2;
  if (p >= 1) return;

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(-Math.PI / 2); // la bouche s'ouvre vers le haut
  ctx.fillStyle = JAUNE;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.arc(0, 0, rayon, angle, Math.PI * 2 - angle);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

// ---------------------------------------------------------------- fantomes

/**
 * Un fantome. Trois apparences selon l'etat :
 * normal (couleur propre), effraye (bleu, puis blanc clignotant quand la
 * super-pastille s'epuise) et mange (les yeux seuls rentrent a la maison).
 */
export function drawGhost(ctx, cx, cy, options) {
  const { couleur, direction = "none", vulnerable = false, mange = false, clignote = false } = options;

  if (!mange) {
    const teinte = vulnerable ? (clignote ? BLANC : BLEU_PEUR) : couleur;
    drawGhostBody(ctx, cx, cy, teinte, options.frange ?? 0);
  }

  if (vulnerable && !mange) drawFrightenedFace(ctx, cx, cy, clignote);
  else drawEyes(ctx, cx, cy, direction);
}

function drawGhostBody(ctx, cx, cy, couleur, frange) {
  const r = TILE * 0.46;
  const haut = cy - r;
  const bas = cy + r * 0.92;

  ctx.fillStyle = couleur;
  ctx.beginPath();
  ctx.arc(cx, haut + r, r, Math.PI, 0); // calotte
  ctx.lineTo(cx + r, bas);

  // Bas festonne. La frange alterne a chaque image pour animer la marche.
  const pas = (r * 2) / 3;
  const creux = r * 0.28;
  for (let i = 0; i < 3; i += 1) {
    const x0 = cx + r - i * pas;
    const sens = (i + frange) % 2 === 0 ? -1 : 1;
    ctx.quadraticCurveTo(x0 - pas / 2, bas + sens * creux, x0 - pas, bas);
  }

  ctx.closePath();
  ctx.fill();
}

function drawEyes(ctx, cx, cy, direction) {
  const r = TILE * 0.46;
  const ecart = r * 0.42;
  const blanc = r * 0.32;
  const pupille = r * 0.16;
  const regard = { right: [1, 0], left: [-1, 0], up: [0, -1], down: [0, 1], none: [0, 0] }[
    direction
  ] ?? [0, 0];

  for (const cote of [-1, 1]) {
    const ex = cx + cote * ecart;
    const ey = cy - r * 0.18;
    ctx.fillStyle = BLANC;
    ctx.beginPath();
    ctx.ellipse(ex, ey, blanc, blanc * 1.2, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#2121de";
    ctx.beginPath();
    ctx.arc(ex + regard[0] * pupille, ey + regard[1] * pupille * 1.2, pupille, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawFrightenedFace(ctx, cx, cy, clignote) {
  const r = TILE * 0.46;
  const trait = clignote ? "#ff0000" : BLANC;

  // Yeux carres.
  ctx.fillStyle = trait;
  for (const cote of [-1, 1]) {
    ctx.fillRect(cx + cote * r * 0.42 - r * 0.15, cy - r * 0.32, r * 0.3, r * 0.3);
  }

  // Bouche en zigzag.
  ctx.strokeStyle = trait;
  ctx.lineWidth = Math.max(1, r * 0.16);
  ctx.beginPath();
  const largeur = r * 1.2;
  const gauche = cx - largeur / 2;
  const y = cy + r * 0.38;
  for (let i = 0; i <= 4; i += 1) {
    const px = gauche + (largeur * i) / 4;
    const py = y + (i % 2 === 0 ? r * 0.14 : -r * 0.14);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.stroke();
}

// ---------------------------------------------------------------- pastilles

export function drawPellet(ctx, cx, cy) {
  ctx.fillStyle = PASTILLE;
  ctx.fillRect(cx - TILE * 0.09, cy - TILE * 0.09, TILE * 0.18, TILE * 0.18);
}

/** Super-pastille : elle bat, pour se distinguer au premier coup d'oeil. */
export function drawPowerPellet(ctx, cx, cy, battement) {
  const rayon = TILE * (0.26 + 0.04 * battement);
  ctx.fillStyle = PASTILLE;
  ctx.beginPath();
  ctx.arc(cx, cy, rayon, 0, Math.PI * 2);
  ctx.fill();
}
