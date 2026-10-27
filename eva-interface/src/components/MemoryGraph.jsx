import { useEffect, useRef, useState } from "react";
import { api } from "../api";

// Carte de ce qu'EVA sait : documents et conversations reliés par proximité de sens. Simulation de forces simple, sur canvas.
// À la main (gestes actifs) : pince un point pour le déplacer, pince brièvement pour l'ouvrir, écarte deux mains ouvertes pour zoomer.
export default function MemoryGraph() {
  const ref = useRef(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [hover, setHover] = useState(null);
  const [open, setOpen] = useState(null);
  const sim = useRef({ nodes: [], hover: null, drag: null, scale: 1 });

  useEffect(() => { api("/api/memory/graph").then(setData).catch((e) => setError(e.message)); }, []);

  async function openNode(n) {
    setOpen({ label: n.label, chunks: null });
    try { const r = await api(`/api/memory/node?source=${encodeURIComponent(n.id)}`); setOpen({ label: n.label, chunks: r.chunks }); }
    catch (e) { setOpen({ label: n.label, chunks: [e.message] }); }
  }

  useEffect(() => {
    if (!data || !data.nodes.length) return undefined;
    const cv = ref.current; if (!cv) return undefined;
    const ctx = cv.getContext("2d");
    const k = window.devicePixelRatio || 1;
    const W = cv.width = cv.clientWidth * k, H = cv.height = 460 * k;
    const nodes = data.nodes.map((n, i) => ({ ...n, x: W / 2 + Math.cos(i) * 120 * k, y: H / 2 + Math.sin(i * 1.7) * 120 * k, vx: 0, vy: 0 }));
    sim.current = { nodes, hover: null, drag: null, scale: 1 };
    const S = sim.current;
    cv.__nodes = nodes;                      // pour les tests de bout en bout
    let raf, steps = 0;

    const toWorld = (px, py) => ({ x: (px - W / 2) / S.scale + W / 2, y: (py - H / 2) / S.scale + H / 2 });
    const fromClient = (cx, cy) => { const r = cv.getBoundingClientRect(); return toWorld((cx - r.left) * (W / r.width), (cy - r.top) * (H / r.height)); };
    const nodeAt = (w) => nodes.find((n) => Math.hypot(n.x - w.x, n.y - w.y) < 16 * k) || null;

    const tick = () => {
      if (steps++ < 260) {
        for (const a of nodes) {
          if (a === S.drag) continue;
          for (const b of nodes) {
            if (a === b) continue;
            const dx = a.x - b.x, dy = a.y - b.y, d2 = Math.max(400, dx * dx + dy * dy);
            const f = (9000 * k * k) / d2;
            a.vx += (dx / Math.sqrt(d2)) * f * 0.02; a.vy += (dy / Math.sqrt(d2)) * f * 0.02;
          }
          a.vx += (W / 2 - a.x) * 0.0009; a.vy += (H / 2 - a.y) * 0.0009;
        }
        for (const e of data.edges) {
          const a = nodes[e.a], b = nodes[e.b];
          const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1, f = (d - 90 * k) * 0.004;
          if (a !== S.drag) { a.vx += (dx / d) * f; a.vy += (dy / d) * f; }
          if (b !== S.drag) { b.vx -= (dx / d) * f; b.vy -= (dy / d) * f; }
        }
        for (const n of nodes) { if (n === S.drag) continue; n.vx *= 0.82; n.vy *= 0.82; n.x = Math.min(W - 12, Math.max(12, n.x + n.vx)); n.y = Math.min(H - 12, Math.max(12, n.y + n.vy)); }
      }
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.setTransform(S.scale, 0, 0, S.scale, (W / 2) * (1 - S.scale), (H / 2) * (1 - S.scale));
      ctx.lineWidth = k;
      for (const e of data.edges) {
        ctx.strokeStyle = `rgba(110,210,255,${0.15 + (e.w - 0.5) * 0.9})`;
        ctx.beginPath(); ctx.moveTo(nodes[e.a].x, nodes[e.a].y); ctx.lineTo(nodes[e.b].x, nodes[e.b].y); ctx.stroke();
      }
      for (const n of nodes) {
        const r = (4 + Math.min(8, Math.sqrt(n.chunks))) * k;
        ctx.fillStyle = n.kind === "message" ? "#ffcf66" : "#6fd8ff";
        ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 6.3); ctx.fill();
        if (n === S.hover || n === S.drag) { ctx.fillStyle = "#fff"; ctx.font = `${13 * k}px sans-serif`; ctx.fillText(n.label, n.x + r + 4 * k, n.y + 4 * k); }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const hit = (w) => { const h = nodeAt(w); if (h !== S.hover) { S.hover = h; setHover(h ? h.label : null); } return h; };
    const move = (ev) => hit(fromClient(ev.clientX, ev.clientY));
    const click = (ev) => { const h = nodeAt(fromClient(ev.clientX, ev.clientY)); if (h) openNode(h); };
    const wheel = (ev) => { ev.preventDefault(); S.scale = Math.min(3, Math.max(0.5, S.scale * (ev.deltaY < 0 ? 1.1 : 1 / 1.1))); };
    cv.addEventListener("wheel", wheel, { passive: false });
    cv.__zoom = (f) => { S.scale = f === 0 ? 1 : Math.min(3, Math.max(0.5, S.scale * f)); };
    cv.addEventListener("pointermove", move);
    cv.addEventListener("click", click);

    // Gestes : le curseur de la main fait office de souris
    const onHand = (e) => {
      const { hands, events, zoom } = e.detail;
      if (zoom && zoom !== 1) S.scale = Math.min(3, Math.max(0.5, S.scale * zoom));
      const h0 = hands[0];
      if (!h0) return;
      const w = fromClient(h0.x * window.innerWidth, h0.y * window.innerHeight);
      // Les événements d'abord : au relâchement, le point pouce-index saute et ne doit pas entraîner le nœud.
      for (const ev of events) {
        if (ev.hand !== 0) continue;
        if (ev.type === "pinchstart") S.drag = nodeAt(fromClient(ev.x * window.innerWidth, ev.y * window.innerHeight));
        if (ev.type === "pinchend") S.drag = null;
        if (ev.type === "tap") { const t = nodeAt(fromClient(ev.x * window.innerWidth, ev.y * window.innerHeight)); if (t) openNode(t); }
      }
      if (S.drag && h0.pinch) { S.drag.x = w.x; S.drag.y = w.y; S.drag.vx = S.drag.vy = 0; }
      else if (!S.drag) hit(w);
    };
    window.addEventListener("eva-hand", onHand);
    return () => { cancelAnimationFrame(raf); cv.removeEventListener("pointermove", move); cv.removeEventListener("click", click); cv.removeEventListener("wheel", wheel); window.removeEventListener("eva-hand", onHand); };
  }, [data]);

  if (error) return <p className="page__warn">{error}</p>;
  if (!data) return <p className="dash-loading">Chargement…</p>;
  if (!data.nodes.length) return <p className="dash-empty">Rien à cartographier : indexe des documents (page Sources) ou discute avec EVA.</p>;
  return (
    <div data-testid="memory-graph">
      <canvas ref={ref} style={{ width: "100%", height: 460, background: "rgba(5,15,25,.6)", borderRadius: 10, touchAction: "none" }} aria-label="Carte de la mémoire d'EVA" />
      <div className="agentform__actions">
        <button className="btn" onClick={() => ref.current?.__zoom(1 / 1.25)} aria-label="Réduire la carte">−</button>
        <button className="btn" onClick={() => ref.current?.__zoom(0)} aria-label="Taille normale">100 %</button>
        <button className="btn" onClick={() => ref.current?.__zoom(1.25)} aria-label="Agrandir la carte">+</button>
      </div>
      <p className="page__sub">{data.nodes.length} éléments · {data.edges.length} liens · <span style={{ color: "#6fd8ff" }}>●</span> documents <span style={{ color: "#ffcf66" }}>●</span> conversations{hover ? ` · ${hover}` : " · survole ou clique un point ; avec les gestes : pince pour déplacer, pince brève pour ouvrir, deux mains ouvertes pour zoomer"}</p>
      {open && (
        <div className="card" data-testid="node-preview">
          <span className="card__label">{open.label}</span>
          {open.chunks ? open.chunks.map((c, i) => <p key={i} className="page__sub">{c}</p>) : <p className="dash-loading">Chargement…</p>}
          <div className="agentform__actions"><button className="btn" onClick={() => setOpen(null)}>Fermer</button></div>
        </div>
      )}
    </div>
  );
}
