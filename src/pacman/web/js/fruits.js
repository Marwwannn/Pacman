/**
 * Les fruits bonus, un par niveau.
 *
 * Le back-end n'envoie qu'un nom (`cerise`, `fraise`, ...) : c'est au client
 * de savoir a quoi ca ressemble. Chaque fruit est trace en quelques primitives
 * plutot qu'en image, pour la meme raison que les personnages.
 */

import { TILE } from "./maze.js";

const DESSINS = {
  cerise(ctx, cx, cy, u) {
    ctx.strokeStyle = "#00a000";
    ctx.lineWidth = u * 0.12;
    ctx.beginPath();
    ctx.moveTo(cx - u * 0.28, cy + u * 0.15);
    ctx.quadraticCurveTo(cx + u * 0.1, cy - u * 0.75, cx + u * 0.3, cy + u * 0.05);
    ctx.stroke();
    ctx.fillStyle = "#e01010";
    for (const [dx, dy] of [
      [-0.28, 0.28],
      [0.3, 0.2],
    ]) {
      ctx.beginPath();
      ctx.arc(cx + dx * u, cy + dy * u, u * 0.3, 0, Math.PI * 2);
      ctx.fill();
    }
  },

  fraise(ctx, cx, cy, u) {
    ctx.fillStyle = "#e01010";
    ctx.beginPath();
    ctx.moveTo(cx, cy + u * 0.7);
    ctx.quadraticCurveTo(cx - u * 0.6, cy + u * 0.1, cx - u * 0.4, cy - u * 0.3);
    ctx.lineTo(cx + u * 0.4, cy - u * 0.3);
    ctx.quadraticCurveTo(cx + u * 0.6, cy + u * 0.1, cx, cy + u * 0.7);
    ctx.fill();
    ctx.fillStyle = "#00a000";
    ctx.fillRect(cx - u * 0.45, cy - u * 0.45, u * 0.9, u * 0.2);
    ctx.fillRect(cx - u * 0.08, cy - u * 0.7, u * 0.16, u * 0.28);
  },

  orange(ctx, cx, cy, u) {
    rond(ctx, cx, cy, u, "#ff9a00", "#00a000");
  },

  pomme(ctx, cx, cy, u) {
    rond(ctx, cx, cy, u, "#e01010", "#00a000");
  },

  melon(ctx, cx, cy, u) {
    rond(ctx, cx, cy, u, "#9be870", "#00a000");
    ctx.strokeStyle = "#3d8b2a";
    ctx.lineWidth = u * 0.08;
    for (const dx of [-0.2, 0.2]) {
      ctx.beginPath();
      ctx.moveTo(cx + dx * u, cy - u * 0.35);
      ctx.lineTo(cx + dx * u, cy + u * 0.4);
      ctx.stroke();
    }
  },

  /** Le vaisseau de Galaxian, clin d'oeil de la borne de 1980. */
  galboss(ctx, cx, cy, u) {
    ctx.fillStyle = "#ffe000";
    ctx.beginPath();
    ctx.moveTo(cx, cy - u * 0.6);
    ctx.lineTo(cx + u * 0.2, cy + u * 0.1);
    ctx.lineTo(cx - u * 0.2, cy + u * 0.1);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#e01010";
    ctx.fillRect(cx - u * 0.6, cy + u * 0.1, u * 1.2, u * 0.22);
    ctx.fillStyle = "#00d0ff";
    ctx.fillRect(cx - u * 0.5, cy + u * 0.34, u * 1.0, u * 0.18);
  },

  cloche(ctx, cx, cy, u) {
    ctx.fillStyle = "#ffe000";
    ctx.beginPath();
    ctx.moveTo(cx - u * 0.55, cy + u * 0.4);
    ctx.quadraticCurveTo(cx - u * 0.45, cy - u * 0.65, cx, cy - u * 0.65);
    ctx.quadraticCurveTo(cx + u * 0.45, cy - u * 0.65, cx + u * 0.55, cy + u * 0.4);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(cx - u * 0.6, cy + u * 0.4, u * 1.2, u * 0.16);
    ctx.beginPath();
    ctx.arc(cx, cy + u * 0.62, u * 0.14, 0, Math.PI * 2);
    ctx.fill();
  },

  cle(ctx, cx, cy, u) {
    ctx.strokeStyle = "#8ad0ff";
    ctx.lineWidth = u * 0.16;
    ctx.beginPath();
    ctx.arc(cx, cy - u * 0.35, u * 0.25, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "#8ad0ff";
    ctx.fillRect(cx - u * 0.08, cy - u * 0.15, u * 0.16, u * 0.8);
    ctx.fillRect(cx - u * 0.08, cy + u * 0.3, u * 0.34, u * 0.14);
    ctx.fillRect(cx - u * 0.08, cy + u * 0.55, u * 0.28, u * 0.14);
  },
};

function rond(ctx, cx, cy, u, chair, feuille) {
  ctx.fillStyle = chair;
  ctx.beginPath();
  ctx.arc(cx, cy + u * 0.1, u * 0.52, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = feuille;
  ctx.fillRect(cx - u * 0.05, cy - u * 0.62, u * 0.1, u * 0.3);
  ctx.beginPath();
  ctx.ellipse(cx + u * 0.22, cy - u * 0.5, u * 0.22, u * 0.11, -0.4, 0, Math.PI * 2);
  ctx.fill();
}

/** Dessine le fruit `nom` centre en (cx, cy). Un nom inconnu tombe sur la cerise. */
export function drawFruit(ctx, cx, cy, nom) {
  const dessin = DESSINS[nom] ?? DESSINS.cerise;
  dessin(ctx, cx, cy, TILE * 0.7);
}
