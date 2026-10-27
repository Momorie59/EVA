import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { WS_URL, getToken } from "../urls";
import { api } from "../api";

// Salon : présence, discussion écrite, appels voix/vidéo à plusieurs (WebRTC maillé, sur le réseau local).
// La connexion vit au niveau de l'application : changer d'onglet ne coupe pas un appel.
const roomUrl = () => `${WS_URL}room?token=${encodeURIComponent(getToken())}`;
// Réseau local : aucun serveur nécessaire (EVA reste 100 % local). Pour des amis hors de chez toi, l'administrateur peut ajouter STUN/TURN (page Salon).

export function useSalon(enabled) {
  const [connected, setConnected] = useState(false);
  const [me, setMe] = useState("");
  const [users, setUsers] = useState([]);
  const [messages, setMessages] = useState([]);
  const [participants, setParticipants] = useState([]);
  const [inCall, setInCall] = useState(false);
  const [local, setLocal] = useState(null);
  const [remotes, setRemotes] = useState({});
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(false);
  const [notice, setNotice] = useState("");
  const [typing, setTyping] = useState("");
  const [unread, setUnread] = useState(0);
  const [dms, setDms] = useState({});            // messages privés, rangés par interlocuteur (minuscules)
  const [reads, setReads] = useState({});          // dernier message lu par interlocuteur (heure du serveur)
  const [dmOpen, setDmOpen] = useState([]);        // fenêtres de discussion privée : [{user, min}]
  const [dmTyping, setDmTyping] = useState("");
  const meRef = useRef("");
  const dmTypingTimer = useRef(null);
  const lastDmTyping = useRef(0);
  const visible = useRef(false);
  const iceRef = useRef([]);

  const ws = useRef(null);
  const cid = useRef("");
  const pcs = useRef(new Map());
  const pendingIce = useRef(new Map());
  const localRef = useRef(null);
  const inCallRef = useRef(false);
  const alive = useRef(true);
  const typingTimer = useRef(null);
  const lastTypingSent = useRef(0);

  const send = useCallback((obj) => { const s = ws.current; if (s && s.readyState === 1) s.send(JSON.stringify(obj)); }, []);

  const closePeer = useCallback((id) => {
    const pc = pcs.current.get(id);
    if (pc) { try { pc.close(); } catch { /* déjà fermé */ } pcs.current.delete(id); }
    pendingIce.current.delete(id);
    setRemotes((r) => { if (!(id in r)) return r; const n = { ...r }; delete n[id]; return n; });
  }, []);

  const makePeer = useCallback((id) => {
    if (pcs.current.has(id)) return pcs.current.get(id);
    const pc = new RTCPeerConnection({ iceServers: iceRef.current });
    pcs.current.set(id, pc);
    localRef.current?.getTracks().forEach((t) => {
      const sender = pc.addTrack(t, localRef.current);
      if (t.kind === "video") {          // débit plafonné : l'appel reste fluide à plusieurs et avec des amis à distance
        try { const p = sender.getParameters(); p.encodings = [{ ...(p.encodings?.[0] || {}), maxBitrate: 700000 }]; sender.setParameters(p).catch(() => {}); } catch { /* navigateur sans réglage */ }
      }
    });
    pc.onicecandidate = (e) => { if (e.candidate) send({ type: "signal", to: id, data: { kind: "ice", candidate: e.candidate } }); };
    pc.ontrack = (e) => { const [stream] = e.streams; if (stream) setRemotes((r) => ({ ...r, [id]: stream })); };
    return pc;
  }, [send]);

  const callPeer = useCallback(async (id) => {
    const pc = makePeer(id);
    // sans caméra locale, on réserve quand même une voie vidéo en réception : sinon la personne appelée ne pourrait pas nous envoyer son image
    if (!localRef.current?.getVideoTracks().length) pc.addTransceiver("video", { direction: "recvonly" });
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    send({ type: "signal", to: id, data: { kind: "offer", sdp: pc.localDescription.sdp } });
  }, [makePeer, send]);

  const onSignal = useCallback(async (ev) => {
    const { from, data } = ev;
    if (!inCallRef.current) return;
    try {
      if (data.kind === "offer") {
        const pc = makePeer(from);
        await pc.setRemoteDescription({ type: "offer", sdp: data.sdp });
        (pendingIce.current.get(from) || []).forEach((c) => pc.addIceCandidate(c).catch(() => {}));
        pendingIce.current.delete(from);
        const ans = await pc.createAnswer();
        await pc.setLocalDescription(ans);
        send({ type: "signal", to: from, data: { kind: "answer", sdp: pc.localDescription.sdp } });
      } else if (data.kind === "answer") {
        const pc = pcs.current.get(from);
        if (pc) {
          await pc.setRemoteDescription({ type: "answer", sdp: data.sdp });
          (pendingIce.current.get(from) || []).forEach((c) => pc.addIceCandidate(c).catch(() => {}));
          pendingIce.current.delete(from);
        }
      } else if (data.kind === "ice" && data.candidate) {
        const pc = pcs.current.get(from);
        if (pc && pc.remoteDescription) await pc.addIceCandidate(data.candidate).catch(() => {});
        else pendingIce.current.set(from, [...(pendingIce.current.get(from) || []), data.candidate]);
      }
    } catch (e) { setNotice(`Appel : ${e.message || e}`); }
  }, [makePeer, send]);

  const stopLocal = useCallback(() => {
    localRef.current?.getTracks().forEach((t) => t.stop());
    localRef.current = null; setLocal(null);
  }, []);

  const leaveCall = useCallback(() => {
    if (inCallRef.current) send({ type: "call_leave" });
    inCallRef.current = false; setInCall(false);
    [...pcs.current.keys()].forEach(closePeer);
    stopLocal();
  }, [send, closePeer, stopLocal]);

  const joinCall = useCallback(async (video) => {
    if (inCallRef.current) return;
    setNotice("");
    if (!navigator.mediaDevices?.getUserMedia) { setNotice("Le micro et la caméra demandent une connexion sécurisée (HTTPS). Active-la dans Paramètres › Sécurité."); return; }
    try { iceRef.current = (await api("/api/room/ice")).servers || []; } catch { iceRef.current = []; }
    let stream = null;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: video ? { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 24, max: 30 } } : false }); }
    catch (e) {
      if (video) {
        try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); setNotice("Caméra indisponible : tu rejoins avec le micro seul."); }
        catch (e2) { setNotice(`Micro refusé ou introuvable : ${e2.message || e2}`); return; }
      } else { setNotice(`Micro refusé ou introuvable : ${e.message || e}`); return; }
    }
    localRef.current = stream; setLocal(stream);
    setMicOn(true); setCamOn(stream.getVideoTracks().length > 0);
    inCallRef.current = true; setInCall(true);
    send({ type: "call_join", video: stream.getVideoTracks().length > 0 });
  }, [send]);

  const toggleMic = useCallback(() => {
    const t = localRef.current?.getAudioTracks()[0]; if (!t) return;
    t.enabled = !t.enabled; setMicOn(t.enabled);
  }, []);
  const toggleCam = useCallback(() => {
    const t = localRef.current?.getVideoTracks()[0]; if (!t) return;
    t.enabled = !t.enabled; setCamOn(t.enabled);
  }, []);

  const sendChat = useCallback((text) => { if (text.trim()) send({ type: "chat", text }); }, [send]);
  const notifyTyping = useCallback(() => { const now = Date.now(); if (now - lastTypingSent.current > 2500) { lastTypingSent.current = now; send({ type: "typing" }); } }, [send]);
  const sendDm = useCallback((to, text) => { if (text.trim()) send({ type: "dm", to, text }); }, [send]);
  const markRead = useCallback((user) => send({ type: "dm_read", with: user }), [send]);
  const notifyDmTyping = useCallback((to) => { const now = Date.now(); if (now - lastDmTyping.current > 2500) { lastDmTyping.current = now; send({ type: "dm_typing", to }); } }, [send]);
  const openDm = useCallback((user) => setDmOpen((a) => {
    const low = user.toLowerCase();
    const rest = a.filter((w) => w.user.toLowerCase() !== low);
    return [...rest, { user, min: false }].slice(-3);               // 3 fenêtres au plus : l'écran reste lisible
  }), []);
  const closeDm = useCallback((user) => setDmOpen((a) => a.filter((w) => w.user.toLowerCase() !== user.toLowerCase())), []);
  const minDm = useCallback((user, min) => setDmOpen((a) => a.map((w) => (w.user.toLowerCase() === user.toLowerCase() ? { ...w, min } : w))), []);
  // non lus par personne : messages reçus après le dernier « lu »
  const dmUnread = useMemo(() => {
    const out = {};
    Object.entries(dms).forEach(([peer, list]) => {
      const n = list.filter((m) => m.from.toLowerCase() === peer && m.ts > (reads[peer] || 0)).length;
      if (n) out[peer] = n;
    });
    return out;
  }, [dms, reads]);
  const dmTotal = Object.values(dmUnread).reduce((a, b) => a + b, 0);
  const setVisible = useCallback((v) => { visible.current = v; if (v) setUnread(0); }, []);

  useEffect(() => {
    alive.current = true;
    if (!enabled) return undefined;
    let retry = null;
    const connect = () => {
      let s;
      try { s = new WebSocket(roomUrl()); } catch { retry = setTimeout(connect, 4000); return; }
      ws.current = s;
      s.onopen = () => setConnected(true);
      s.onclose = (e) => {
        setConnected(false);
        if (inCallRef.current) { inCallRef.current = false; setInCall(false); [...pcs.current.keys()].forEach(closePeer); stopLocal(); setNotice("Connexion perdue : l'appel a été interrompu."); }
        if (alive.current && e.code !== 4401 && e.code !== 4403) retry = setTimeout(connect, 3000);
      };
      s.onmessage = (m) => {
        let ev; try { ev = JSON.parse(m.data); } catch { return; }
        if (ev.type === "hello") { cid.current = ev.cid; meRef.current = ev.me; setDms(ev.dms || {}); setReads(ev.reads || {}); setMe(ev.me); setUsers(ev.users); setParticipants(ev.call); setMessages(ev.history); }
        else if (ev.type === "presence") {
          setUsers(ev.users); setParticipants(ev.call);
          const ids = new Set(ev.call.map((p) => p.cid));
          [...pcs.current.keys()].forEach((id) => { if (!ids.has(id)) closePeer(id); });
        }
        else if (ev.type === "chat") {
          setMessages((a) => [...a.slice(-299), ev.msg]);
          if (!visible.current && ev.msg.user !== meRef.current) setUnread((n) => n + 1);
          setTyping("");
        }
        else if (ev.type === "dm") {
          const m = ev.msg;
          const mine = m.from.toLowerCase() === meRef.current.toLowerCase();
          const peer = (mine ? m.to : m.from).toLowerCase();
          setDms((d) => ({ ...d, [peer]: [...(d[peer] || []).filter((x) => x.id !== m.id), m].slice(-200) }));
          if (!mine) {
            setDmTyping("");
            setDmOpen((a) => (a.some((w) => w.user.toLowerCase() === peer) ? a : [...a, { user: m.from, min: true }].slice(-3)));   // la fenêtre s'ouvre repliée, avec sa pastille
          }
        }
        else if (ev.type === "dm_read") setReads((r) => ({ ...r, [ev.with]: ev.ts }));
        else if (ev.type === "dm_typing") { setDmTyping(ev.user); clearTimeout(dmTypingTimer.current); dmTypingTimer.current = setTimeout(() => setDmTyping(""), 3000); }
        else if (ev.type === "typing") { setTyping(ev.user); clearTimeout(typingTimer.current); typingTimer.current = setTimeout(() => setTyping(""), 3000); }
        else if (ev.type === "call_joined") ev.peers.forEach((p) => callPeer(p.cid).catch((e) => setNotice(`Appel : ${e.message || e}`)));
        else if (ev.type === "signal") onSignal(ev);
        else if (ev.type === "notice") setNotice(ev.text);
      };
    };
    connect();
    return () => {
      alive.current = false; clearTimeout(retry); clearTimeout(typingTimer.current); clearTimeout(dmTypingTimer.current);
      inCallRef.current = false; [...pcs.current.keys()].forEach(closePeer); stopLocal();
      try { ws.current?.close(); } catch { /* fermé */ }
      setConnected(false); setInCall(false);
    };
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  return { connected, me, users, messages, participants, inCall, local, remotes, micOn, camOn, notice, typing, unread, dms, dmUnread, dmTotal, dmOpen, dmTyping, sendDm, markRead, notifyDmTyping, openDm, closeDm, minDm, myCid: cid, joinCall, leaveCall, toggleMic, toggleCam, sendChat, notifyTyping, setVisible, clearNotice: () => setNotice("") };
}
