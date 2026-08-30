/**
 * Assemblage du client.
 *
 * Ce fichier ne connait aucune regle du jeu : il cree une partie, branche le
 * canal temps reel sur la vue, et fait tourner la boucle d'affichage. Toute la
 * logique est ailleurs : au back-end pour le jeu, dans les modules voisins
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

// `?ia=appris` : on regarde un agent jouer au lieu de jouer soi-meme. Le
// serveur ignore alors les entrees de direction ; la pause reste au spectateur.
const PILOTE = new URLSearchParams(location.search).get("ia");
const PILOTES = {
  aleatoire: "agent aléatoire",
  heuristique: "heuristique écrite à la main",
  appris: "agent appris : Q-learning approximé",
  recherche: "recherche en ligne : profondeur 3",
};
const LIBELLE_IA = PILOTES[PILOTE] ?? "agent inconnu";

const AIDE = `
  <b>Flèches</b> ou <b>WASD</b> pour se déplacer ·
  <b>Espace</b> pour la pause<br>
  Appuyez sur <span class="touche">Entrée</span> pour commencer.<br>
  Ou regardez <b>l'IA jouer</b> :
  <a href="?ia=appris">agent appris</a> ·
  <a href="?ia=recherche">recherche</a> ·
  <a href="?ia=heuristique">heuristique</a> ·
  <a href="?ia=aleatoire">aléatoire</a>
`;
const AIDE_SPECTATEUR = `
  L'IA joue : <b>${LIBELLE_IA}</b> · <b>Espace</b> pour la pause<br>
  Appuyez sur <span class="touche">Entrée</span> pour lancer une partie ·
  <a href="/">jouer soi-même</a>
`;
const CONSIGNES = PILOTE ? AIDE_SPECTATEUR : AIDE;

class Client {
  constructor() {
    this.view = new GameView();
    this.hud = new Hud();
    this.sons = new Sounds();
    this.renderer = new Renderer(document.getElementById("board"), this.view);
    this.controls = new Controls(document.getElementById("board"), {
      onDirection: (direction) => {
        if (!PILOTE) this.link?.input(direction);
      },
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
    // Un spectateur a deja dit ce qu'il voulait en ouvrant `?ia=...` : la
    // partie demarre seule. Les bruitages restent muets tant qu'aucune touche
    // n'a ete pressee : le navigateur l'impose, et `Sounds.play` le sait.
    if (PILOTE) this.nouvellePartie();
    requestAnimationFrame((t) => this.boucle(t));
  }

  async ecranTitre() {
    const classement = await readScores();
    if (classement.length) {
      this.record = Math.max(this.record, classement[0].score);
      this.hud.setBest(this.record);
    }
    this.hud.showOverlay(PILOTE ? "L'IA joue" : "Pac-Man", CONSIGNES + formatScores(classement));
    this.hud.setStatus(PILOTE ? `Prêt : ${LIBELLE_IA}` : "Prêt à jouer");
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
      const partie = await createGame(PILOTE ? { maze: "classic", pilot: PILOTE } : { maze: "classic" });
      this.gameId = partie.state.id;
      this.renderer.setMaze(partie.maze);
      this.brancher();
    } catch (erreur) {
      this.enCours = false;
      const inconnu = PILOTE && /422/.test(erreur.message);
      this.hud.setStatus(inconnu ? "IA inconnue" : `Serveur injoignable : ${erreur.message}`, true);
      this.hud.showOverlay(
        inconnu ? "IA inconnue" : "Hors service",
        inconnu
          ? 'Aucun agent de ce nom. <a href="/">Retour</a>'
          : "Le back-end ne répond pas. Relancez <b>pacman-server</b>."
      );
    }
  }

  brancher() {
    this.link = new GameLink(this.gameId, {
      onInit: (message) => {
        this.view.applyInit(message);
        this.hud.update(message.state);
        this.hud.hideOverlay();
        this.hud.setStatus(PILOTE ? `L'IA joue : ${LIBELLE_IA}` : "Bonne chance !");
      },
      onState: (message) => this.surEtat(message),
      onError: (message) => this.hud.setStatus(message, true),
      onClose: () => {
        if (this.terminee) return;
        this.enCours = false;
        this.hud.setStatus("Connexion perdue", true);
        this.hud.showOverlay("Déconnecté", "La partie s'est interrompue.<br>" + CONSIGNES);
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

    if (!PILOTE && message.score > this.record) {
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

    if (PILOTE) {
      // Le score d'une IA n'a rien a faire dans le classement des joueurs.
      this.hud.showOverlay(
        "Partie de l'IA terminée",
        `Score <b>${message.score}</b> · niveau <b>${message.level}</b><br>` +
          `Appuyez sur <span class="touche">Entrée</span> pour une nouvelle partie · ` +
          `<a href="/">jouer soi-même</a>`
      );
      if (this.gameId) deleteGame(this.gameId);
      this.gameId = null;
      return;
    }

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
