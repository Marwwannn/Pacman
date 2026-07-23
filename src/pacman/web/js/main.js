/**
 * Assemblage du client.
 *
 * Ce fichier ne connait aucune regle du jeu : il cree une partie, branche le
 * canal temps reel sur la vue, et fait tourner la boucle d'affichage. Toute la
 * logique est ailleurs — au back-end pour le jeu, dans les modules voisins
 * pour le rendu et les entrees.
 */

import { Sounds } from "./audio.js";
import { Hud, formatScores } from "./hud.js";
import { Controls } from "./input.js";
import { GameLink, createGame, deleteGame, readScores, submitScore } from "./net.js";
import { Renderer } from "./render.js";
import { GameView } from "./state.js";

const CLE_NOM = "pacman.nom";
const CLE_RECORD = "pacman.record";

const AIDE = `
  <b>Flèches</b> ou <b>WASD</b> pour se déplacer ·
  <b>Espace</b> pour la pause<br>
  Appuyez sur <span class="touche">Entrée</span> pour commencer.
`;

class Client {
  constructor() {
    this.view = new GameView();
    this.hud = new Hud();
    this.sons = new Sounds();
    this.renderer = new Renderer(document.getElementById("board"), this.view);
    this.controls = new Controls(document.getElementById("board"), {
      onDirection: (direction) => this.link?.input(direction),
      onPause: () => this.basculerPause(),
      onValider: () => this.valider(),
    });

    this.link = null;
    this.gameId = null;
    this.enCours = false;
    this.terminee = false;
    this.record = Number(localStorage.getItem(CLE_RECORD) || 0);
  }

  // ------------------------------------------------------------------ demarrage

  async start() {
    this.controls.attach();
    window.addEventListener("resize", () => this.renderer.resize());
    // Une partie qui continue dans un onglet cache n'est pas jouable : on la met
    // en pause plutot que de laisser les fantomes manger Pac-Man en coulisses.
    document.addEventListener("visibilitychange", () => {
      if (document.hidden && this.enCours) this.link?.pause();
    });
    document.getElementById("board").addEventListener("click", () => this.valider());

    this.hud.setBest(this.record);
    await this.ecranTitre();
    requestAnimationFrame((t) => this.boucle(t));
  }

  async ecranTitre() {
    const classement = await readScores();
    if (classement.length) {
      this.record = Math.max(this.record, classement[0].score);
      this.hud.setBest(this.record);
    }
    this.hud.showOverlay("Pac-Man", AIDE + formatScores(classement));
    this.hud.setStatus("Prêt à jouer");
  }

  /** Entree ou clic : selon le moment, ca lance, ca reprend ou ca rejoue. */
  valider() {
    this.sons.unlock();
    if (!this.enCours) this.nouvellePartie();
    else if (this.view.etat?.state === "paused") this.basculerPause();
  }

  // ------------------------------------------------------------------ partie

  async nouvellePartie() {
    if (this.enCours) return;
    this.enCours = true;
    this.terminee = false;
    this.controls.reset();
    this.hud.showOverlay("Chargement…");
    this.hud.setStatus("Création de la partie…");

    try {
      const partie = await createGame({ maze: "classic" });
      this.gameId = partie.state.id;
      this.renderer.setMaze(partie.maze);
      this.brancher();
    } catch (erreur) {
      this.enCours = false;
      this.hud.setStatus(`Serveur injoignable — ${erreur.message}`, true);
      this.hud.showOverlay("Hors service", "Le back-end ne répond pas. Relancez <b>pacman-server</b>.");
    }
  }

  brancher() {
    this.link = new GameLink(this.gameId, {
      onInit: (message) => {
        this.view.applyInit(message);
        this.hud.update(message.state);
        this.hud.hideOverlay();
        this.hud.setStatus("Bonne chance !");
      },
      onState: (message) => this.surEtat(message),
      onError: (message) => this.hud.setStatus(message, true),
      onClose: () => {
        if (this.terminee) return;
        this.enCours = false;
        this.hud.setStatus("Connexion perdue", true);
        this.hud.showOverlay("Déconnecté", "La partie s'est interrompue.<br>" + AIDE);
      },
    }).connect();
  }

  surEtat(message) {
    this.view.applyState(message);
    this.hud.update(message);

    for (const evenement of message.events ?? []) {
      this.sons.play(evenement.type);
      // Le serveur n'envoie les pastilles qu'a l'ouverture du canal : au
      // changement de niveau, le client doit aller rechercher le plan garni.
      if (evenement.type === "level_start") this.resynchroniser();
    }

    if (message.score > this.record) {
      this.record = message.score;
      this.hud.setBest(this.record);
    }

    if (message.state === "paused" && !this.hud.overlayVisible) {
      this.hud.showOverlay("Pause", "Appuyez sur <span class=\"touche\">Espace</span> pour reprendre.");
    } else if (message.state !== "paused" && this.hud.overlayVisible && !this.terminee) {
      this.hud.hideOverlay();
    }

    if (message.state === "game_over") this.finPartie(message);
  }

  async resynchroniser() {
    try {
      const reponse = await fetch(`/api/games/${this.gameId}?include_pellets=true`);
      if (reponse.ok) this.view.resync(await reponse.json());
    } catch {
      // Sans resynchronisation les pastilles du niveau suivant manquent a
      // l'affichage, mais la partie reste jouable : on n'interrompt rien.
      this.hud.setStatus("Resynchronisation impossible", true);
    }
  }

  basculerPause() {
    if (!this.enCours || this.terminee) return;
    if (this.view.etat?.state === "paused") this.link?.resume();
    else this.link?.pause();
  }

  // ------------------------------------------------------------------ fin

  async finPartie(message) {
    if (this.terminee) return;
    this.terminee = true;
    this.enCours = false;
    this.link?.close();
    this.hud.setStatus("Partie terminée");

    localStorage.setItem(CLE_RECORD, String(Math.max(this.record, message.score)));
    const classement = await this.enregistrer(message);
    this.hud.showOverlay(
      "Game over",
      `Score <b>${message.score}</b> · niveau <b>${message.level}</b><br>` +
        formatScores(classement.entrees, classement.rang) +
        `Appuyez sur <span class="touche">Entrée</span> pour rejouer.`
    );

    if (this.gameId) deleteGame(this.gameId);
    this.gameId = null;
  }

  /** Depose le score au classement. Un echec ne doit pas bloquer le rejeu. */
  async enregistrer(message) {
    const nom = this.demanderNom();
    try {
      const reponse = await submitScore({ name: nom, score: message.score, level: message.level });
      return { entrees: await readScores(), rang: reponse.ranked ? reponse.rank - 1 : null };
    } catch {
      return { entrees: await readScores(), rang: null };
    }
  }

  /** Le nom n'est demande qu'une fois, puis retenu d'une partie a l'autre. */
  demanderNom() {
    let nom = localStorage.getItem(CLE_NOM);
    if (!nom) {
      nom = (prompt("Votre nom pour le classement ?", "JOUEUR") || "").trim() || "ANONYME";
      localStorage.setItem(CLE_NOM, nom);
    }
    return nom;
  }

  // ------------------------------------------------------------------ boucle

  boucle(horodatage) {
    this.renderer.draw(horodatage);
    requestAnimationFrame((t) => this.boucle(t));
  }
}

new Client().start();
