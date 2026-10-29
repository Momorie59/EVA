import PageGuide from "./PageGuide";
import HelpLayer from "./components/HelpLayer";
import SalonDock from "./components/SalonDock";
import SalonPage from "./components/pages/SalonPage";
import NotebooksPage from "./components/pages/NotebooksPage";
import { useSalon } from "./hooks/useSalon";
import ErrorBoundary from "./ErrorBoundary";
import { useEffect, useRef, useState } from "react";
import LogoCore from "./components/LogoCore";
import TopBar from "./components/TopBar";
import StatusLine from "./components/StatusLine";
import WidgetArc from "./components/WidgetArc";
import ChatDrawer from "./components/ChatDrawer";
import ControlDock from "./components/ControlDock";
import DashboardPanel from "./components/DashboardPanel";
import Sidebar, { NAV_ITEMS } from "./components/Sidebar";
import ChatPage from "./components/pages/ChatPage";
import AgentsPage from "./components/pages/AgentsPage";
import SkillsPage from "./components/pages/SkillsPage";
import SourcesPage from "./components/pages/SourcesPage";
import TracesPage from "./components/pages/TracesPage";
import LearningPage from "./components/pages/LearningPage";
import EvolutionPage from "./components/pages/EvolutionPage";
import OverviewPage from "./components/pages/OverviewPage";
import LogsPage from "./components/pages/LogsPage";
import SettingsPage from "./components/pages/SettingsPage";
import ProjectsPage from "./components/pages/ProjectsPage";
import MaisonPage from "./components/pages/MaisonPage";
import ListesPage from "./components/pages/ListesPage";
import PapiersPage from "./components/pages/PapiersPage";
import WikiPage from "./components/pages/WikiPage";
import RecettesPage from "./components/pages/RecettesPage";
import InventairePage from "./components/pages/InventairePage";
import Miroir from "./components/Miroir";
import FinancesPage from "./components/pages/FinancesPage";
import ContenusPage from "./components/pages/ContenusPage";
import ImagesPage from "./components/pages/ImagesPage";
import SimpleShell from "./components/SimpleShell";
import { useAuth } from "./components/AuthGate";
import { MemoryPage } from "./components/pages/ListPages";
import { useIsDesktop } from "./hooks/useIsDesktop";
import { useSessions } from "./hooks/useSessions";
import HudRings from "./components/HudRings";
import CameraPanel from "./components/CameraPanel";
import SceneStage from "./components/SceneStage";
import HandCursor from "./components/HandCursor";
import LiveCheck from "./components/LiveCheck";
import { isClearCommand, isVerifyCommand } from "./voice/speech";
import { useEvaCore } from "./hooks/useEvaCore";
import { api } from "./api";
import { useVoice } from "./hooks/useVoice";
import { useWakeWord } from "./hooks/useWakeWord";
import { useGestures } from "./hooks/useGestures";
import { useMusique, QUESTION_MUSIQUE } from "./hooks/useMusique";
import { useVoicePrefs } from "./hooks/useVoicePrefs";
import { useIdentity } from "./hooks/useIdentity";
import { nextSpeakable, parseYesNo } from "./voice/speech";
import ThemeDrawer from "./components/ThemeDrawer";
import NotesLayer, { NoteAdder } from "./components/NotesLayer";
import { uploadFile, imageToPending } from "./attach";
import { useNotes } from "./hooks/useNotes";
import { useTheme } from "./theme/store";
import "./App.css";
import "./theme/theme.css";

export default function App() {
  const auth = useAuth();
  const admin = !auth.required || auth.role === "admin";
  const salon = useSalon(auth.required && (auth.role === "admin" || (auth.features || []).includes("salon")));
  const [cameraPanelOpen, setCameraPanelOpen] = useState(false);
  const [pendingImage, setPendingImage] = useState(null);
  const [pendingFiles, setPendingFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [attachError, setAttachError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [view, setView] = useState("home");
  const isDesktop = useIsDesktop();
  const [theme, setTheme] = useTheme();
  const L = theme.layout;
  const [themeOpen, setThemeOpen] = useState(false);
  const notes = useNotes();
  const [menuOpen, setMenuOpen] = useState(false);
  const activeView = view;
  const goto = (v) => { setView(v); setMenuOpen(false); };
  // Mode miroir (écran derrière un miroir sans tain) : adresse « ?miroir » (kiosque) ou bouton dans Maison › Miroir.
  const [miroir, setMiroir] = useState(() => { try { return new URLSearchParams(window.location.search).has("miroir"); } catch { return false; } });
  useEffect(() => { const ouvrir = () => setMiroir(true); window.addEventListener("eva:miroir", ouvrir); return () => window.removeEventListener("eva:miroir", ouvrir); }, []);
  const quitterMiroir = () => {
    setMiroir(false);
    try { const u = new URL(window.location.href); if (u.searchParams.has("miroir")) { u.searchParams.delete("miroir"); window.history.replaceState(null, "", u); } } catch { /* ignoré */ }
  };
  // Ne parle à voix haute que si la dernière question venait du micro —
  // pas si on lui a écrit, pour ne pas surprendre en silence.
  const lastInputWasVoiceRef = useRef(false);
  const spokenRef = useRef(0); // nombre de caractères de la réponse en cours déjà envoyés à la lecture

  const [sessionId, setSessionId] = useState(() => {
    try {
      return window.localStorage.getItem("eva.session") || "default";
    } catch {
      return "default";
    }
  });
  const conversations = useSessions();

  // À l'ouverture d'EVA : toujours une NOUVELLE discussion (on ne reprend pas la dernière, qui peut parler d'un projet).
  // Une discussion vide déjà existante est réutilisée pour ne pas en empiler ; l'historique reste dans la barre latérale.
  const startedRef = useRef(false);
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    (async () => {
      try {
        const data = await api("/api/sessions");
        const list = data.sessions || [];
        // Seulement une discussion vide À SOI : l'administrateur voit aussi celles des autres (owner rempli), il ne doit jamais écrire dedans.
        const empty = list.find((x) => !x.message_count && x.id !== "default" && !x.owner);
        const id = empty ? empty.id : await conversations.create();
        setSessionId(id);
        window.localStorage.setItem("eva.session", id);
      } catch { /* EVA CORE injoignable : on garde la discussion mémorisée */ }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function openSession(id) {
    setSessionId(id);
    setView("chat");
    setMenuOpen(false);
    try {
      window.localStorage.setItem("eva.session", id);
    } catch {
      /* stockage indisponible : on garde juste l'état en mémoire */
    }
  }

  const [voicePrefs, setVoicePrefs] = useVoicePrefs();
  const [liveOpen, setLiveOpen] = useState(false);
  const hintRef = useRef(null);
  const { activity, evaState, setEvaState, scene, setScene, messages, sendMessage, stop, respondConfirm, respondQuestion, connected, offlineReason, transport, lastModel, rateMessage } = useEvaCore({
    sessionId,
    onTurnComplete: conversations.refresh,
    onSpeaker: (name, source) => hintRef.current?.(name, source),
    // Lecture au fil de l'eau : chaque phrase complète est lue dès qu'elle arrive, sans attendre la fin.
    onToken: (textSoFar) => {
      if (!(lastInputWasVoiceRef.current || voicePrefs.speakAll)) return;
      const { chunks, upto } = nextSpeakable(textSoFar, spokenRef.current);
      spokenRef.current = upto;
      chunks.forEach((c) => voice.enqueue(c));
    },
    onAttente: (text) => {
      if (lastInputWasVoiceRef.current) voice.enqueue(text);
    },
    onReplyComplete: (text) => {
      if (lastInputWasVoiceRef.current || voicePrefs.speakAll) voice.enqueue(text.slice(spokenRef.current));
      spokenRef.current = 0;
    },
  });

  useEffect(() => {
    const onVis = (e) => setTheme((t) => ({ ...t, layout: { ...t.layout, notes: !!e.detail } }));
    window.addEventListener("eva-notes-visibility", onVis);
    return () => window.removeEventListener("eva-notes-visibility", onVis);
  }, [setTheme]);

  const identity = useIdentity();
  hintRef.current = identity.hint;
  const identityRef = useRef(identity);
  identityRef.current = identity;
  // Phrase dite : on identifie la voix en même temps (jamais bloquant), puis on envoie.
  function clearScreen() {
    setScene(null);
    setView("home");
    voice.stopSpeaking();
  }
  async function sendSpoken(text, blob) {
    // Une action sensible attend ta réponse : « oui » / « non » à voix haute suffit.
    const waiting = [...messagesRef.current].reverse().find((m) => m.from === "confirm" && !m.resolved);
    const yn = waiting ? parseYesNo(text) : null;
    if (waiting && yn) {
      respondConfirm(waiting.id, yn === "yes");
      voice.speak(yn === "yes" ? "D'accord, je le fais." : "D'accord, j'annule.");
      return;
    }
    if (QUESTION_MUSIQUE.test(text)) {
      voice.speak("J'écoute.");
      const r = await musique.ecouter();
      if (r?.phrase) voice.speak(r.phrase);
      return;
    }
    if (isClearCommand(text)) return clearScreen();
    if (isVerifyCommand(text)) return setLiveOpen(true);
    lastInputWasVoiceRef.current = true;
    spokenRef.current = 0;
    const token = await identityRef.current.forVoice(blob);
    sendMessage(text, undefined, { voice: true, speakerToken: token || undefined });
  }

  const gestures = useGestures({ enabled: voicePrefs.gestures });
  const musique = useMusique();
  const wakeApiRef = useRef(null);
  const messagesRef = useRef([]);
  messagesRef.current = messages;
  // Quand EVA demande une confirmation après une demande vocale, elle la pose à voix haute.
  const askedRef = useRef(new Set());
  useEffect(() => {
    const m = [...messages].reverse().find((x) => x.from === "confirm" && !x.resolved);
    if (!m || askedRef.current.has(m.id) || !lastInputWasVoiceRef.current) return;
    askedRef.current.add(m.id);
    voice.speak(`Je dois te demander confirmation : ${m.spoken}. Tu confirmes ? Dis oui ou non.`);
  }, [messages]); // eslint-disable-line react-hooks/exhaustive-deps
  const voice = useVoice({
    onTranscript: (text, blob) => sendSpoken(text, blob),
    // Après une réponse parlée, on reste à l'écoute quelques secondes (question de suivi sans redire « EVA »).
    onSpeakEnd: () => wakeApiRef.current?.listenAgain(6000),
  });

  useEffect(() => {                                    // rappel ou minuteur : toujours lu à voix haute
    const dire = (e) => voice.enqueue(String(e.detail || "").replace(/^⏰\s*/, ""));
    window.addEventListener("eva-rappel", dire);
    return () => window.removeEventListener("eva-rappel", dire);
  }, [voice]);

  // Pouce levé / baissé devant la caméra : répond « oui » / « non » à la demande d'accord en attente.
  useEffect(() => {
    const onGesture = (e) => {
      if (e.detail !== "yes" && e.detail !== "no") return;
      const waiting = [...messagesRef.current].reverse().find((m) => m.from === "confirm" && !m.resolved);
      if (!waiting) return;
      respondConfirm(waiting.id, e.detail === "yes");
      if (voicePrefs.speakAll || lastInputWasVoiceRef.current) voice.speak(e.detail === "yes" ? "D'accord, je le fais." : "D'accord, j'annule.");
    };
    window.addEventListener("eva-gesture", onGesture);
    return () => window.removeEventListener("eva-gesture", onGesture);
  }, [respondConfirm, voice, voicePrefs.speakAll]);

  const busy = evaState === "thinking" || evaState === "acting";
  const wakeWord = useWakeWord({
    enabled: voicePrefs.wake,
    word: voicePrefs.word,
    engine: voicePrefs.engine,
    paused: voice.isSpeaking || voice.isRecording,
    onCommand: (text, blob) => {
      voice.stopSpeaking();
      sendSpoken(text, blob);
    },
  });
  wakeApiRef.current = wakeWord;

  // Dès que l'utilisateur commence à parler (mot d'éveil ou micro), on charge le modèle rapide en mémoire.
  useEffect(() => {
    if (wakeWord.phase === "awake" || voice.isRecording) api("/api/models/warm", { method: "POST", body: "{}" }).catch(() => {});
  }, [wakeWord.phase, voice.isRecording]);

  // L'anneau d'état reflète la voix : écoute (réveillée) / parole.
  useEffect(() => {
    if (voice.isSpeaking) setEvaState("speaking");
    else setEvaState((s) => (s === "speaking" ? "idle" : s));
  }, [voice.isSpeaking, setEvaState]);
  useEffect(() => {
    if (wakeWord.phase === "awake") setEvaState((s) => (s === "idle" ? "listening" : s));
    else setEvaState((s) => (s === "listening" && !voice.isRecording ? "idle" : s));
  }, [wakeWord.phase, voice.isRecording, setEvaState]);

  async function handleToggleMic() {
    if (voice.isRecording) {
      voice.stopRecording();
      setEvaState("thinking");
    } else {
      const started = await voice.startRecording();
      if (started) setEvaState("listening");
    }
  }

  async function addFiles(list) {
    setAttachError("");
    for (const f of Array.from(list || [])) {
      try {
        if (f.type.startsWith("image/")) { setPendingImage(await imageToPending(f)); continue; }
        setUploading(true);
        const info = await uploadFile(f);
        setPendingFiles((prev) => [...prev, info].slice(-6));
      } catch (e) { setAttachError(`${f.name} : ${e.message}`); }
    }
    setUploading(false);
  }

  function handleTextSend(text, image) {
    const files = pendingFiles;
    if (!image && !files.length && isClearCommand(text)) return clearScreen();
    if (!image && isVerifyCommand(text)) return setLiveOpen(true);
    lastInputWasVoiceRef.current = false;
    spokenRef.current = 0;
    sendMessage(text, image, { speakerToken: identity.forText() || undefined, files });
    if (image) setPendingImage(null);
    if (files.length) setPendingFiles([]);
  }

  const pendingConfirms = messages.filter((m) => m.from === "confirm" && !m.resolved).length;

  const pages = {
    chat: (
      <ChatPage
        messages={messages}
        onSend={handleTextSend}
        onConfirm={respondConfirm}
        onQuestion={respondQuestion}
        pendingImage={pendingImage}
        onRemoveImage={() => setPendingImage(null)}
        onPickImage={setPendingImage}
        pendingFiles={pendingFiles} uploading={uploading} attachError={attachError} onAttach={addFiles} onRemoveFile={(p) => setPendingFiles((a) => a.filter((f) => f.path !== p))}
        onOpenCamera={() => setCameraPanelOpen(true)}
        sessionId={sessionId}
        lastModel={lastModel}
        evaState={evaState} activity={activity}
        onRate={rateMessage}
        onStop={() => { stop(); voice.stopSpeaking(); }}
      />
    ),
    overview: <OverviewPage />,
    agents: <AgentsPage />,
    skills: <SkillsPage />,
    sources: <SourcesPage />,
    traces: <TracesPage />,
    learning: <LearningPage />,
    evolution: <EvolutionPage />,
    projects: <ProjectsPage onOpenSession={openSession} onNewInProject={async (slug) => {
      const id = await conversations.create();
      await api(`/api/sessions/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ project: slug }) });
      await conversations.refresh();
      openSession(id);
    }} />,
    maison: <MaisonPage />,
    salon: <SalonPage salon={salon} />,
    carnets: <NotebooksPage />,
    images: <ImagesPage />,
    lists: <ListesPage />,
    papiers: <PapiersPage />,
    wiki: <WikiPage />,
    recettes: <RecettesPage />,
    inventaire: <InventairePage />,
    finances: <FinancesPage />,
    contenus: <ContenusPage />,
    memory: <MemoryPage />,
    logs: <LogsPage messages={messages} />,
    settings: <SettingsPage connected={connected} offlineReason={offlineReason} />,
  };

  const chatDrawer = (
    <ChatDrawer
      onRate={rateMessage}
      messages={messages}
      onSend={handleTextSend}
      onStop={() => { stop(); voice.stopSpeaking(); }} evaState={evaState}
      onConfirm={respondConfirm}
        onQuestion={respondQuestion}
      pendingImage={pendingImage}
      onRemoveImage={() => setPendingImage(null)}
      pendingFiles={pendingFiles} uploading={uploading} attachError={attachError} onAttach={addFiles} onRemoveFile={(p) => setPendingFiles((a) => a.filter((f) => f.path !== p))}
      sessionId={sessionId} lastModel={lastModel}
    />
  );
  const lastReplyMsg = [...messages].reverse().find((m) => m.from === "eva" && m.text);
  const lastReply = lastReplyMsg ? { id: lastReplyMsg.id, text: lastReplyMsg.text.slice(0, 320) } : null;

  if (miroir) {
    return (
      <Miroir onQuitter={quitterMiroir} onMicro={handleToggleMic} onDire={(t) => voice.speak(t)}
        ecoute={voice.isRecording || wakeWord.phase === "awake"} parle={voice.isSpeaking} etat={evaState}
        derniereReponse={lastReply} connecte={connected} />
    );
  }

  if (!admin) {
    return (
      <SimpleShell pages={{ chat: pages.chat, images: pages.images, lists: pages.lists, papiers: pages.papiers, wiki: pages.wiki, recettes: pages.recettes, inventaire: pages.inventaire, salon: pages.salon, carnets: pages.carnets, maison: pages.maison, projects: pages.projects }} onMic={handleToggleMic} recording={voice.isRecording} speaking={voice.isSpeaking} sessions={conversations.sessions} activeId={sessionId}
        onOpen={openSession} onNew={async () => openSession(await conversations.create())} connected={connected} salon={salon} />
    );
  }

  return (
    <div className="app" data-view={activeView}
      onDragOver={(e) => { if (e.dataTransfer?.types?.includes("Files")) { e.preventDefault(); setDragging(true); } }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false); }}
      onDrop={(e) => { if (e.dataTransfer?.files?.length) { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); } }}>
      {dragging && <div className="drop-overlay">Dépose ton fichier ici</div>}
      <HelpLayer view={activeView} />
      <SalonDock salon={salon} />
      <Sidebar
        view={activeView}
        onSelect={goto}
        mobileOpen={menuOpen}
        connected={connected}
        transport={transport}
        offlineReason={offlineReason}
        pendingConfirms={pendingConfirms}
        badges={{ salon: salon.unread + salon.dmTotal }}
        conversations={{
          ...conversations,
          activeId: sessionId,
          onOpen: openSession,
          onNew: async () => openSession(await conversations.create()),
          onDelete: async (id) => {
            await conversations.remove(id);
            if (id === sessionId) openSession(await conversations.create());
          },
          onDeleteMany: async (body, ids) => {
            const n = await conversations.removeMany(body);
            if (body.tout || (ids || []).includes(sessionId)) openSession(await conversations.create());
            return n;
          },
        }}
      />

      <div className={`app-main ${activeView === "home" ? "is-home" : ""}`}>
        {activeView !== "home" ? (
          <>
            <header className="mobile-bar">
              <button className="menu-btn" onClick={() => setMenuOpen(true)} aria-label="Menu">☰</button>
              <span className="mobile-bar__title">{NAV_ITEMS.find((n) => n.id === activeView)?.label}</span>
              <button className="menu-btn" onClick={() => goto("home")} aria-label="Accueil">◎</button>
            </header>
            {activeView !== "chat" && <PageGuide id={activeView} />}
            <ErrorBoundary resetKey={activeView}>{pages[activeView]}</ErrorBoundary>
          </>
        ) : (
          <>
            <TopBar connected={connected} offlineReason={offlineReason} who={identity.who} onMenu={() => setMenuOpen(true)} onSettings={() => goto("settings")} canVerify={identity.canVerify} onVerify={() => setLiveOpen(true)}
              onCommand={(t) => handleTextSend(t)} onTheme={() => setThemeOpen(true)}
              speaking={voice.isSpeaking} speakOn={voicePrefs.speakAll} onStopSpeaking={voice.stopSpeaking} onToggleSpeak={() => setVoicePrefs({ speakAll: !voicePrefs.speakAll })}
              extra={<NoteAdder onAdd={notes.add} count={notes.notes.filter((n) => !n.done).length} trash={notes.notes.filter((n) => n.done)} onRestore={(id) => notes.patch(id, { done: false })} onPurge={notes.remove} onEmptyTrash={() => notes.clear(true)} visible={L.notes} onToggleVisible={() => setTheme((t) => ({ ...t, layout: { ...t.layout, notes: !t.layout.notes } }))} />} />

            <aside className="hud-left">
              {isDesktop ? (
                <>
                  {L.widgets === "left" && <div className="hud-widgets"><WidgetArc /></div>}
                  {L.chat === "left" && <div className="hud-chat">{chatDrawer}</div>}
                </>
              ) : <WidgetArc />}
            </aside>

            <main className="avatar-stage">
              <HudRings evaState={evaState} />
              <LogoCore evaState={evaState} />
              <div className="hud-frame" aria-hidden="true">
                <span className="hud-corner hud-corner--tl" />
                <span className="hud-corner hud-corner--tr" />
                <span className="hud-corner hud-corner--bl" />
                <span className="hud-corner hud-corner--br" />
                <span className="hud-scan" />
              </div>
            </main>

            <StatusLine evaState={evaState} onStateChange={setEvaState} />
            {isDesktop && L.chat === "hidden" && lastReply && <p className="hud-reply" data-testid="hud-reply" key={lastReply.id}>{lastReply.text}</p>}

            <ControlDock
              micOn={voice.isRecording}
              speakOn={voicePrefs.speakAll}
              onToggleSpeak={() => setVoicePrefs({ speakAll: !voicePrefs.speakAll })}
              wakeOn={voicePrefs.wake}
              wakePhase={wakeWord.phase}
              wakeWord={voicePrefs.word}
              wakeError={wakeWord.error || voice.error}
              wakeLevel={wakeWord.level}
              wakeHeard={wakeWord.heard}
              wakeBusy={wakeWord.busy}
              thinking={busy}
              onToggleWake={() => setVoicePrefs({ wake: !voicePrefs.wake })}
              speaking={voice.isSpeaking}
              onStopSpeaking={voice.stopSpeaking}
              onMusique={musique.ecouter}
              musiqueOn={musique.etat === "ecoute" || musique.etat === "analyse"}
              cameraOn={cameraPanelOpen}
              onToggleMic={handleToggleMic}
              onToggleCamera={() => setCameraPanelOpen((v) => !v)}
              onOpenDashboard={() => (isDesktop ? setView("projects") : setDashboardOpen(true))}
            />

            <aside className="hud-right">
              {isDesktop ? (
                <>
                  {L.widgets === "right" && <div className="hud-widgets"><WidgetArc /></div>}
                  {L.chat === "right" && <div className="hud-chat">{chatDrawer}</div>}
                </>
              ) : chatDrawer}
            </aside>

            {isDesktop && L.widgets === "bottom" && <div className="hud-bottom"><WidgetArc /></div>}
          </>
        )}
      </div>

      {activeView === "home" && <NotesLayer notes={notes.notes.filter((n) => !n.done)} visible={L.notes} onPatch={notes.patch} onRemove={notes.remove} />}
      <ThemeDrawer open={themeOpen} onClose={() => setThemeOpen(false)} />

      <LiveCheck open={liveOpen} onClose={() => setLiveOpen(false)} onVerified={identity.acceptLive} />

      {gestures.state === "ready" && <div className="gesture-badge" data-testid="gesture-badge" title="Gestes actifs">✋{gestures.last ? ` ${{ next: "suivante →", prev: "← précédente", pin: "📌", clear: "effacé", summarize: "résumé", yes: "👍 oui", no: "👎 non" }[gestures.last] || ""}` : ""}</div>}
      {gestures.state === "ready" && <HandCursor />}
      {musique.etat !== "off" && (
        <div className="musique-carte" role="status" data-testid="musique-carte">
          {musique.etat === "ecoute" && <>🎵 J'écoute… <b>{musique.reste} s</b><span className="page__sub"> Approche le téléphone ou l'ordinateur de la musique.</span></>}
          {musique.etat === "analyse" && <>🎵 Je cherche…</>}
          {(musique.etat === "fini" || musique.etat === "erreur") && musique.resultat && (
            musique.resultat.trouve
              ? <><b>{musique.resultat.titre}</b>{musique.resultat.artiste && <> — {musique.resultat.artiste}</>}{musique.resultat.album && <div className="page__sub">{musique.resultat.album}</div>}<a href={musique.resultat.lien} target="_blank" rel="noreferrer">MusicBrainz ↗</a></>
              : <span>{musique.resultat.phrase}</span>
          )}
          {musique.etat !== "ecoute" && musique.etat !== "analyse" && <button className="dash-close" onClick={musique.fermer} aria-label="Fermer">✕</button>}
        </div>
      )}
      <SceneStage scene={scene} onClose={() => { setScene(null); setView("home"); setMenuOpen(false); }} holdOpen={voice.isSpeaking}
        onSummarize={(sc) => {
          const text = (sc.slides || []).map((sl) => [sl.title, ...(sl.bullets || [])].join(" : ")).join(" | ").slice(0, 1200) || sc.title || "";
          lastInputWasVoiceRef.current = true; spokenRef.current = 0;
          sendMessage(`Résume en deux phrases ce qui est affiché à l'écran (${sc.title || sc.kind}) : ${text}`, undefined, { voice: true });
        }} />

      {menuOpen && <div className="mobile-backdrop" onClick={() => setMenuOpen(false)} />}

      <DashboardPanel open={dashboardOpen} onClose={() => setDashboardOpen(false)} />

      <CameraPanel
        open={cameraPanelOpen}
        onClose={() => setCameraPanelOpen(false)}
        onCapture={setPendingImage}
      />
    </div>
  );
}
