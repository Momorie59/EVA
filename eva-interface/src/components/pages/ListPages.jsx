import { useState } from "react";
import { MemoryTab } from "../DashboardPanel";
import MemoryGraph from "../MemoryGraph";
import SouvenirsPanel from "../SouvenirsPanel";

export function MemoryPage() {
  const [mode, setMode] = useState("souvenirs");
  return (
    <section className="page">
      <header className="page__header">
        <h1>Mémoire</h1>
        <span className="page__sub">{mode === "souvenirs" ? "Ce qu'EVA retient de toi" : "Derniers échanges conservés par EVA"}</span>
        <select className="page__action" data-testid="memory-mode" value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="souvenirs">Ce qu'EVA retient de moi</option><option value="list">Échanges</option><option value="graph">Carte</option>
        </select>
      </header>
      <div className="page__body">{mode === "souvenirs" ? <SouvenirsPanel /> : mode === "graph" ? <MemoryGraph /> : <MemoryTab />}</div>
    </section>
  );
}
