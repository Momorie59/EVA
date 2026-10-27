import { useEffect, useState } from "react";

// Confirmation DANS la page (plus de fenêtre « OK / Annuler » du navigateur) : await confirmer("Supprimer… ?") → true / false.
let ouvrir = null;
const enAttente = [];

export function confirmer(message, { ok = "Confirmer", annuler = "Annuler", seul = false } = {}) {
  return new Promise((resolve) => {
    const d = { message: String(message || ""), ok, annuler, seul, resolve };
    if (ouvrir) ouvrir(d); else enAttente.push(d);
  });
}

// Information simple (remplace alert) : un seul bouton.
export function avertir(message) {
  return confirmer(message, { ok: "OK", seul: true });
}

export function ConfirmHost() {
  const [file, setFile] = useState([]);
  useEffect(() => {
    ouvrir = (d) => setFile((f) => [...f, d]);
    if (enAttente.length) setFile((f) => [...f, ...enAttente.splice(0)]);
    return () => { ouvrir = null; };
  }, []);
  const d = file[0];
  useEffect(() => {
    if (!d) return undefined;
    const touche = (e) => {
      if (e.key === "Escape") repondre(false);
      if (e.key === "Enter") repondre(true);
    };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  });
  if (!d) return null;
  function repondre(v) {
    d.resolve(d.seul ? true : v);
    setFile((f) => f.slice(1));
  }
  return (
    <div className="confirmer" role="alertdialog" aria-modal="true" aria-label="Confirmation" data-testid="confirmer" onClick={() => repondre(false)}>
      <div className="confirmer__boite" onClick={(e) => e.stopPropagation()}>
        <p className="confirmer__texte">{d.message}</p>
        <div className="confirmer__boutons">
          {!d.seul && <button type="button" className="btn btn--ghost" onClick={() => repondre(false)} data-testid="confirmer-non">{d.annuler}</button>}
          <button type="button" className="btn btn--primary" autoFocus onClick={() => repondre(true)} data-testid="confirmer-oui">{d.ok}</button>
        </div>
      </div>
    </div>
  );
}
