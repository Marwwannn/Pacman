/**
 * Bruitages, synthetises a la volee.
 *
 * Aucun fichier son : quelques oscillateurs suffisent pour les bips d'une
 * borne, et le jeu reste un seul dossier sans dependance. Les navigateurs
 * interdisent de jouer un son avant que le joueur ait agi — le contexte n'est
 * donc cree qu'au premier appui sur une touche.
 */

const SONS = {
  pellet: { frequences: [660], duree: 0.05, forme: "square", volume: 0.05 },
  power_pellet: { frequences: [220, 440], duree: 0.18, forme: "square", volume: 0.09 },
  ghost_eaten: { frequences: [180, 900], duree: 0.25, forme: "sawtooth", volume: 0.09 },
  fruit_eaten: { frequences: [520, 780, 1040], duree: 0.22, forme: "triangle", volume: 0.09 },
  extra_life: { frequences: [660, 880, 1320], duree: 0.35, forme: "square", volume: 0.09 },
  pacman_died: { frequences: [520, 90], duree: 0.85, forme: "sawtooth", volume: 0.11 },
  level_complete: { frequences: [440, 660, 880, 1320], duree: 0.5, forme: "triangle", volume: 0.09 },
  game_over: { frequences: [330, 70], duree: 1.1, forme: "sawtooth", volume: 0.11 },
};

export class Sounds {
  constructor() {
    this.ctx = null;
    this.actif = true;
    /** Un bip par pastille ferait un bourdonnement : on les espace. */
    this._dernierePastille = 0;
  }

  /** A appeler depuis un geste du joueur, sinon le navigateur refuse. */
  unlock() {
    if (!this.ctx) {
      const Contexte = window.AudioContext || window.webkitAudioContext;
      if (!Contexte) return;
      this.ctx = new Contexte();
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
  }

  toggle() {
    this.actif = !this.actif;
    return this.actif;
  }

  /** Joue le bruitage associe a un evenement du moteur, s'il en a un. */
  play(type) {
    if (!this.actif || !this.ctx || this.ctx.state !== "running") return;

    if (type === "pellet") {
      const maintenant = this.ctx.currentTime;
      if (maintenant - this._dernierePastille < 0.08) return;
      this._dernierePastille = maintenant;
    }

    const son = SONS[type];
    if (son) this._bip(son);
  }

  /** Balayage entre les frequences donnees, avec une extinction douce. */
  _bip({ frequences, duree, forme, volume }) {
    const debut = this.ctx.currentTime;
    const oscillateur = this.ctx.createOscillator();
    const gain = this.ctx.createGain();

    oscillateur.type = forme;
    oscillateur.frequency.setValueAtTime(frequences[0], debut);
    frequences.slice(1).forEach((frequence, i) => {
      oscillateur.frequency.exponentialRampToValueAtTime(
        frequence,
        debut + (duree * (i + 1)) / (frequences.length - 1)
      );
    });

    gain.gain.setValueAtTime(volume, debut);
    // Extinction exponentielle : couper net produirait un claquement.
    gain.gain.exponentialRampToValueAtTime(0.0001, debut + duree);

    oscillateur.connect(gain).connect(this.ctx.destination);
    oscillateur.start(debut);
    oscillateur.stop(debut + duree);
  }
}
