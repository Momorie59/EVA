import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

// Post-it : liste côté serveur, rafraîchie sur signal d'EVA (WebSocket) et toutes les 30 s.
export function useNotes() {
  const [notes, setNotes] = useState([]);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const r = await api("/api/notes");
      if (alive.current) setNotes(r.notes || []);
    } catch { /* serveur injoignable : on garde l'affichage actuel */ }
  }, []);

  useEffect(() => {
    alive.current = true;
    refresh();
    const id = setInterval(refresh, 30000);
    window.addEventListener("eva-notes-changed", refresh);
    return () => { alive.current = false; clearInterval(id); window.removeEventListener("eva-notes-changed", refresh); };
  }, [refresh]);

  const add = useCallback(async (text, color = "jaune") => {
    const n = await api("/api/notes", { method: "POST", body: JSON.stringify({ text, color }) });
    setNotes((prev) => [...prev, n]);
    return n;
  }, []);
  // Mise à jour optimiste (déplacement fluide), le serveur confirme ensuite.
  const patch = useCallback(async (id, fields) => {
    setNotes((prev) => prev.map((n) => (n.id === id ? { ...n, ...fields, ...(fields.done === true ? { done_at: new Date().toISOString() } : fields.done === false ? { done_at: null } : {}) } : n)));
    try { await api(`/api/notes/${id}`, { method: "PUT", body: JSON.stringify(fields) }); } catch { refresh(); }
  }, [refresh]);
  const remove = useCallback(async (id) => {
    setNotes((prev) => prev.filter((n) => n.id !== id));
    try { await api(`/api/notes/${id}`, { method: "DELETE" }); } catch { refresh(); }
  }, [refresh]);
  const clear = useCallback(async (doneOnly) => {
    await api(`/api/notes${doneOnly ? "?done_only=true" : ""}`, { method: "DELETE" });
    refresh();
  }, [refresh]);

  return { notes, add, patch, remove, clear, refresh };
}
