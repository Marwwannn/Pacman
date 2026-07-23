/**
 * Tableau de bord : score, niveau, vies, messages.
 *
 * Tout ce qui est hors du canvas passe par ici. On n'ecrit dans le DOM que
 * lorsqu'une valeur a change : reecrire le score soixante fois par seconde
 * ferait travailler le navigateur pour rien.
 */

export class Hud {
  constructor(racine = document) {
    this.score = racine.getElementById("score");
    this.best = racine.getElementById("best");
    this.level = racine.getElementById("level");
    this.lives = racine.getElementById("lives");
    this.status = racine.getElementById("status");
    this.overlay = racine.getElementById("overlay");
    this.overlayTitre = racine.getElementById("overlay-title");
    this.overlayTexte = racine.getElementById("overlay-text");
    this._dernier = {};
  }

  update(etat) {
    this._ecrire(this.score, etat.score);
    this._ecrire(this.level, etat.level);
    this._vies(etat.lives);
  }

  setBest(valeur) {
    this._ecrire(this.best, valeur);
  }

  _ecrire(noeud, valeur) {
    if (this._dernier[noeud.id] === valeur) return;
    this._dernier[noeud.id] = valeur;
    noeud.textContent = valeur;
  }

  /** Une pastille par vie en reserve : celle en cours de jeu ne compte pas. */
  _vies(vies) {
    const reserve = Math.max(0, vies - 1);
    if (this._dernier.lives === reserve) return;
    this._dernier.lives = reserve;
    this.lives.replaceChildren(
      ...Array.from({ length: reserve }, () => {
        const pastille = document.createElement("span");
        pastille.className = "life";
        return pastille;
      })
    );
  }

  setStatus(texte, erreur = false) {
    this.status.textContent = texte;
    this.status.classList.toggle("erreur", erreur);
  }

  /** `contenu` est du HTML : les messages contiennent des touches et des listes. */
  showOverlay(titre, contenu = "") {
    this.overlayTitre.textContent = titre;
    this.overlayTexte.innerHTML = contenu;
    this.overlay.hidden = false;
  }

  hideOverlay() {
    this.overlay.hidden = true;
  }

  get overlayVisible() {
    return !this.overlay.hidden;
  }
}

/** Rend un classement en liste, la ligne du joueur mise en avant. */
export function formatScores(entrees, moi = null) {
  if (!entrees.length) return "<p>Aucun score enregistre pour l'instant.</p>";
  const lignes = entrees
    .slice(0, 5)
    .map((entree, rang) => {
      const marque = rang === moi ? ' class="moi"' : "";
      return `<li${marque}><span>${rang + 1}. ${echapper(entree.name)}</span><span>${
        entree.score
      }</span></li>`;
    })
    .join("");
  return `<ul class="scores">${lignes}</ul>`;
}

/** Le classement est declaratif : un nom vient d'un autre joueur, on l'echappe. */
function echapper(texte) {
  const noeud = document.createElement("span");
  noeud.textContent = texte;
  return noeud.innerHTML;
}
