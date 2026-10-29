// Conversation sans WebSocket : même interface qu'un WebSocket (onopen, onmessage, onclose, send, close, readyState),
// mais en HTTP ordinaire (envoi par POST, réception par « long polling »). Sert quand un proxy (réseau d'entreprise,
// hôtel…) bloque les WebSocket : EVA CORE branche la même conversation (voir eva-core/app/chat_http.py).
import { CORE_URL, getToken } from "./urls";

const entetes = () => { const t = getToken(); return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) }; };

export default class HttpSocket {
  static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;

  constructor(sessionId) {
    this.readyState = 0;
    this.onopen = null; this.onmessage = null; this.onclose = null; this.onerror = null;
    this._id = null; this._n = 0; this._file = Promise.resolve();
    this._ouvrir(sessionId);
  }

  async _ouvrir(sessionId) {
    try {
      const r = await fetch(`${CORE_URL}/api/chat-http/ouvrir?session=${encodeURIComponent(sessionId)}`, { method: "POST", headers: entetes() });
      if (!r.ok) return this._fin(r.status === 401 ? 4401 : r.status === 403 ? 4403 : 1006);
      this._id = (await r.json()).id;
      this.readyState = 1;
      this.onopen?.({});
      this._ecouter();
    } catch { this._fin(1006); }
  }

  async _ecouter() {
    while (this.readyState === 1) {
      try {
        const r = await fetch(`${CORE_URL}/api/chat-http/${this._id}/recevoir?apres=${this._n}`, { headers: entetes(), cache: "no-store" });
        if (!r.ok) return this._fin(r.status === 410 ? 1001 : 1006);
        const d = await r.json();
        for (const e of d.evenements || []) {
          this._n = e.n;
          if (this.readyState === 1) this.onmessage?.({ data: JSON.stringify(e.data) });
        }
        if (d.ferme) return this._fin(d.code || 1000);
      } catch { return this._fin(1006); }
    }
  }

  send(texte) {
    if (this.readyState !== 1) return;
    // Envois les uns après les autres, dans l'ordre (un « oui » ne doit pas doubler le message qui l'a précédé).
    this._file = this._file.then(() => fetch(`${CORE_URL}/api/chat-http/${this._id}/envoyer`, { method: "POST", headers: entetes(), body: texte })
      .then((r) => { if (!r.ok) this._fin(1006); }).catch(() => this._fin(1006)));
  }

  close() {
    if (this.readyState >= 2) return;
    if (this._id) fetch(`${CORE_URL}/api/chat-http/${this._id}/fermer`, { method: "POST", headers: entetes(), keepalive: true }).catch(() => {});
    this._fin(1000);
  }

  _fin(code) {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.({ code });
  }
}
