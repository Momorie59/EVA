const ICON = { pdf: "📕", word: "📘", excel: "📗", powerpoint: "📙", zip: "🗜", texte: "📄", image: "🖼", autre: "📎" };

// Fichiers prêts à être envoyés (au-dessus de la zone de saisie).
export default function AttachChips({ files, uploading, error, onRemove }) {
  if (!files?.length && !uploading && !error) return null;
  return (
    <div className="attach-chips" data-testid="attach-chips">
      {files.map((f) => (
        <span key={f.path} className="attach-chip" title={f.note || f.path} data-testid="attach-chip">
          {ICON[f.kind] || ICON.autre} {f.name}
          <button type="button" onClick={() => onRemove(f.path)} aria-label={`Retirer ${f.name}`}>×</button>
        </span>
      ))}
      {uploading && <span className="attach-chip is-busy">Dépôt en cours…</span>}
      {error && <span className="attach-chip is-error" role="alert">{error}</span>}
    </div>
  );
}
