import { CORE_URL, authHeaders } from "./urls";

// Appel JSON vers EVA CORE. Lève une Error avec le message du serveur (champ "detail").
export async function api(path, options = {}) {
  const res = await fetch(`${CORE_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(options.headers || {}) },
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* réponse vide ou non JSON */
  }
  if (!res.ok) {
    if (res.status === 401) window.dispatchEvent(new Event("eva:unauthorized"));
    const d = data?.detail;
    const err = new Error(typeof d === "string" ? d : typeof d?.message === "string" ? d.message : `Erreur ${res.status}`);
    err.status = res.status; err.data = typeof d === "object" ? d : null;      // ex. conflit d'édition : la version de l'autre personne
    throw err;
  }
  return data;
}
