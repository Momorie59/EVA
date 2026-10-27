import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

// Liste des conversations (barre latérale) : création, renommage, suppression, recherche.
export function useSessions() {
  const [sessions, setSessions] = useState([]);
  const [results, setResults] = useState(null); // résultats de recherche, ou null

  const refresh = useCallback(async (essai = 0) => {
    try {
      const data = await api("/api/sessions");
      setSessions(data.sessions || []);
    } catch {
      // EVA CORE injoignable (souvent : il redémarre après une mise à jour) : on garde la liste actuelle et on réessaie,
      // sinon la liste restait vide jusqu'au rechargement de la page.
      const n = typeof essai === "number" ? essai : 0;           // appelé aussi par un événement
      if (n < 40) setTimeout(() => refresh(n + 1), 3000);
    }
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener("eva:sessions-changed", refresh);   // projet changé depuis l'en-tête de la conversation
    return () => window.removeEventListener("eva:sessions-changed", refresh);
  }, [refresh]);

  const create = useCallback(async () => {
    const created = await api("/api/sessions", { method: "POST", body: "{}" });
    await refresh();
    return created.id;
  }, [refresh]);

  const rename = useCallback(
    async (id, title) => {
      await api(`/api/sessions/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ title }) });
      await refresh();
    },
    [refresh]
  );

  const remove = useCallback(
    async (id) => {
      await api(`/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
      await refresh();
    },
    [refresh]
  );

  // Plusieurs d'un coup : { ids: [...] }, { tout: true } (toutes les miennes) ou { personne } (administrateur).
  const removeMany = useCallback(
    async (body) => {
      const r = await api("/api/sessions/supprimer", { method: "POST", body: JSON.stringify(body) });
      await refresh();
      return r.supprimees || 0;
    },
    [refresh]
  );

  const attach = useCallback(
    async (ids, project) => {
      await api("/api/sessions/rattacher", { method: "POST", body: JSON.stringify({ ids, project }) });
      await refresh();
    },
    [refresh]
  );

  const search = useCallback(async (q) => {
    if (!q.trim()) {
      setResults(null);
      return;
    }
    try {
      const data = await api(`/api/sessions/search?q=${encodeURIComponent(q)}`);
      setResults(data.results || []);
    } catch {
      setResults([]);
    }
  }, []);

  return { sessions, results, refresh, create, rename, remove, removeMany, attach, search };
}
