/**
 * Entrees du joueur : clavier et ecran tactile.
 *
 * Le client n'envoie que des intentions. C'est le moteur qui decide si le
 * virage est possible — et il memorise la demande jusqu'a ce qu'elle le
 * devienne, ce qui rend le controle souple sans qu'on ait rien a faire ici.
 */

const TOUCHES = {
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
  KeyW: "up",
  KeyS: "down",
  KeyA: "left",
  KeyD: "right",
  KeyZ: "up",
  KeyQ: "left",
};

/** Distance minimale d'un glissement pour qu'il compte comme une direction. */
const SEUIL_GLISSEMENT = 24;

export class Controls {
  constructor(cible, handlers = {}) {
    this.cible = cible;
    this.handlers = handlers;
    this.derniere = null;
    this._debut = null;
    this._detacher = [];
  }

  attach() {
    this._ecouter(window, "keydown", (e) => this._clavier(e));
    this._ecouter(this.cible, "pointerdown", (e) => this._doigtPose(e));
    this._ecouter(this.cible, "pointermove", (e) => this._doigtBouge(e));
    this._ecouter(this.cible, "pointerup", () => (this._debut = null));
    this._ecouter(this.cible, "pointercancel", () => (this._debut = null));
    return this;
  }

  detach() {
    for (const annuler of this._detacher) annuler();
    this._detacher = [];
  }

  _ecouter(cible, type, fonction) {
    cible.addEventListener(type, fonction, { passive: false });
    this._detacher.push(() => cible.removeEventListener(type, fonction));
  }

  // ------------------------------------------------------------------ clavier

  _clavier(evenement) {
    const direction = TOUCHES[evenement.code];
    if (direction) {
      evenement.preventDefault(); // les fleches font defiler la page, sinon
      this._diriger(direction);
      return;
    }

    if (evenement.code === "Space" || evenement.code === "KeyP") {
      evenement.preventDefault();
      this.handlers.onPause?.();
    } else if (evenement.code === "Enter") {
      this.handlers.onValider?.();
    }
  }

  // ------------------------------------------------------------------ tactile

  _doigtPose(evenement) {
    this._debut = { x: evenement.clientX, y: evenement.clientY };
  }

  _doigtBouge(evenement) {
    if (!this._debut) return;
    const dx = evenement.clientX - this._debut.x;
    const dy = evenement.clientY - this._debut.y;
    if (Math.abs(dx) < SEUIL_GLISSEMENT && Math.abs(dy) < SEUIL_GLISSEMENT) return;

    evenement.preventDefault();
    // L'axe dominant l'emporte : un glissement n'est jamais parfaitement droit.
    this._diriger(
      Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : dy > 0 ? "down" : "up"
    );
    this._debut = { x: evenement.clientX, y: evenement.clientY };
  }

  // ------------------------------------------------------------------ envoi

  /** Renvoyer deux fois la meme direction ne sert a rien : on filtre. */
  _diriger(direction) {
    if (direction === this.derniere) return;
    this.derniere = direction;
    this.handlers.onDirection?.(direction);
  }

  /** A appeler quand la partie repart : la prochaine demande doit repasser. */
  reset() {
    this.derniere = null;
  }
}
