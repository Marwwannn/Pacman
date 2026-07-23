/**
 * Dialogue avec le back-end : creation de partie en REST, puis canal WebSocket.
 *
 * Le front ne simule rien. Il envoie des intentions et affiche ce que le
 * serveur lui renvoie : une image par tick. C'est ce qui garantit qu'on ne
 * peut pas tricher en modifiant le client, et que deux onglets ouverts sur la
 * meme partie voient exactement la meme chose.
 */

const BASE = "";

async function json(chemin, options = {}) {
  const reponse = await fetch(BASE + chemin, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!reponse.ok) {
    const detail = await reponse.text().catch(() => "");
    throw new Error(`${options.method || "GET"} ${chemin} → ${reponse.status} ${detail}`);
  }
  return reponse.status === 204 ? null : reponse.json();
}

/** Cree une partie. Renvoie le plan du labyrinthe et l'etat initial. */
export function createGame(options = {}) {
  return json("/api/games", { method: "POST", body: JSON.stringify(options) });
}

/** Abandonne une partie ; le serveur libere sa memoire. */
export function deleteGame(id) {
  return json(`/api/games/${id}`, { method: "DELETE" }).catch(() => null);
}

/** Meilleurs scores, du plus haut au plus bas. */
export function readScores() {
  return json("/api/scores").catch(() => []);
}

/** Propose un score au classement. Declaratif, comme sur une borne. */
export function submitScore(entree) {
  return json("/api/scores", { method: "POST", body: JSON.stringify(entree) });
}

/**
 * Canal temps reel d'une partie.
 *
 * Les messages du serveur sont de trois formes : `init` (plan + etat complet,
 * une seule fois), `state` (etat dynamique et evenements, a chaque tick) et
 * `error`. Le client, lui, n'envoie que des actions.
 */
export class GameLink {
  constructor(gameId, handlers = {}) {
    this.gameId = gameId;
    this.handlers = handlers;
    this.socket = null;
    this.ferme = false;
  }

  get url() {
    const protocole = location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocole}//${location.host}/ws/games/${this.gameId}`;
  }

  connect() {
    this.socket = new WebSocket(this.url);

    this.socket.addEventListener("open", () => this.handlers.onOpen?.());

    this.socket.addEventListener("message", (evenement) => {
      let message;
      try {
        message = JSON.parse(evenement.data);
      } catch {
        return; // message illisible : on ignore plutot que de casser la partie
      }
      if (message.type === "init") this.handlers.onInit?.(message);
      else if (message.type === "state") this.handlers.onState?.(message);
      else if (message.type === "error") this.handlers.onError?.(message.message);
    });

    this.socket.addEventListener("close", (evenement) => {
      if (!this.ferme) this.handlers.onClose?.(evenement);
    });

    return this;
  }

  get ouvert() {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  send(action) {
    if (this.ouvert) this.socket.send(JSON.stringify(action));
  }

  /** Direction voulue par le joueur ; prise en compte au tick suivant. */
  input(direction) {
    this.send({ action: "input", direction });
  }

  pause() {
    this.send({ action: "pause" });
  }

  resume() {
    this.send({ action: "resume" });
  }

  close() {
    this.ferme = true;
    this.socket?.close();
  }
}
