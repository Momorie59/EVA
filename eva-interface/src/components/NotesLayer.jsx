import { useEffect, useRef, useState } from "react";
import { api } from "../api";

const COLORS = ["jaune", "rose", "rouge", "orange", "vert", "bleu", "violet"];
export const NOTE_FILL = { jaune: "#ffe58a", rose: "#ffb8d1", rouge: "#ff9a8f", orange: "#ffc58a", vert: "#b9f0a8", bleu: "#a9d6ff", violet: "#d4b8ff" };

function Note({ note, onPatch, onRemove, bounds }) {
  const ref = useRef(null);
  const drag = useRef(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(note.text);
  const [pos, setPos] = useState(null); // position locale pendant le glisser
  const posRef = useRef(null);            // dernière position (lisible sans attendre le rendu)
  const [sharing, setSharing] = useState(false);
  const [people, setPeople] = useState([]);
  const shared = note.shared || [];
  const mine = note.mine !== false;
  async function openShare() {
    if (!sharing) { try { setPeople((await api("/api/notes/people")).users || []); } catch { setPeople([]); } }
    setSharing((v) => !v);
  }
  function toggle(name) {
    const base = shared.includes("*") ? [] : shared;
    onPatch(note.id, { shared: base.includes(name) ? base.filter((x) => x !== name) : [...base, name] });
  }

  useEffect(() => { if (!editing) setDraft(note.text); }, [note.text, editing]);

  function down(e) {
    if (e.button !== undefined && e.button !== 0) return;
    const box = bounds.current.getBoundingClientRect();
    const el = ref.current.getBoundingClientRect();
    drag.current = { dx: e.clientX - el.left, dy: e.clientY - el.top, box, w: el.width, h: el.height };
    e.currentTarget.setPointerCapture?.(e.pointerId);
    e.preventDefault();
  }
  function move(e) {
    const d = drag.current;
    if (!d) return;
    const x = Math.min(Math.max((e.clientX - d.dx - d.box.left) / d.box.width, 0), Math.max(0, 1 - d.w / d.box.width));
    const y = Math.min(Math.max((e.clientY - d.dy - d.box.top) / d.box.height, 0), Math.max(0, 1 - d.h / d.box.height));
    posRef.current = { x, y };
    setPos({ x, y });
  }
  function up() {
    if (drag.current && posRef.current) onPatch(note.id, { x: posRef.current.x, y: posRef.current.y });
    drag.current = null;
    posRef.current = null;
    setPos(null);
  }
  function commit() {
    setEditing(false);
    const t = draft.trim();
    if (t && t !== note.text) onPatch(note.id, { text: t });
    else setDraft(note.text);
  }

  const x = pos ? pos.x : note.x;
  const y = pos ? pos.y : note.y;
  return (
    <div
      ref={ref}
      className={`postit ${note.done ? "is-done" : ""} ${pos ? "is-drag" : ""} ${note.created_by === "eva" ? "is-eva" : ""}`}
      style={{ left: `${x * 100}%`, top: `${y * 100}%`, "--note": NOTE_FILL[note.color] || NOTE_FILL.jaune }}
      data-testid="postit"
      data-note-id={note.id}
      data-color={note.color}
    >
      <div className="postit__bar" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} data-testid="postit-grip" title="Glisser pour déplacer">
        <span className="postit__who">{!mine ? `De ${note.owner}` : note.created_by === "eva" ? "EVA" : "Moi"}</span>
        {mine && (
          <button type="button" className={`postit__btn ${shared.length ? "is-on" : ""}`} onPointerDown={(e) => e.stopPropagation()} onClick={openShare} aria-label="Partager ce post-it" aria-expanded={sharing} title={shared.length ? `Partagé avec ${shared.includes("*") ? "tout le monde" : shared.join(", ")}` : "Partager avec d'autres personnes"} data-testid="postit-share">👥</button>
        )}
        <button type="button" className="postit__btn" onPointerDown={(e) => e.stopPropagation()} onClick={() => onPatch(note.id, { done: true })} aria-label="Valider : ranger dans la corbeille" title="Valider (rangé dans la corbeille avec la date)" data-testid="postit-done">✓</button>
        {mine && <button type="button" className="postit__btn" onPointerDown={(e) => e.stopPropagation()} onClick={() => onRemove(note.id)} aria-label="Supprimer définitivement le post-it" title="Supprimer définitivement" data-testid="postit-del">×</button>}
      </div>
      {sharing && (
        <div className="postit__share" data-testid="postit-share-pop" onPointerDown={(e) => e.stopPropagation()}>
          <label><input type="checkbox" checked={shared.includes("*")} onChange={() => onPatch(note.id, { shared: shared.includes("*") ? [] : ["*"] })} /> Tout le monde</label>
          {people.length === 0 && <small>Aucune autre personne.</small>}
          {people.map((u) => (
            <label key={u}><input type="checkbox" checked={shared.includes("*") || shared.includes(u)} disabled={shared.includes("*")} onChange={() => toggle(u)} data-testid={`postit-share-${u}`} /> {u}</label>
          ))}
        </div>
      )}
      {editing ? (
        <textarea className="postit__edit" value={draft} autoFocus rows={3} maxLength={600} aria-label="Texte du post-it" data-testid="postit-edit"
          onChange={(e) => setDraft(e.target.value)} onBlur={commit}
          onKeyDown={(e) => { if (e.key === "Escape") { setDraft(note.text); setEditing(false); } if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commit(); } }} />
      ) : (
        <p className="postit__text" onClick={() => setEditing(true)} data-testid="postit-text" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setEditing(true)} title="Cliquer pour modifier">{note.text}</p>
      )}
      <div className="postit__colors" role="group" aria-label="Couleur">
        {COLORS.map((c) => (
          <button key={c} type="button" className={`postit__dot ${note.color === c ? "is-on" : ""}`} style={{ background: NOTE_FILL[c] }} onClick={() => onPatch(note.id, { color: c })} aria-label={`Couleur ${c}`} />
        ))}
      </div>
    </div>
  );
}

// Calque des post-it : au-dessus de toutes les pages, sans bloquer les clics autour.
export default function NotesLayer({ notes, visible, onPatch, onRemove }) {
  const bounds = useRef(null);
  return (
    <div ref={bounds} className="notes-layer" data-testid="notes-layer" hidden={!visible}>
      {notes.map((n) => <Note key={n.id} note={n} onPatch={onPatch} onRemove={onRemove} bounds={bounds} />)}
    </div>
  );
}

// Bouton « + Post-it » avec petit formulaire, pour en coller un à la main.
function fmtDate(iso) {
  try { return new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); } catch { return ""; }
}

export function NoteAdder({ onAdd, count, visible, onToggleVisible, trash = [], onRestore, onPurge, onEmptyTrash }) {
  const [open, setOpen] = useState(false);
  const [showTrash, setShowTrash] = useState(false);
  const [text, setText] = useState("");
  const [color, setColor] = useState("jaune");
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    if (!text.trim()) return;
    try { await onAdd(text.trim(), color); setText(""); setOpen(false); setError(""); } catch (err) { setError(err.message); }
  }
  return (
    <div className="note-adder">
      <button type="button" className="note-adder__btn" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-testid="note-add-open" title="Coller un post-it">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M5 4h14v11l-5 5H5z" /><path d="M14 20v-5h5" /></svg>
        <span>Post-it{count ? ` · ${count}` : ""}</span>
      </button>
      {open && (
        <form className="note-adder__pop" onSubmit={submit} data-testid="note-form">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={600} placeholder="Ex. Appeler le plombier demain" aria-label="Texte du post-it" autoFocus data-testid="note-text" />
          <div className="note-adder__colors" role="group" aria-label="Couleur">
            {COLORS.map((c) => <button key={c} type="button" className={`postit__dot ${color === c ? "is-on" : ""}`} style={{ background: NOTE_FILL[c] }} onClick={() => setColor(c)} aria-label={`Couleur ${c}`} />)}
          </div>
          {error && <p className="te-error" role="alert">{error}</p>}
          <div className="note-adder__actions">
            <button type="submit" className="btn" data-testid="note-submit">Coller</button>
            <button type="button" className="btn btn--ghost" onClick={onToggleVisible} data-testid="note-toggle">{visible ? "Masquer tout" : "Afficher tout"}</button>
            <button type="button" className="btn btn--ghost" onClick={() => setShowTrash((v) => !v)} aria-expanded={showTrash} data-testid="note-trash-toggle">🗑 Corbeille ({trash.length})</button>
          </div>
          {showTrash && (
            <div className="note-trash" data-testid="note-trash">
              {trash.length === 0 && <p className="note-trash__empty">Aucun post-it traité.</p>}
              {[...trash].sort((a, b) => String(b.done_at || "").localeCompare(String(a.done_at || ""))).map((n) => (
                <div className="note-trash__row" key={n.id} data-testid="trash-row">
                  <span className="note-trash__dot" style={{ background: NOTE_FILL[n.color] }} />
                  <div className="note-trash__body"><span className="note-trash__text">{n.text}</span><small>Traité le {fmtDate(n.done_at || n.updated_at)} · par {n.created_by === "eva" ? "EVA" : "moi"}</small></div>
                  <button type="button" className="postit__btn" onClick={() => onRestore(n.id)} title="Remettre à l'écran" aria-label="Restaurer" data-testid="trash-restore">↩</button>
                  <button type="button" className="postit__btn" onClick={() => onPurge(n.id)} title="Supprimer définitivement" aria-label="Supprimer définitivement" data-testid="trash-purge">×</button>
                </div>
              ))}
              {trash.length > 0 && <button type="button" className="btn btn--ghost" onClick={onEmptyTrash} data-testid="trash-empty">Vider la corbeille</button>}
            </div>
          )}
        </form>
      )}
    </div>
  );
}
