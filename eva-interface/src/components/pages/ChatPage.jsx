import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import ChoixModele from "../ChoixModele";
import { libelle } from "../../models/catalogue";
import FilPanel from "../FilPanel";
import RateBar from "../RateBar";
import WeatherCard from "../WeatherCard";
import { StatsCard } from "../AiServerPanel";
import MessageText from "../MessageText";
import AttachChips from "../AttachChips";
import ChatImage from "../ChatImage";
import PlanCard from "../PlanCard";
import TachesFond from "../TachesFond";
import QuestionBubble from "../QuestionBubble";
import DownloadBubble from "../DownloadBubble";

const STATE = {
  idle: ["is-idle", "Prête"], thinking: ["is-thinking", "EVA réfléchit…"], acting: ["is-acting", "EVA utilise un outil…"], speaking: ["is-speaking", "EVA répond…"], error: ["is-error", "Problème"],
};
const SUGGESTIONS = ["Quel temps fait-il demain ?", "Cherche sur le web les dernières nouvelles de Linux", "Explique-moi comment fonctionne le Wi-Fi", "Ajoute du lait à la liste de courses"];

// Indicateur de réflexion : orbe animée, étape en cours, chronomètre, étapes déjà faites.
function Thinking({ evaState, activity }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(t); }, []);
  const secs = activity ? Math.max(0, Math.floor((now - activity.since) / 1000)) : 0;
  const label = activity?.tool ? `${activity.tool}…` : evaState === "acting" ? "EVA utilise un outil…" : "EVA réfléchit…";
  return (
    <div className="cp-think" role="status" aria-live="polite" data-testid="eva-thinking">
      <span className="cp-orb" aria-hidden="true" />
      <div className="cp-think__body">
        <span className="cp-think__label">{label}<span className="cp-dots" aria-hidden="true"><i /><i /><i /></span></span>
        {activity?.done?.length > 0 && <span className="cp-think__done">{activity.done.map((d, i) => <em key={i}>✓ {d}</em>)}</span>}
        {secs >= 15 && <span className="cp-think__hint">Un modèle local peut prendre un moment (surtout au premier message) : EVA travaille toujours.</span>}
      </div>
      <span className="cp-think__time" data-testid="eva-thinking-time">{secs} s</span>
    </div>
  );
}

// Copier une réponse d'EVA (texte brut, Markdown compris).
function CopyBtn({ text }) {
  const [ok, setOk] = useState(false);
  const copier = async () => {
    try { await navigator.clipboard.writeText(text); } catch {
      const t = document.createElement("textarea"); t.value = text; document.body.appendChild(t); t.select();
      try { document.execCommand("copy"); } catch { /* ignoré */ } t.remove();
    }
    setOk(true); setTimeout(() => setOk(false), 1500);
  };
  return <button type="button" className="cp-copy" onClick={copier} title="Copier la réponse" aria-label="Copier la réponse">{ok ? "✓ Copié" : "⧉ Copier"}</button>;
}

export default function ChatPage({ evaState = "idle", activity = null, messages, onSend, onStop, onConfirm, onQuestion, pendingImage, onRemoveImage, onPickImage, onOpenCamera, sessionId, lastModel, onRate, pendingFiles = [], uploading, attachError, onAttach, onRemoveFile }) {
  const [draft, setDraft] = useState("");
  const [installed, setInstalled] = useState([]);
  useEffect(() => {
    api("/api/models").then((d) => setInstalled((d.installed || []).filter((m) => !m.embedding))).catch(() => {});
  }, []);
  const listRef = useRef(null);
  const fileRef = useRef(null);

  // Fichier choisi (photo, PDF, Word, Excel, ZIP, texte…) : les photos vont au modèle vision, le reste est déposé dans le workspace.
  function pickFile(e) {
    const files = e.target.files;
    if (files?.length) onAttach?.(files);
    e.target.value = "";
  }

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, evaState, activity?.tool]);

  function submit(e) {
    e.preventDefault();
    if (!draft.trim() && !pendingImage && !pendingFiles.length) return;
    onSend(draft.trim(), pendingImage?.base64);
    setDraft("");
  }

  return (
    <section className="page page--chat">
      <header className="page__header">
        <h1>Conversation</h1>
        <span className={`cp-pill ${(STATE[evaState] || STATE.idle)[0]}`} data-testid="eva-state"><i />{(STATE[evaState] || STATE.idle)[1]}</span>
        <span className="page__sub">
          {lastModel ? `Dernière réponse : ${libelle(lastModel.model, installed)} — ${lastModel.reason}` : "Les outils utilisés par EVA apparaissent dans le fil"}
        </span>
        <ChoixModele sessionId={sessionId} lastModel={lastModel} />
        <TachesFond />
        {sessionId && <FilPanel sessionId={sessionId} />}
      </header>

      <div className="chatpage__scroll" ref={listRef}>
        <div className="chatpage__col">
          {messages.length <= 1 && messages.every((m) => m.from === "eva") && (
            <div className="cp-welcome" data-testid="chat-welcome">
              <span className="cp-orb cp-orb--big" aria-hidden="true" />
              <h2>Comment puis-je t'aider ?</h2>
              <p className="page__sub">Pose une question : EVA cherche sur le web, lit tes documents, pilote la maison, crée des images…</p>
              <div className="cp-chips">{SUGGESTIONS.map((q) => <button key={q} type="button" onClick={() => onSend(q)}>{q}</button>)}</div>
            </div>
          )}
          {messages.map((m) => {
            if (m.from === "user") return <div key={m.id} className="cp-user">{m.text}</div>;
            if (m.from === "system")
              return (
                <div key={m.id} className="cp-trace">
                  <span className="cp-trace__dot" />{m.text}
                </div>
              );
            if (m.from === "image") return <ChatImage key={m.id} m={m} />;
            if (m.from === "card") return m.kind === "stats" ? <StatsCard key={m.id} /> : <WeatherCard key={m.id} data={m.data} />;
            if (m.from === "download") return <DownloadBubble key={m.id} m={m} />;
            if (m.from === "plan") return <PlanCard key={m.id} plan={m.plan} />;
            if (m.from === "question") return <QuestionBubble key={m.id} m={m} onAnswer={onQuestion} />;
            if (m.from === "confirm")
              return (
                <div key={m.id} className="cp-confirm">
                  <span>{m.text}</span>
                  {!m.resolved ? (
                    <div className="cp-confirm__actions">
                      <button onClick={() => onConfirm(m.id, true)}>Autoriser cette fois</button>
                      {!m.critique && <button onClick={() => onConfirm(m.id, true, true)} title="EVA ne te redemandera plus pour cet outil (retirable dans Paramètres › Sécurité)" data-testid="confirm-always">Toujours autoriser</button>}
                      <button className="is-deny" onClick={() => onConfirm(m.id, false)}>Refuser</button>
                    </div>
                  ) : (
                    <em>{m.approved ? (m.always ? "Autorisé en permanence" : "Autorisé") : "Refusé"}</em>
                  )}
                </div>
              );
            return (
              <div key={m.id} className="cp-eva">
                <span className="cp-eva__who"><span className="cp-orb cp-orb--small" aria-hidden="true" />EVA</span>
                <div className="cp-eva__bubble"><MessageText text={m.text} /></div>
                <div className="cp-eva__tools">
                  {onRate && m.dbId && <RateBar m={m} onRate={onRate} />}
                  {m.text && <CopyBtn text={m.text} />}
                </div>
              </div>
            );
          })}
          {(evaState === "thinking" || evaState === "acting") && <Thinking evaState={evaState} activity={activity} />}
        </div>
      </div>

      <input ref={fileRef} type="file" multiple hidden onChange={pickFile} data-testid="photo-input" />
      <form className="chatpage__input" onSubmit={submit}>
        {pendingImage && (
          <div className="chatpage__image">
            <img src={pendingImage.previewUrl} alt="Photo à envoyer" />
            <button type="button" onClick={onRemoveImage} aria-label="Retirer la photo">×</button>
          </div>
        )}
        <AttachChips files={pendingFiles} uploading={uploading} error={attachError} onRemove={onRemoveFile} />
        <button type="button" className="chatpage__attach" onClick={() => fileRef.current?.click()} aria-label="Joindre un fichier" title="Joindre un fichier ou une photo (PDF, Word, Excel, ZIP, texte, image…)" data-testid="attach-btn">📎</button>
        <button type="button" className="chatpage__attach" onClick={onOpenCamera} aria-label="Prendre une photo" title="Prendre une photo">📷</button>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Message pour EVA…"
          aria-label="Message pour EVA"
          autoFocus
        />
        {onStop && ["thinking", "acting", "speaking"].includes(evaState)
          ? <button type="button" className="cp-send cp-stop" onClick={onStop} aria-label="Arrêter" title="Arrêter la réponse" data-testid="stop-btn"><span>Arrêter</span><b aria-hidden="true">■</b></button>
          : <button type="submit" className="cp-send" aria-label="Envoyer"><span>Envoyer</span><b aria-hidden="true">➤</b></button>}
      </form>
    </section>
  );
}
