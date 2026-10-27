import { useEffect } from "react";
import ThemeEditor from "./ThemeEditor";

// Panneau latéral : on règle le thème en voyant l'accueil changer en direct derrière.
export default function ThemeDrawer({ open, onClose }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <aside className="theme-drawer" role="dialog" aria-label="Personnaliser l'interface" data-testid="theme-drawer">
      <header className="theme-drawer__head">
        <strong>Personnaliser</strong>
        <button type="button" className="theme-drawer__close" onClick={onClose} aria-label="Fermer" data-testid="theme-close">×</button>
      </header>
      <div className="theme-drawer__body"><ThemeEditor /></div>
    </aside>
  );
}
