/**
 * Vue du jeu cote client.
 *
 * Le serveur envoie une image par tick, soit une douzaine par seconde, alors
 * que l'ecran en affiche soixante. On garde donc pour chaque personnage la
 * case quittee et la case visee, et le rendu interpole entre les deux. Sans
 * cela le jeu avancerait par saccades d'une case entiere.
 *
 * Cette classe ne decide rien : elle traduit les messages du serveur en
 * quelque chose de dessinable. Toute la regle du jeu reste au back-end.
 */

/** Duree d'interpolation par defaut, si l'on n'a pas encore mesure la cadence. */
const INTERVALLE_DEFAUT = 1000 / 12;

/** Bornes de la cadence mesuree : au-dela, c'est une hesitation du reseau. */
const INTERVALLE_MIN = 40;
const INTERVALLE_MAX = 250;

/** Duree d'affichage d'un gain de points. */
const DUREE_POPUP = 900;

/** Les fantomes clignotent quand il reste moins de ca de vulnerabilite. */
const SEUIL_CLIGNOTEMENT = 2000;

const cle = (x, y) => `${x},${y}`;

class Mobile {
  constructor(x, y) {
    this.from = { x, y };
    this.to = { x, y };
    this.t0 = 0;
    this.duree = INTERVALLE_DEFAUT;
  }

  /** Vise une nouvelle case en partant de la position affichee a l'instant. */
  viser(x, y, maintenant, duree) {
    const actuelle = this.sample(maintenant);
    this.from = actuelle;
    this.to = { x, y };
    this.t0 = maintenant;
    this.duree = duree;

    // Passage par un tunnel : le personnage ressort a l'oppose du plateau.
    // Interpoler le traverserait de part en part, on le teleporte donc.
    if (Math.abs(this.to.x - this.from.x) > 1 || Math.abs(this.to.y - this.from.y) > 1) {
      this.from = { ...this.to };
    }
  }

  sample(maintenant) {
    const avancement = Math.min(1, Math.max(0, (maintenant - this.t0) / this.duree));
    return {
      x: this.from.x + (this.to.x - this.from.x) * avancement,
      y: this.from.y + (this.to.y - this.from.y) * avancement,
    };
  }
}

export class GameView {
  constructor() {
    this.maze = null;
    this.pellets = new Set();
    this.powerPellets = new Set();
    this.pacman = null;
    this.ghosts = new Map();
    this.etat = null;
    this.popups = [];
    this.frightenedJusqua = 0;
    this.mortDepuis = 0;
    this.intervalle = INTERVALLE_DEFAUT;
    this.dernierMessage = 0;
    this.tickRate = 12;
    /** Evenements du dernier tick, a la disposition du son et du HUD. */
    this.derniersEvenements = [];
  }

  // ------------------------------------------------------------------ entree

  applyInit(message, maintenant = performance.now()) {
    this.maze = message.maze;
    this.pellets = new Set(message.state.pellets.map(([x, y]) => cle(x, y)));
    this.powerPellets = new Set(message.state.power_pellets.map(([x, y]) => cle(x, y)));
    this.pacman = new Mobile(message.state.pacman.x, message.state.pacman.y);
    this.ghosts = new Map(
      message.state.ghosts.map((g) => [g.name, new Mobile(g.x, g.y)])
    );
    this.etat = message.state;
    this.dernierMessage = maintenant;
  }

  applyState(message, maintenant = performance.now()) {
    if (!this.maze) return;

    this._mesurerCadence(maintenant);
    this.etat = message;
    this.derniersEvenements = message.events ?? [];

    this.pacman.viser(message.pacman.x, message.pacman.y, maintenant, this.intervalle);
    for (const fantome of message.ghosts) {
      const mobile = this.ghosts.get(fantome.name);
      if (mobile) mobile.viser(fantome.x, fantome.y, maintenant, this.intervalle);
      else this.ghosts.set(fantome.name, new Mobile(fantome.x, fantome.y));
    }

    for (const evenement of this.derniersEvenements) this._appliquerEvenement(evenement, maintenant);
    this.popups = this.popups.filter((p) => maintenant - p.t0 < DUREE_POPUP);
  }

  /** La cadence reelle se mesure : elle depend de la charge du serveur. */
  _mesurerCadence(maintenant) {
    const ecart = maintenant - this.dernierMessage;
    this.dernierMessage = maintenant;
    if (ecart >= INTERVALLE_MIN && ecart <= INTERVALLE_MAX) {
      // Moyenne glissante : une image en retard ne doit pas tout desequilibrer.
      this.intervalle = this.intervalle * 0.8 + ecart * 0.2;
    }
  }

  _appliquerEvenement(evenement, maintenant) {
    const { type, payload = {} } = evenement;

    if (type === "pellet") {
      this.pellets.delete(cle(payload.x, payload.y));
    } else if (type === "power_pellet") {
      this.powerPellets.delete(cle(payload.x, payload.y));
    } else if (type === "frightened") {
      // La duree arrive en ticks : c'est la seule facon de savoir quand faire
      // clignoter les fantomes, le serveur n'envoyant pas de compte a rebours.
      this.frightenedJusqua = maintenant + (payload.duration / this.tickRate) * 1000;
    } else if (type === "frightened_end") {
      this.frightenedJusqua = 0;
    } else if (type === "ghost_eaten") {
      const mobile = this.ghosts.get(payload.ghost);
      const ou = mobile ? mobile.sample(maintenant) : { x: 14, y: 17 };
      this._popup(payload.points, ou, maintenant, "#00ffff");
    } else if (type === "fruit_eaten") {
      this._popup(payload.points, this.pacman.sample(maintenant), maintenant, "#ffb8ff");
    } else if (type === "pacman_died") {
      this.mortDepuis = maintenant;
    } else if (type === "level_start" || type === "round_start") {
      this.frightenedJusqua = 0;
      this.mortDepuis = 0;
    }
  }

  _popup(points, position, maintenant, couleur) {
    this.popups.push({ texte: String(points), x: position.x, y: position.y, t0: maintenant, couleur });
  }

  /** Recharge les pastilles apres un changement de niveau (etat complet). */
  resync(etat) {
    if (etat.pellets) this.pellets = new Set(etat.pellets.map(([x, y]) => cle(x, y)));
    if (etat.power_pellets) {
      this.powerPellets = new Set(etat.power_pellets.map(([x, y]) => cle(x, y)));
    }
  }

  // ------------------------------------------------------------------ lecture

  /** Les fantomes vulnerables clignotent sur la fin de la super-pastille. */
  clignotement(maintenant) {
    const restant = this.frightenedJusqua - maintenant;
    if (restant <= 0 || restant > SEUIL_CLIGNOTEMENT) return false;
    return Math.floor(restant / 200) % 2 === 0;
  }

  /** Avancement de l'animation de mort, de 0 a 1. */
  progressionMort(maintenant, duree = 1500) {
    if (!this.mortDepuis) return 0;
    return Math.min(1, (maintenant - this.mortDepuis) / duree);
  }

  popupsVivants(maintenant) {
    return this.popups.map((p) => ({ ...p, opacite: 1 - (maintenant - p.t0) / DUREE_POPUP }));
  }
}
