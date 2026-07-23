/**
 * Rendu d'une image.
 *
 * Le decor est recopie depuis le canvas hors ecran, puis on empile ce qui
 * bouge. L'ordre compte : les pastilles d'abord, les personnages ensuite,
 * les gains de points par-dessus tout — un « 200 » cache par un fantome
 * serait illisible.
 */

import { TILE, paintMaze } from "./maze.js";
import { drawFruit } from "./fruits.js";
import {
  drawGhost,
  drawPacman,
  drawPacmanDeath,
  drawPellet,
  drawPowerPellet,
} from "./sprites.js";

/** Passe du repere en cases au repere en pixels : on vise le centre de la case. */
const centre = (v) => v * TILE + TILE / 2;

export class Renderer {
  constructor(canvas, view) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.view = view;
    this.decor = null;
  }

  /** Peint le decor une bonne fois et ajuste le canvas au plan recu. */
  setMaze(maze) {
    this.decor = paintMaze(maze);
    this.largeur = maze.width * TILE;
    this.hauteur = maze.height * TILE;
    this.resize();
  }

  /**
   * Aligne la resolution du canvas sur celle de l'ecran. Sans cela, le jeu
   * est flou sur un ecran a forte densite : le navigateur etire une image
   * de 448 pixels sur le double.
   */
  resize() {
    if (!this.decor) return;
    const densite = Math.min(window.devicePixelRatio || 1, 3);
    this.canvas.width = Math.round(this.largeur * densite);
    this.canvas.height = Math.round(this.hauteur * densite);
    this.ctx.setTransform(densite, 0, 0, densite, 0, 0);
    this.ctx.imageSmoothingEnabled = false;
  }

  draw(maintenant) {
    const { ctx, view } = this;
    if (!this.decor || !view.etat) return;

    ctx.clearRect(0, 0, this.largeur, this.hauteur);
    ctx.drawImage(this.decor, 0, 0);

    this._pastilles(maintenant);
    this._fruit();
    this._personnages(maintenant);
    this._popups(maintenant);
  }

  // ------------------------------------------------------------------ couches

  _pastilles(maintenant) {
    const { ctx, view } = this;
    for (const position of view.pellets) {
      const [x, y] = position.split(",");
      drawPellet(ctx, centre(+x), centre(+y));
    }

    // Les super-pastilles battent toutes ensemble, comme sur la borne.
    const battement = Math.abs(Math.sin(maintenant / 220));
    for (const position of view.powerPellets) {
      const [x, y] = position.split(",");
      drawPowerPellet(ctx, centre(+x), centre(+y), battement);
    }
  }

  _fruit() {
    const fruit = this.view.etat.fruit;
    if (fruit) drawFruit(this.ctx, centre(fruit.x), centre(fruit.y), fruit.name);
  }

  _personnages(maintenant) {
    const { ctx, view } = this;
    const etat = view.etat;
    const mourant = etat.state === "dying";

    // Pendant l'animation de mort, les fantomes disparaissent : toute
    // l'attention doit aller a Pac-Man, c'est le codes de la borne d'origine.
    if (!mourant) {
      const frange = Math.floor(maintenant / 150) % 2;
      const clignote = view.clignotement(maintenant);
      for (const fantome of etat.ghosts) {
        const position = view.ghosts.get(fantome.name)?.sample(maintenant);
        if (!position) continue;
        drawGhost(ctx, centre(position.x), centre(position.y), {
          couleur: fantome.color,
          direction: fantome.direction,
          vulnerable: fantome.vulnerable,
          mange: fantome.mode === "eaten",
          clignote,
          frange,
        });
      }
    }

    const position = view.pacman.sample(maintenant);
    if (mourant) {
      drawPacmanDeath(ctx, centre(position.x), centre(position.y), view.progressionMort(maintenant));
      return;
    }

    // Bouche figee tant que la partie n'a pas demarre : un Pac-Man qui machouille
    // dans le vide pendant le compte a rebours donne l'impression d'un bug.
    const anime = etat.state === "playing" && etat.pacman.direction !== "none";
    const ouverture = anime ? Math.abs(Math.sin(maintenant / 70)) : 0.55;
    drawPacman(ctx, centre(position.x), centre(position.y), etat.pacman.direction, ouverture);
  }

  _popups(maintenant) {
    const { ctx, view } = this;
    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `bold ${Math.round(TILE * 0.75)}px ui-monospace, monospace`;
    for (const popup of view.popupsVivants(maintenant)) {
      ctx.globalAlpha = Math.max(0, popup.opacite);
      ctx.fillStyle = popup.couleur;
      // Le gain monte doucement : il se detache du fond et se lit meme si le
      // personnage qui l'a produit est deja reparti.
      ctx.fillText(popup.texte, centre(popup.x), centre(popup.y) - (1 - popup.opacite) * TILE);
    }
    ctx.restore();
  }
}
