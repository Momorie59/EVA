import { record } from "../voice/latency";
import { useCallback, useEffect, useRef, useState } from "react";
import { CORE_URL, WS_URL, getToken, authHeaders } from "../urls";
import HttpSocket from "../httpSocket";

const TRANSPORT_KEY = "eva.transport";   // « http » : ce réseau bloque les WebSocket (retenu pour cet onglet)


function buildWsUrl(sessionId) {
  const params = new URLSearchParams({ session: sessionId });
  const token = getToken();
  if (token) params.set("token", token);
  const separator = WS_URL.includes("?") ? "&" : "?";
  return `${WS_URL}${separator}${params.toString()}`;
}

const IMG_MARK = /\n?\[\[image:(img-\d+\.png)\]\]/;

function toUiMessages(rows) {
  const mapped = rows.flatMap((m) => {
    const found = m.role === "assistant" ? IMG_MARK.exec(m.content || "") : null;      // image rangée avec la réponse : on la réaffiche
    const msg = {
      id: `h-${m.id}`,
      from: m.role === "user" ? "user" : "eva",
      text: found ? m.content.replace(IMG_MARK, "") : m.content,
      ...(m.role === "assistant" ? { dbId: m.id, rating: m.rating || 0 } : {}),
    };
    return found ? [msg, { id: `h-${m.id}-img`, from: "image", name: found[1] }] : [msg];
  });
  return mapped.length ? mapped : INITIAL_MESSAGES;
}

const INITIAL_MESSAGES = [
  { id: "greeting", from: "eva", text: "Bonjour. Tout fonctionne correctement de mon côté." },
];

const TOOL_LABELS = {
  poser_question: "Question", plan_taches: "Plan de travail", document_creer: "Création du fichier", document_modifier: "Modification du fichier",
  recherche_approfondie: "Recherche approfondie", tache_de_fond: "Tâche en fond", navigateur_ouvrir: "Ouvrir la page", navigateur_lire: "Lire la page",
  navigateur_capture: "Capture d'écran", navigateur_cliquer: "Cliquer sur la page", navigateur_remplir: "Remplir un champ",
  obs_etat: "État d'OBS", obs_action: "Piloter OBS", discord_envoyer: "Publier sur Discord", instagram_stats: "Statistiques Instagram",
  appel_telephone: "Appel téléphonique", device_presence: "Qui est à la maison", device_hue_scene: "Scène Hue",
  fs_tree: "Explorer le projet",
  fs_grep: "Chercher dans le code",
  fs_edit: "Modifier un fichier",
  dev_check: "Vérifier la syntaxe",
  zip_make: "Préparer le ZIP",
  sandbox_run: "Tester dans le bac à sable",
  sandbox_install: "Installer des paquets (bac à sable)",
  sandbox_db: "Base de test",
  fs_list: "Lister un dossier",
  fs_read: "Lire un fichier",
  fs_write: "Écrire un fichier",
  fs_append: "Ajouter à un fichier",
  fs_delete: "Supprimer un fichier",
  project_init: "Créer un projet",
  project_log_decision: "Noter une décision",
  project_log_change: "Noter une modification",
  weather_get: "Consulter la météo",
  api_search: "Chercher une API publique",
  api_get: "Interroger une API publique",
  docker_ps: "Lister les conteneurs",
  docker_logs: "Lire les logs d'un conteneur",
  docker_restart: "Redémarrer un conteneur",
  docker_stop: "Arrêter un conteneur",
  docker_start: "Démarrer un conteneur",
  system_stats: "Mesurer le système",
  terminal_run: "Exécuter une commande",
  web_search: "Chercher sur le web",
  web_fetch: "Lire une page web",
  git_status: "État du dépôt Git",
  git_log: "Historique Git",
  git_diff: "Différences Git",
  git_commit: "Commit Git",
  docs_search: "Chercher dans les documents",
  skill_list: "Lister les skills",
  skill_read: "Charger un skill",
  skill_save: "Créer un skill",
  skill_install: "Installer un skill",
  code_run: "Exécuter du code (bac à sable)",
  delegate: "Déléguer à un assistant",
  self_read: "Lire son propre code",
  self_propose: "Proposer une modification de son code",
  gmail_search: "Chercher dans Gmail",
  gmail_read: "Lire un e-mail",
  gmail_send: "Envoyer un e-mail",
  calendar_list: "Consulter l'agenda",
  calendar_create: "Créer un événement",
  ha_states: "Lire la maison (Home Assistant)",
  ha_get: "Lire un appareil",
  ha_call: "Commander un appareil",
  device_list: "Lister les appareils de la maison",
  device_control: "Commander un appareil de la maison",
  scene_run: "Lancer une scène",
  list_show: "Lire une liste",
  list_add: "Ajouter à une liste",
  list_check: "Cocher un élément d'une liste",
  list_remove: "Retirer d'une liste",
  printer_list: "Lister les imprimantes",
  print_text: "Imprimer un texte",
  print_file: "Imprimer un fichier",
  print_list: "Imprimer une liste",
  net_hosts: "Voir le réseau (dernière analyse)",
  net_scan: "Analyser le réseau",
  net_probe: "Tester une machine du réseau",
  net_http: "Appeler un appareil du réseau",
  net_ssh: "Exécuter une commande sur une machine (SSH)",
  net_inspect: "Inspecter une machine (SSH)",
};

// Fenêtres flottantes (heure, actualités, météo, stats, présentations) : désactivées par défaut, activables dans Paramètres › Apparence.
export const carteMeteoOn = () => { try { return localStorage.getItem("eva.carte_meteo") === "1"; } catch { return false; } };
export const popupsOn = () => { try { return localStorage.getItem("eva.popups") === "1"; } catch { return false; } };

export function useEvaCore({ onReplyComplete, onToken, onAttente, onTurnComplete, onSpeaker, sessionId = "default" } = {}) {
  const [evaState, setEvaState] = useState("idle");
  const [messages, setMessages] = useState(INITIAL_MESSAGES);
  const [connected, setConnected] = useState(false);
  const [offlineReason, setOfflineReason] = useState("connexion en cours…");
  const [transport, setTransport] = useState("ws");
  const echecsWsRef = useRef(0);
  const [lastModel, setLastModel] = useState(null);
  const [activity, setActivity] = useState(null); // tour en cours : {since, tool, done[]} — alimente l'indicateur « EVA réfléchit »
  const [scene, setScene] = useState(null); // présentation affichée en direct (diaporama, météo, heure…)
  const messagesRef = useRef(INITIAL_MESSAGES);

  const socketRef = useRef(null);
  const streamingIdRef = useRef(null);
  const streamingTextRef = useRef("");
  const reconnectTimerRef = useRef(null);
  const onReplyCompleteRef = useRef(onReplyComplete);
  onReplyCompleteRef.current = onReplyComplete;
  const onSpeakerRef = useRef(onSpeaker);
  onSpeakerRef.current = onSpeaker;
  const onTokenRef = useRef(onToken);
  onTokenRef.current = onToken;
  const onAttenteRef = useRef(onAttente);
  onAttenteRef.current = onAttente;
  const onTurnCompleteRef = useRef(onTurnComplete);
  onTurnCompleteRef.current = onTurnComplete;

  const connect = useCallback(() => {
    // Transport : WebSocket d'abord ; si un proxy le bloque (serveur joignable mais WebSocket refusé deux fois de suite),
    // conversation en HTTP ordinaire (httpSocket.js), retenue pour cet onglet.
    const enHttp = (() => { try { return sessionStorage.getItem(TRANSPORT_KEY) === "http"; } catch { return false; } })();
    const socket = enHttp ? new HttpSocket(sessionId) : new WebSocket(buildWsUrl(sessionId));
    socketRef.current = socket;
    setTransport(enHttp ? "http" : "ws");

    let opened = false;
    socket.onopen = () => { opened = true; echecsWsRef.current = 0; setConnected(true); setOfflineReason(""); };

    socket.onclose = (ev) => {
      // Refus avant ouverture (HTTP 403) : le navigateur ne donne pas de code, on fait vérifier la session.
      if (ev && (ev.code === 4401 || !opened)) window.dispatchEvent(new Event("eva:unauthorized"));
      // Socket remplacée (changement de conversation) ou démontée : pas de reconnexion.
      if (socketRef.current !== socket) return;
      setConnected(false);
      // On cherche POURQUOI c'est hors ligne : serveur arrêté, ou serveur là mais connexion temps réel refusée.
      fetch(`${CORE_URL}/api/health`, { cache: "no-store" })
        .then((r) => {
          if (r.ok && !enHttp && !opened && ++echecsWsRef.current >= 2) {
            // Serveur joignable, WebSocket refusé deux fois : proxy probable → on passe en HTTP tout de suite.
            try { sessionStorage.setItem(TRANSPORT_KEY, "http"); } catch { /* ignoré */ }
            clearTimeout(reconnectTimerRef.current);
            setOfflineReason("réseau qui bloque les WebSocket : passage en mode compatible (HTTP)…");
            reconnectTimerRef.current = setTimeout(connect, 300);
            return;
          }
          setOfflineReason(r.ok
            ? (enHttp ? "le serveur répond mais refuse la conversation : session ou jeton invalide (reconnecte-toi)"
              : "le serveur répond mais la connexion temps réel (WebSocket) est refusée : session/jeton invalide ou proxy qui bloque /ws/chat")
            : `le serveur répond une erreur ${r.status} (voir les journaux d'eva-core)`);
        })
        .catch(() => setOfflineReason("EVA redémarre ou est arrêtée (normal pendant une mise à jour : 1 à 3 min) — si ça dure, lance bash diagnostic.sh"));
      // Nouvelle tentative dans 3s — utile pour les coupures réseau
      // ou si EVA CORE redémarre (ex: mise à jour du conteneur).
      reconnectTimerRef.current = setTimeout(connect, 3000);
    };

    socket.onerror = () => socket.close();

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case "state":
          setEvaState(data.state);
          if (data.state === "thinking" || data.state === "acting") setActivity((a) => a || { since: Date.now(), tool: null, done: [] });
          else setActivity(null);
          return;

        case "saved": {
          const id = streamingIdRef.current;
          if (id) setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, dbId: data.message_id, rating: 0 } : m)));
          return;
        }

        case "timing":
          if (data.ttft_ms != null) record("ttft", data.ttft_ms);
          record("total", data.total_ms);
          return;

        case "model":
          setLastModel({ model: data.model, category: data.category, reason: data.reason });
          return;

        case "attente":                       // phrase d'attente à dire à voix haute (« Je regarde la météo. »), jamais affichée
          onAttenteRef.current?.(data.text);
          return;

        case "token": {
          streamingTextRef.current += data.text;
          onTokenRef.current?.(streamingTextRef.current);
          if (!streamingIdRef.current) {
            const id = `eva-${Date.now()}`;
            streamingIdRef.current = id;
            setMessages((prev) => [...prev, { id, from: "eva", text: data.text }]);
          } else {
            const id = streamingIdRef.current;
            setMessages((prev) =>
              prev.map((m) => (m.id === id ? { ...m, text: m.text + data.text } : m))
            );
          }
          return;
        }

        case "stopped": {                     // « Arrêter » : la réponse coupée reste affichée, marquée
          const id = streamingIdRef.current;
          if (id) setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, text: `${m.text}\n\n_(réponse arrêtée)_` } : m)));
          else setMessages((prev) => [...prev, { id: `stop-${Date.now()}`, from: "eva", text: "_(réponse arrêtée)_" }]);
          setActivity(null);
          return;
        }

        case "done": {
          onTurnCompleteRef.current?.();
          const fullText = streamingTextRef.current;
          streamingIdRef.current = null;
          streamingTextRef.current = "";
          if (fullText.trim()) onReplyCompleteRef.current?.(fullText);
          return;
        }

        case "memoire":
          // EVA a retenu d'elle-même ce que la personne a dit d'elle (modifiable dans la page Mémoire).
          if (Array.isArray(data.retenus) && data.retenus.length) {
            setMessages((prev) => [...prev, { id: `mem-${Date.now()}`, from: "system", text: `🧠 Retenu : ${data.retenus.join(" · ")} (page Mémoire pour corriger)`, ts: Date.now() }]);
          }
          return;

        case "tool_result":
          setActivity((a) => a && { ...a, tool: null, done: a.tool ? [...a.done, a.tool] : a.done });
          if ((data.name === "system_stats" || data.name === "ai_server_stats") && data.result && !data.result.error && !popupsOn()) {
            setMessages((prev) => [...prev, { id: `card-${Date.now()}`, from: "card", kind: "stats" }]);
          }
          if (data.name === "system_stats" && data.result && !data.result.error && popupsOn()) setScene({ kind: "stats", data: data.result, id: Date.now() });
          if (data.name === "docker_ps" && data.result?.containers && popupsOn()) {
            const rows = data.result.containers.map((c) => [c.name, c.status, c.image, (c.ports || []).join(", ") || "—"]);
            setScene({ kind: "slides", title: "Conteneurs Docker", id: Date.now(),
              slides: [{ title: `${rows.length} conteneur(s)`, emoji: "🐳", table: { headers: ["Nom", "État", "Image", "Ports"], rows } }] });
          }
          if (data.name === "tache_de_fond") window.dispatchEvent(new Event("eva-taches-fond"));
          if ((data.name === "zip_make" || data.name === "file_deliver" || data.result?.download) && data.result?.path && !data.result.error) {
            setMessages((prev) => [...prev, { id: `dl-${Date.now()}`, from: "download", path: data.result.path, size: data.result.size_bytes, count: data.result.files }]);
          }
          if (data.name === "image_generate" && data.result?.image && !data.result.error) {
            setMessages((prev) => [...prev, { id: `img-${Date.now()}`, from: "image", name: data.result.image, prompt: data.result.prompt_used || "" }]);
          }
          if (data.name === "present" && data.result?.scene && popupsOn()) setScene({ ...data.result.scene, id: Date.now() });
          // Météo : plus de fenêtre qui s'ouvre ; la carte dans la conversation seulement si on l'a demandé (Paramètres › Apparence).
          if (data.name === "weather_get" && data.result && !data.result.error && carteMeteoOn()) {
            setMessages((prev) => [...prev, { id: `card-${Date.now()}`, from: "card", kind: "weather", data: data.result }]);
          }
          return;

        case "speaker":
          onSpeakerRef.current?.(data.name, data.source);
          return;

        case "notes_changed":
          window.dispatchEvent(new Event("eva-notes-changed"));
          return;

        case "notes_visibility":
          window.dispatchEvent(new CustomEvent("eva-notes-visibility", { detail: !!data.visible }));
          return;

        case "image":
          setMessages((prev) => [...prev, { id: `img-${Date.now()}`, from: "image", name: data.name || "", src: data.image, prompt: data.prompt || "" }]);
          return;

        case "scene":
          if (data.scene && data.scene.kind !== "weather" && popupsOn()) setScene({ ...data.scene, id: Date.now() });
          return;

        case "security":
          setMessages((prev) => [
            ...prev,
            { id: `sec-${Date.now()}`, from: "system", text: "⚠️ Contenu suspect : une instruction cachée a été repérée dans le résultat d'un outil. EVA ne la suit pas.", ts: Date.now() },
          ]);
          return;

        case "tool_call": {
          const label = TOOL_LABELS[data.name] || data.name;
          setActivity((a) => ({ since: a?.since || Date.now(), tool: label, done: a?.done || [] }));
          setMessages((prev) => [
            ...prev,
            { id: `tool-${Date.now()}`, from: "system", text: `🔧 ${label}`, ts: Date.now() },
          ]);
          return;
        }

        case "plan": {
          setMessages((prev) => {
            if (!data.plan) return prev.filter((m) => m.id !== "plan");
            return prev.some((m) => m.id === "plan") ? prev.map((m) => (m.id === "plan" ? { ...m, plan: data.plan } : m)) : [...prev, { id: "plan", from: "plan", plan: data.plan }];
          });
          return;
        }

        case "question_request": {
          setMessages((prev) => [...prev, { id: `q-${data.id}`, qid: data.id, from: "question", question: data.question, choix: data.choix || [], plusieurs: !!data.plusieurs, resolved: false }]);
          return;
        }

        case "question_closed": {
          setMessages((prev) => prev.map((m) => (m.qid === data.id ? { ...m, resolved: true } : m)));
          return;
        }

        case "confirm_request": {
          const label = TOOL_LABELS[data.tool] || data.tool;
          setMessages((prev) => [
            ...prev,
            {
              id: `confirm-${Date.now()}`,
              from: "confirm",
              text: data.texte || `EVA veut : ${label} — ${JSON.stringify(data.args)}`,   // phrase unique fournie par EVA CORE
              tool: data.tool,
              args: data.args,
              critique: !!data.critique,
              spoken: data.texte ? data.texte.replace(/^EVA veut /, "").replace(/\.$/, "") : `${label.toLowerCase()}${(() => { const v = Object.values(data.args || {}).find((x) => typeof x === "string" && x.length < 60); return v ? ` : ${v}` : ""; })()}`,
              resolved: false,
            },
          ]);
          return;
        }

        case "proactive": {
          if ((data.text || "").includes("Tâche en fond")) window.dispatchEvent(new Event("eva-taches-fond"));
          if (data.monitor === "rappel") {                 // rappel / minuteur : petit carillon, notification du système, lu à voix haute
            try {
              const ctx = new (window.AudioContext || window.webkitAudioContext)();
              [880, 1175, 1568].forEach((f, i) => {
                const o = ctx.createOscillator(); const g = ctx.createGain();
                o.frequency.value = f; o.connect(g); g.connect(ctx.destination);
                const t = ctx.currentTime + i * 0.18;
                g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);
                o.start(t); o.stop(t + 0.4);
              });
            } catch { /* pas de son possible */ }
            try { if (window.Notification?.permission === "granted") new window.Notification("EVA", { body: data.text }); } catch { /* facultatif */ }
            window.dispatchEvent(new CustomEvent("eva-rappel", { detail: data.text }));
          }
          setMessages((prev) => [
            ...prev,
            { id: `proactive-${Date.now()}`, from: "eva", text: data.text },
          ]);
          onReplyCompleteRef.current?.(data.text);
          return;
        }

        case "error":
          streamingIdRef.current = null;
          streamingTextRef.current = "";
          setMessages((prev) => [
            ...prev,
            { id: `err-${Date.now()}`, from: "eva", text: data.message },
          ]);
          return;

        default:
          return;
      }
    };
  }, [sessionId]);

  // Changement de conversation : on recharge l'historique et on se reconnecte.
  useEffect(() => {
    let cancelled = false;
    streamingIdRef.current = null;
    streamingTextRef.current = "";
    setEvaState("idle");
    setLastModel(null);
    fetch(`${CORE_URL}/api/sessions/${encodeURIComponent(sessionId)}/messages`, {
      headers: authHeaders(),
    })
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) setMessages([...toUiMessages(data.messages || []), ...(data.plan ? [{ id: "plan", from: "plan", plan: data.plan }] : [])]);
      })
      .catch(() => {
        if (!cancelled) setMessages(INITIAL_MESSAGES);
      });

    connect();
    return () => {
      cancelled = true;
      clearTimeout(reconnectTimerRef.current);
      const old = socketRef.current;
      socketRef.current = null;
      old?.close();
    };
  }, [connect, sessionId]);

  const sendMessage = useCallback((text, image, opts = {}) => {
    const names = (opts.files || []).map((f) => f.name);
    const base = image ? `${text || "Que vois-tu ?"} 📷` : (text || (names.length ? "Résume ce fichier." : ""));
    const displayText = names.length ? `${base}\n📎 ${names.join(", ")}` : base;
    setMessages((prev) => [...prev, { id: `user-${Date.now()}`, from: "user", text: displayText }]);

    if (socketRef.current?.readyState === WebSocket.OPEN) {
      const payload = image ? { text, image } : { text };
      if (opts.files?.length) payload.files = opts.files.map((f) => f.path);
      if (opts.voice) payload.voice = true;
      if (opts.speakerToken) payload.speaker_token = opts.speakerToken;
      socketRef.current.send(JSON.stringify(payload));
    } else {
      setEvaState("error");
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          from: "eva",
          text: "EVA CORE n'est pas joignable pour le moment.",
        },
      ]);
    }
  }, []);

  // Bouton « Arrêter » : coupe la réponse en cours (EVA CORE l'arrête aussitôt, AirLLM compris).
  const stop = useCallback(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: "stop" }));
  }, []);

  const rateMessage = useCallback(async (messageId, rating, comment = "") => {
    const patch = (p) => setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, ...p } : m)));
    const msg = messagesRef.current.find((m) => m.id === messageId);
    if (!msg?.dbId) {
      patch({ rating: 0, rateStatus: "error", rateError: "Cette réponse n'a pas encore d'identifiant : recharge la page." });
      return;
    }
    patch({ rating, rateStatus: "saving" });
    try {
      const res = await fetch(`${CORE_URL}/api/messages/${msg.dbId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ rating, comment }),
      });
      if (!res.ok) {
        let detail = `Erreur ${res.status}`;
        try { detail = (await res.json()).detail || detail; } catch { /* corps vide */ }
        throw new Error(detail);
      }
      patch({ rateStatus: "saved" });
    } catch (e) {
      patch({ rating: msg.rating || 0, rateStatus: "error", rateError: `Avis non enregistré (${e.message}).` });
    }
  }, []);

  const respondConfirm = useCallback((messageId, approved, always = false) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === messageId ? { ...m, resolved: true, approved, always: !!(approved && always) } : m))
    );
    socketRef.current?.send(JSON.stringify({ type: "confirm_response", approved, always: !!(approved && always) }));
  }, []);

  const respondQuestion = useCallback((messageId, reponses) => {
    let qid = null;
    setMessages((prev) => prev.map((m) => {
      if (m.id !== messageId) return m;
      qid = m.qid;
      return { ...m, resolved: true, reponses };
    }));
    const id = messageId.replace(/^q-/, "");
    socketRef.current?.send(JSON.stringify({ type: "question_response", id: qid || id, reponses }));
  }, []);

  messagesRef.current = messages;
  return { activity, evaState, setEvaState, scene, setScene, messages, sendMessage, stop, respondConfirm, respondQuestion, connected, offlineReason, transport, lastModel, rateMessage };
}
