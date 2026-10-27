import { useState } from "react";

// Question à choix posée par EVA : un clic répond ; plusieurs choix → cocher puis « Valider ». On peut aussi écrire sa réponse.
export default function QuestionBubble({ m, onAnswer }) {
  const [coches, setCoches] = useState([]);
  if (m.resolved) {
    return (
      <div className="bubble bubble--question is-done" data-testid="question-bubble">
        <span className="question__texte">{m.question}</span>
        <span className="bubble__resolved">{m.reponses?.length ? `→ ${m.reponses.join(", ")}` : "Répondu par écrit"}</span>
      </div>
    );
  }
  return (
    <div className="bubble bubble--question" data-testid="question-bubble">
      <span className="question__texte">❓ {m.question}</span>
      <div className="question__choix">
        {m.choix.map((c) => (m.plusieurs ? (
          <label key={c} className={`question__puce ${coches.includes(c) ? "is-on" : ""}`}>
            <input type="checkbox" checked={coches.includes(c)} onChange={() => setCoches(coches.includes(c) ? coches.filter((x) => x !== c) : [...coches, c])} /> {c}
          </label>
        ) : (
          <button key={c} type="button" className="question__puce" onClick={() => onAnswer(m.id, [c])} data-testid="question-choix">{c}</button>
        )))}
      </div>
      {m.plusieurs && <button type="button" className="btn btn--primary" disabled={!coches.length} onClick={() => onAnswer(m.id, coches)}>Valider</button>}
      <span className="question__aide">…ou écris ta réponse dans la zone de message.</span>
    </div>
  );
}
