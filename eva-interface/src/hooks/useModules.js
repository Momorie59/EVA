import { useEffect, useState } from "react";
import { api } from "../api";

// Modules facultatifs allumés par l'administrateur (wiki, recettes) : le menu n'affiche que ceux qui sont actifs.
export function useModules() {
  const [m, setM] = useState({});
  useEffect(() => {
    const charger = () => api("/api/modules").then((d) => setM(Object.fromEntries((d.modules || []).map((x) => [x.id, x.actif])))).catch(() => {});
    charger();
    window.addEventListener("eva:modules-changed", charger);
    return () => window.removeEventListener("eva:modules-changed", charger);
  }, []);
  return m;
}
