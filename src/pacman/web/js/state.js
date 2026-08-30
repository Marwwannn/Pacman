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

/** Intervalle entre deux images du serveur, avant premiere mesure. */
const INTERVALLE_DEFAUT = 1000 / 60;

/** Bornes de la cadence mesuree : au-dela, c'est une hesitation du reseau. */
const INTERVALLE_MIN = 5;
const INTERVALLE_MAX = 250;

/** Duree d'un pas d'une case, avant d'avoir observe le rythme reel. */
const DUREE_CASE_DEFAUT = 1000 / 9.6;

/** Bornes du rythme des pas : du fantome mange au fantome ralenti en tunnel. */
const PAS_MIN = 40;
const PAS_MAX = 400;

/** Au-dela, ce n'est plus du retard mais un replacement : on teleporte. */
const ECART_TELEPORT = 1.5;

/**
 * Seuil de rattrapage, en cases. En dessous, le personnage avance a vitesse
 * constante ; au-dela, il accelere a proportion de son retard.
 *
 * C'est le reglage qui arbitre entre fluidite et latence, et les deux
 * s'opposent : rattraper vite rapproche le dessin de la verite du serveur,
 * mais le personnage rejoint alors sa case avant le pas suivant et se fige en
 * l'attendant. Mesure a 60 images/s, pour Pac-Man au niveau 1 :
 *
 *     seuil 0,3 -> 36 % d'images figees, 12 ms de retard
 *     seuil 0,7 ->  4 % d'images figees, 36 ms de retard
 *     seuil 1,2 ->  0 % d'images figees, 52 ms de retard
 *
 * Le retard se stabilise a une demi-case quoi qu'il arrive : c'est le prix
 * d'un serveur qui ne dit que la case occupee, jamais la fraction parcourue.
 * Autant le payer et avoir un mouvement parfaitement continu.
 */
const RETARD_VISE = 1.2;

/** Duree d'affichage d'un gain de points. */
const DUREE_POPUP = 900;

/** Les fantomes clignotent quand il reste moins de ca de vulnerabilite. */
const SEUIL_CLIGNOTEMENT = 2000;

const cle = (x, y) => `${x},${y}`;

/**
 * Un personnage, entre la case ou le serveur le place et le point ou on le
 * dessine.
 *
 * L'avance se fait a vitesse constante, pas sur la duree d'une image du
 * serveur. C'est la difference entre un mouvement fluide et un mouvement
 * saccade : les pas du moteur sont irreguliers, une entite a 0,16 case par
 * tick avance un tick sur six, jamais exactement le meme, alors qu'a l'oeil,
 * un personnage se deplace a vitesse egale. On lisse donc sur le rythme moyen
 * des pas, mesure en cours de partie plutot que suppose.
 */
class Mobile {
  constructor(x, y) {
    this.pos = { x, y };
    this.to = { x, y };
    this.dureeParCase = DUREE_CASE_DEFAUT;
    this._dernierPas = 0;
    this._dernierRendu = 0;
  }

  /** Position a dessiner. Pure : la lire ne fait pas avancer le personnage. */
  get position() {
    return { x: this.pos.x, y: this.pos.y };
  }

  /** Enregistre la case ou le serveur place le personnage. */
  viser(x, y, maintenant) {
    if (x === this.to.x && y === this.to.y) return;

    if (this._dernierPas) {
      const ecart = maintenant - this._dernierPas;
      if (ecart >= PAS_MIN && ecart <= PAS_MAX) {
        this.dureeParCase = this.dureeParCase * 0.7 + ecart * 0.3;
      }
    }
    this._dernierPas = maintenant;
    this.to = { x, y };

    // Passage par un tunnel, ou replacement apres une mort : le personnage
    // reapparait loin. L'y faire glisser lui ferait traverser tout le plateau.
    if (
      Math.abs(x - this.pos.x) > ECART_TELEPORT ||
      Math.abs(y - this.pos.y) > ECART_TELEPORT
    ) {
      this.pos = { x, y };
    }
  }

  /** Rapproche la position dessinee de la case visee. Un appel par image. */
  avancer(maintenant) {
    // Onglet revenu au premier plan, ou image tres en retard : on borne le
    // saut plutot que de projeter le personnage a travers un mur.
    const dt = Math.min(100, Math.max(0, maintenant - this._dernierRendu));
    this._dernierRendu = maintenant;

    const reste = Math.abs(this.to.x - this.pos.x) + Math.abs(this.to.y - this.pos.y);
    if (reste === 0) return;

    // On accelere a proportion du retard, ce qui le stabilise autour de la
    // valeur visee. A vitesse fixe, il s'accumulerait pas apres pas.
    const pas = (dt / this.dureeParCase) * Math.max(1, reste / RETARD_VISE);

    for (const axe of ["x", "y"]) {
      const ecart = this.to[axe] - this.pos[axe];
      if (Math.abs(ecart) <= pas) this.pos[axe] = this.to[axe];
      else this.pos[axe] += Math.sign(ecart) * pas;
    }
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
    this.tickRate = 60;
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

    this.pacman.viser(message.pacman.x, message.pacman.y, maintenant);
    for (const fantome of message.ghosts) {
      const mobile = this.ghosts.get(fantome.name);
      if (mobile) mobile.viser(fantome.x, fantome.y, maintenant);
      else this.ghosts.set(fantome.name, new Mobile(fantome.x, fantome.y));
    }

    for (const evenement of this.derniersEvenements) this._appliquerEvenement(evenement, maintenant);
    this.popups = this.popups.filter((p) => maintenant - p.t0 < DUREE_POPUP);
  }

  /**
   * Fait avancer tous les personnages d'une image.
   * Un seul appel par image, sinon ils avanceraient deux fois plus vite.
   */
  avancer(maintenant) {
    this.pacman?.avancer(maintenant);
    for (const mobile of this.ghosts.values()) mobile.avancer(maintenant);
  }

  /** La cadence reelle se mesure : elle depend de la charge du serveur. */
  _mesurerCadence(maintenant) {
    const ecart = maintenant - this.dernierMessage;
    this.dernierMessage = maintenant;
    if (ecart >= INTERVALLE_MIN && ecart <= INTERVALLE_MAX) {
      // Moyenne glissante : une image en retard ne doit pas tout desequilibrer.
      this.intervalle = this.intervalle * 0.8 + ecart * 0.2;
      // Le serveur envoie une image par tick : sa cadence se deduit de la
      // notre. C'est ce qui permet de convertir en secondes les durees qu'il
      // exprime en ticks, sans coder en dur une valeur qu'il peut changer.
      this.tickRate = 1000 / this.intervalle;
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
      this._popup(payload.points, mobile?.position ?? { x: 14, y: 17 }, maintenant, "#00ffff");
    } else if (type === "fruit_eaten") {
      this._popup(payload.points, this.pacman.position, maintenant, "#ffb8ff");
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
