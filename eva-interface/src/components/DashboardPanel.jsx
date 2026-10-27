import { useEffect, useState } from "react";
import { CORE_URL, authHeaders } from "../urls";



const DOC_LABELS = {
  "README.md": "README",
  "OBJECTIFS.md": "Objectifs",
  "DECISIONS.md": "Décisions",
  "CHANGELOG.md": "Changelog",
  "TODO.md": "À faire",
};

function ProjectDetail({ slug, onBack }) {
  const [project, setProject] = useState(null);
  const [activeDoc, setActiveDoc] = useState("README.md");

  useEffect(() => {
    fetch(`${CORE_URL}/api/dashboard/projects/${encodeURIComponent(slug)}`, {
      headers: authHeaders(),
    })
      .then((r) => r.json())
      .then((data) => {
        setProject(data);
        const firstAvailable = Object.keys(DOC_LABELS).find((f) => data.docs?.[f]);
        if (firstAvailable) setActiveDoc(firstAvailable);
      })
      .catch(() => setProject({ docs: {} }));
  }, [slug]);

  if (!project) return <p className="dash-loading">Chargement…</p>;

  return (
    <div className="dash-project">
      <button className="dash-back" onClick={onBack}>
        ← Tous les projets
      </button>
      <h3 className="dash-project__title">{slug}</h3>
      <div className="dash-doc-tabs">
        {Object.entries(DOC_LABELS).map(([file, label]) => (
          <button
            key={file}
            className={`dash-doc-tab ${activeDoc === file ? "is-active" : ""} ${
              !project.docs?.[file] ? "is-empty" : ""
            }`}
            onClick={() => setActiveDoc(file)}
          >
            {label}
          </button>
        ))}
      </div>
      <pre className="dash-doc-content">
        {project.docs?.[activeDoc] || "(ce fichier n'existe pas encore pour ce projet)"}
      </pre>
    </div>
  );
}

export function ProjectsTab() {
  const [projects, setProjects] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    fetch(`${CORE_URL}/api/dashboard/projects`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setProjects(data.projects || []))
      .catch(() => setProjects([]));
  }, []);

  if (selected) return <ProjectDetail slug={selected} onBack={() => setSelected(null)} />;

  if (projects === null) return <p className="dash-loading">Chargement…</p>;
  if (projects.length === 0) {
    return <p className="dash-empty">Aucun projet dans le workspace pour l'instant.</p>;
  }

  return (
    <div className="dash-project-list">
      {projects.map((p) => (
        <button key={p.slug} className="dash-project-card" onClick={() => setSelected(p.slug)}>
          <span className="dash-project-card__slug">{p.slug}</span>
          {p.description && <span className="dash-project-card__desc">{p.description}</span>}
        </button>
      ))}
    </div>
  );
}

export function MemoryTab() {
  const [messages, setMessages] = useState(null);

  useEffect(() => {
    fetch(`${CORE_URL}/api/dashboard/memory`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setMessages(data.messages || []))
      .catch(() => setMessages([]));
  }, []);

  if (messages === null) return <p className="dash-loading">Chargement…</p>;
  if (messages.length === 0) {
    return <p className="dash-empty">Rien en mémoire pour l'instant.</p>;
  }

  return (
    <div className="dash-memory-list">
      {messages.map((m, i) => (
        <div key={i} className={`dash-memory-item dash-memory-item--${m.role}`}>
          <span className="dash-memory-item__role">{m.role === "user" ? "Toi" : "EVA"}</span>
          <span className="dash-memory-item__text">{m.content}</span>
        </div>
      ))}
    </div>
  );
}

export default function DashboardPanel({ open, onClose }) {
  const [tab, setTab] = useState("projects");

  if (!open) return null;

  return (
    <div className="dash-overlay" role="dialog" aria-label="Tableau de bord EVA">
      <div className="dash-panel">
        <div className="dash-header">
          <div className="dash-tabs">
            <button
              className={`dash-tab ${tab === "projects" ? "is-active" : ""}`}
              onClick={() => setTab("projects")}
            >
              Projets
            </button>
            <button
              className={`dash-tab ${tab === "memory" ? "is-active" : ""}`}
              onClick={() => setTab("memory")}
            >
              Mémoire
            </button>
          </div>
          <button className="dash-close" onClick={onClose} aria-label="Fermer">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="1.8" />
            </svg>
          </button>
        </div>
        <div className="dash-body">{tab === "projects" ? <ProjectsTab /> : <MemoryTab />}</div>
      </div>
    </div>
  );
}
