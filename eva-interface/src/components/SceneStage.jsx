import { useEffect, useRef, useState } from "react";
import WeatherCard from "./WeatherCard";

const TTL_MS = 90000;
const SHORT_TTL_MS = 8000; // météo / heure : disparaissent vite (la souris dessus les retient)
const SHORT_KINDS = new Set(["weather", "clock"]); // retour automatique au menu initial après 90 s sans interaction

function Clock({ scene }) {
  const [now, setNow] = useState(() => new Date(scene.iso));
  const t0 = useRef(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date(new Date(scene.iso).getTime() + Date.now() - t0.current)), 1000);
    return () => clearInterval(id);
  }, [scene.iso]);
  const hhmm = now.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", timeZone: scene.tz });
  const ss = now.toLocaleTimeString("fr-FR", { second: "2-digit", timeZone: scene.tz });
  return (
    <div className="stage-clock" data-testid="clock-scene">
      <div className="stage-clock__time">{hhmm}<small>:{ss}</small></div>
      <div className="stage-clock__date">{scene.date}</div>
    </div>
  );
}

function Gauge({ label, pct, detail }) {
  const tone = pct >= 90 ? "is-bad" : pct >= 75 ? "is-warn" : "";
  return (
    <div className={`gauge ${tone}`}>
      <div className="gauge__top"><span>{label}</span><b>{Math.round(pct)}%</b></div>
      <div className="gauge__bar"><i style={{ width: `${Math.min(100, pct)}%` }} /></div>
      {detail && <small>{detail}</small>}
    </div>
  );
}

function Stats({ data }) {
  return (
    <div className="stage-stats" data-testid="stats-scene">
      <Gauge label="Processeur" pct={data.cpu_percent ?? 0} />
      <Gauge label="Mémoire" pct={data.memory?.percent ?? 0} detail={`${data.memory?.used_gb} / ${data.memory?.total_gb} Go`} />
      <Gauge label="Disque" pct={data.disk?.percent ?? 0} detail={`${data.disk?.used_gb} / ${data.disk?.total_gb} Go`} />
    </div>
  );
}

function Slide({ s }) {
  return (
    <div className="slide">
      {s.emoji && <div className="slide__emoji">{s.emoji}</div>}
      {s.title && <h2 className="slide__title">{s.title}</h2>}
      {s.image && <img className="slide__img" src={s.image} alt={s.title || "Image générée"} data-testid="slide-image" />}
      {s.subtitle && <p className="slide__sub">{s.subtitle}</p>}
      {s.stat && <div className="slide__stat"><b>{s.stat.value}</b><span>{s.stat.label}</span></div>}
      {s.bullets?.length > 0 && <ul className="slide__bullets">{s.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>}
      {s.table && (
        <div className="md-tablewrap">
          <table className="md-table">
            <thead><tr>{s.table.headers.map((h, i) => <th key={i}>{h}</th>)}</tr></thead>
            <tbody>{s.table.rows.map((r, a) => <tr key={a}>{r.map((c, b) => <td key={b}>{c}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
      {s.note && <p className="slide__note">{/^https?:\/\//.test(s.note) ? <a href={s.note} target="_blank" rel="noreferrer noopener">{s.note.replace(/^https?:\/\/(www\.)?/, "").slice(0, 60)}</a> : s.note}</p>}
    </div>
  );
}

// Écran de présentation en direct. Se ferme tout seul (retour au menu initial), ou sur « EVA, efface ».
export default function SceneStage({ scene, onClose, holdOpen, onSummarize }) {
  const [zoom, setZoom] = useState(1);
  const [idx, setIdx] = useState(0);
  const [pinned, setPinned] = useState(false);
  const ttl = scene && SHORT_KINDS.has(scene.kind) ? SHORT_TTL_MS : TTL_MS;
  const [left, setLeft] = useState(ttl);
  const last = useRef(Date.now());
  const hover = useRef(false);
  const slides = scene?.kind === "slides" ? scene.slides : [];
  const bump = () => { last.current = Date.now(); setLeft(ttl); };

  useEffect(() => { setIdx(0); setPinned(false); setZoom(1); bump(); }, [scene?.id]);
  useEffect(() => {
    if (!scene) return undefined;
    const id = setInterval(() => {
      if (pinned || holdOpen || hover.current) { last.current = Date.now(); setLeft(ttl); return; }
      const rest = ttl - (Date.now() - last.current);
      setLeft(Math.max(0, rest));
      if (rest <= 0) onClose();
    }, 500);
    return () => clearInterval(id);
  }, [scene, pinned, holdOpen, onClose, ttl]);
  useEffect(() => {
    if (!scene) return undefined;
    const key = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") { setIdx((i) => Math.min(slides.length - 1, i + 1)); bump(); }
      if (e.key === "ArrowLeft") { setIdx((i) => Math.max(0, i - 1)); bump(); }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [scene, slides.length, onClose]);

  useEffect(() => {
    if (!scene) return undefined;
    const onGesture = (e) => {
      const g = e.detail;
      if (g === "next") { setIdx((i) => Math.min(slides.length - 1, i + 1)); bump(); }
      else if (g === "prev") { setIdx((i) => Math.max(0, i - 1)); bump(); }
      else if (g === "pin") { setPinned((v) => !v); bump(); }
      else if (g === "clear") onClose();
      else if (g === "summarize") { onSummarize?.(scene); bump(); }
    };
    const onHand = (e) => { if (e.detail.zoom && e.detail.zoom !== 1) { setZoom((z) => Math.min(1.8, Math.max(0.6, z * e.detail.zoom))); bump(); } };
    window.addEventListener("eva-hand", onHand);
    window.addEventListener("eva-gesture", onGesture);
    return () => { window.removeEventListener("eva-gesture", onGesture); window.removeEventListener("eva-hand", onHand); };
  }, [scene, slides.length, onClose, onSummarize]);

  if (!scene) return null;
  const title = scene.kind === "weather" ? "Météo" : scene.kind === "clock" ? "Heure" : scene.kind === "stats" ? "Système" : scene.title;
  return (
    <div className="stage" role="dialog" aria-label={title} data-testid="stage" onPointerDown={bump}
      onWheel={(e) => { setZoom((z) => Math.min(1.8, Math.max(0.6, +(z * (e.deltaY < 0 ? 1.1 : 1 / 1.1)).toFixed(2)))); bump(); }}>
      <div className="stage__panel" onMouseEnter={() => { hover.current = true; }} onMouseLeave={() => { hover.current = false; bump(); }} style={zoom !== 1 ? { transform: `scale(${zoom})`, transformOrigin: "center" } : undefined} data-zoom={zoom.toFixed(2)}>
        <header className="stage__head">
          <span className="stage__title">{title}</span>
          <span className="stage__tools">
            <button type="button" onClick={() => setZoom((z) => Math.max(0.6, +(z / 1.2).toFixed(2)))} title="Réduire" aria-label="Réduire">−</button>
            <button type="button" onClick={() => setZoom(1)} title="Taille normale" aria-label="Taille normale">{Math.round(zoom * 100)} %</button>
            <button type="button" onClick={() => setZoom((z) => Math.min(1.8, +(z * 1.2).toFixed(2)))} title="Agrandir" aria-label="Agrandir">+</button>
            <button type="button" className={pinned ? "is-on" : ""} onClick={() => setPinned((v) => !v)} title="Garder à l'écran">{pinned ? "📌 Épinglé" : "📌"}</button>
            <button type="button" onClick={onClose} aria-label="Fermer" title="Fermer (Échap)">✕</button>
          </span>
        </header>
        <div className="stage__body">
          {scene.kind === "weather" && <WeatherCard data={scene.data} big />}
          {scene.kind === "clock" && <Clock scene={scene} />}
          {scene.kind === "stats" && <Stats data={scene.data} />}
          {scene.kind === "slides" && slides[idx] && <Slide key={idx} s={slides[idx]} />}
        </div>
        {scene.kind === "slides" && slides.length > 1 && (
          <footer className="stage__nav">
            <button type="button" disabled={idx === 0} onClick={() => { setIdx(idx - 1); bump(); }}>←</button>
            <span className="stage__dots">{slides.map((_, i) => <i key={i} className={i === idx ? "is-on" : ""} onClick={() => { setIdx(i); bump(); }} />)}</span>
            <span className="stage__count">{idx + 1} / {slides.length}</span>
            <button type="button" disabled={idx === slides.length - 1} onClick={() => { setIdx(idx + 1); bump(); }}>→</button>
          </footer>
        )}
        {!pinned && <div className="stage__ttl"><span style={{ width: `${(left / ttl) * 100}%` }} /></div>}
      </div>
    </div>
  );
}
