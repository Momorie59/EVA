import { useState } from "react";

// Pouces 👍/👎 sous une réponse d'EVA, avec confirmation visible de l'enregistrement.
export default function RateBar({ m, onRate }) {
  const [asking, setAsking] = useState(false);
  const [comment, setComment] = useState("");
  if (!onRate) return null;

  const status = m.rateStatus === "saving" ? "Envoi…" : m.rateStatus === "saved" ? (m.rating ? "Avis enregistré, merci." : "Avis retiré.") : m.rateStatus === "error" ? `⚠ ${m.rateError || "Avis non enregistré."}` : "";

  return (
    <div className="cp-rate">
      <button className={m.rating === 1 ? "is-on" : ""} aria-label="Bonne réponse" title="Bonne réponse"
        onClick={() => { onRate(m.id, m.rating === 1 ? 0 : 1); setAsking(false); }}>👍</button>
      <button className={m.rating === -1 ? "is-on" : ""} aria-label="Mauvaise réponse" title="Mauvaise réponse"
        onClick={() => {
          if (m.rating === -1) { onRate(m.id, 0); setAsking(false); }
          else { onRate(m.id, -1); setAsking(true); setComment(""); }
        }}>👎</button>
      {status && <span className={`cp-rate__status ${m.rateStatus === "error" ? "is-error" : ""}`}>{status}</span>}
      {asking && m.rating === -1 && (
        <form className="cp-rate__form" onSubmit={(e) => { e.preventDefault(); onRate(m.id, -1, comment); setAsking(false); }}>
          <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Qu'est-ce qui n'allait pas ? (facultatif)" autoFocus />
          <button type="submit">Envoyer</button>
        </form>
      )}
    </div>
  );
}
