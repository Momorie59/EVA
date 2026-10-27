import { useState, useRef, useEffect } from "react";
import RateBar from "./RateBar";
import WeatherCard from "./WeatherCard";
import { StatsCard } from "./AiServerPanel";
import MessageText from "./MessageText";
import AttachChips from "./AttachChips";
import ChatImage from "./ChatImage";
import PlanCard from "./PlanCard";
import QuestionBubble from "./QuestionBubble";
import DownloadBubble from "./DownloadBubble";
import ChoixModele from "./ChoixModele";

// Suggestions selon le moment de la journée, tant que la conversation n'a pas commencé.
function suggestions() {
  const h = new Date().getHours();
  if (h >= 5 && h < 11) return ["Quel temps fait-il aujourd'hui ?", "Quoi de neuf dans l'actualité ?", "Qu'est-ce qu'il y a sur la liste de courses ?"];
  if (h >= 11 && h < 18) return ["Une idée de recette pour ce soir ?", "Qu'est-ce qu'il y a sur la liste de courses ?", "Résume-moi l'actualité du jour"];
  return ["Quel temps fera-t-il demain ?", "Lis-moi la liste des tâches", "Une idée de film pour ce soir ?"];
}

export default function ChatDrawer({ messages, onSend, onStop, evaState = "idle", onConfirm, onQuestion, pendingImage, onRemoveImage, onRate, pendingFiles = [], uploading, attachError, onAttach, onRemoveFile, sessionId, lastModel }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const listRef = useRef(null);
  const fileRef = useRef(null);
  const lastMessage = [...messages].reverse().find((m) => m.from === "eva" || m.from === "user");

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [open, messages]);

  // Ouvre le tiroir tout seul quand une photo vient d'être prise, pour
  // que la miniature soit visible sans action supplémentaire.
  useEffect(() => {
    if (pendingImage) setOpen(true);
  }, [pendingImage]);

  function handleSubmit(e) {
    e.preventDefault();
    if (!draft.trim() && !pendingImage && !pendingFiles.length) return;
    onSend(draft.trim(), pendingImage?.base64);
    setDraft("");
  }

  return (
    <div className={`chat-drawer ${open ? "is-open" : ""}`}>
      <button
        className="chat-drawer__handle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="chat-drawer__grip" />
        {!open && lastMessage && (
          <span className="chat-drawer__preview">
            <strong>{lastMessage.from === "eva" ? "EVA" : "Toi"}</strong>
            {lastMessage.text}
          </span>
        )}
      </button>

      <div className="chat-drawer__body">
        {sessionId && <div className="chat-drawer__modele" data-testid="drawer-modele"><span>IA :</span><ChoixModele sessionId={sessionId} lastModel={lastModel} /></div>}
        <div className="chat-drawer__messages" ref={listRef}>
          {messages.every((m) => m.from === "eva") && messages.length <= 1 && (
            <div className="drawer-chips" data-testid="drawer-chips">
              {suggestions().map((q) => <button key={q} type="button" onClick={() => onSend(q)}>{q}</button>)}
            </div>
          )}
          {messages.map((m) => {
            if (m.from === "system") {
              return (
                <div key={m.id} className="bubble bubble--system">
                  {m.text}
                </div>
              );
            }

            if (m.from === "image") return <ChatImage key={m.id} m={m} />;
            if (m.from === "card") return m.kind === "stats" ? <StatsCard key={m.id} /> : <WeatherCard key={m.id} data={m.data} />;
            if (m.from === "download") return <DownloadBubble key={m.id} m={m} />;
            if (m.from === "plan") return <PlanCard key={m.id} plan={m.plan} />;
            if (m.from === "question") return <QuestionBubble key={m.id} m={m} onAnswer={onQuestion} />;
            if (m.from === "confirm") {
              return (
                <div key={m.id} className="bubble bubble--confirm">
                  <span>{m.text}</span>
                  {!m.resolved ? (
                    <div className="bubble__actions">
                      <button onClick={() => onConfirm(m.id, true)}>Autoriser cette fois</button>
                      {!m.critique && <button onClick={() => onConfirm(m.id, true, true)} title="EVA ne te redemandera plus pour cet outil (retirable dans Paramètres › Sécurité)" data-testid="confirm-always">Toujours autoriser</button>}
                      <button onClick={() => onConfirm(m.id, false)}>Refuser</button>
                    </div>
                  ) : (
                    <span className="bubble__resolved">
                      {m.approved ? (m.always ? "Autorisé en permanence" : "Autorisé") : "Refusé"}
                    </span>
                  )}
                </div>
              );
            }

            return (
              <div key={m.id} className={`bubble bubble--${m.from}`}>
                {m.from === "eva" ? <MessageText text={m.text} /> : m.text}
                {m.from === "eva" && m.dbId && <RateBar m={m} onRate={onRate} />}
              </div>
            );
          })}
        </div>

        {pendingImage && (
          <div className="pending-image">
            <img className="pending-image__thumb" src={pendingImage.previewUrl} alt="Photo à envoyer" />
            <span className="pending-image__label">Photo prête à être envoyée</span>
            <button className="pending-image__remove" onClick={onRemoveImage} aria-label="Retirer la photo">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" />
              </svg>
            </button>
          </div>
        )}

        <AttachChips files={pendingFiles} uploading={uploading} error={attachError} onRemove={onRemoveFile} />
        <input ref={fileRef} type="file" multiple hidden onChange={(e) => { if (e.target.files?.length) onAttach?.(e.target.files); e.target.value = ""; }} data-testid="drawer-file-input" />
        <form className="chat-drawer__input" onSubmit={handleSubmit}>
          <button type="button" className="chat-drawer__attach" onClick={() => fileRef.current?.click()} aria-label="Joindre un fichier" title="Joindre un fichier ou une photo" data-testid="drawer-attach">📎</button>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={pendingImage ? "Une question sur la photo ? (optionnel)" : "Écris à EVA…"}
            aria-label="Message pour EVA"
          />
          {onStop && ["thinking", "acting", "speaking"].includes(evaState) ? (
            <button type="button" onClick={onStop} aria-label="Arrêter" title="Arrêter la réponse" data-testid="drawer-stop">
              <svg width="16" height="16" viewBox="0 0 24 24"><rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor" /></svg>
            </button>
          ) : (
            <button type="submit" aria-label="Envoyer">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M4 12h15M13 5l7 7-7 7" stroke="currentColor" strokeWidth="1.8" />
              </svg>
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
