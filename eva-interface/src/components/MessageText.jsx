import { useState } from "react";
import { api } from "../api";

const FENCE = /```([\w+-]*)\n([\s\S]*?)```/g;
const RUNNABLE = new Set(["", "python", "py", "python3"]);

function CodeBlock({ lang, code }) {
  const [out, setOut] = useState(null);
  const [busy, setBusy] = useState(false);
  const runnable = RUNNABLE.has(lang.toLowerCase());

  async function run() {
    setBusy(true); setOut(null);
    try { setOut(await api("/api/sandbox/run", { method: "POST", body: JSON.stringify({ code }) })); }
    catch (e) { setOut({ error: e.message }); }
    finally { setBusy(false); }
  }

  return (
    <div className="codeblock">
      <div className="codeblock__bar">
        <span>{lang || "code"}</span>
        <span className="codeblock__actions">
          <button type="button" onClick={() => navigator.clipboard?.writeText(code)}>Copier</button>
          {runnable && <button type="button" disabled={busy} onClick={run}>{busy ? "Exécution…" : "▶ Exécuter dans le bac à sable"}</button>}
        </span>
      </div>
      <pre><code>{code}</code></pre>
      {out && (
        <pre className={`codeblock__out ${out.error || out.exit_code ? "is-error" : ""}`}>
          {out.error ? `⚠ ${out.error}` : out.output || "(aucune sortie)"}
          {out.exit_code ? `\n[code de sortie ${out.exit_code}]` : ""}
        </pre>
      )}
    </div>
  );
}

// Liens sûrs seulement (http/https) : un lien « javascript: » dans une réponse ne doit jamais devenir cliquable.
const sur = (u) => /^https?:\/\//i.test(u);
// Images et vidéos : fichiers d'EVA (/api/public/medias/…) ou adresses https.
const media = (u) => /^\/api\/public\/medias\/[0-9a-f]{32}\.[a-z0-9]{2,5}$/.test(u) || /^https:\/\//i.test(u);
const estVideo = (u) => /\.(mp4|webm|mov|m4v)$/i.test(u);
// Lien vers une page du wiki : [[Titre]] → la page Wiki l'ouvre (évènement « eva:wiki-ouvrir »).
const ouvrirWiki = (titre) => (e) => { e.preventDefault(); window.dispatchEvent(new CustomEvent("eva:wiki-ouvrir", { detail: { titre } })); };

function inline(t) {
  const out = [];
  const re = /(!\[[^\]\n]*\]\([^)\s]+\)|\[\[[^\]\n]{1,120}\]\]|\*\*[^*]+\*\*|`[^`]+`|\[[^\]\n]+\]\((?:https?:\/\/)[^)\s]+\)|https?:\/\/[^\s<>()]+[^\s<>().,;:!?»"']|(?<![\w*])\*[^*\n]+\*(?![\w*])|(?<![\w_])_[^_\n]+_(?![\w_]))/g;
  let last = 0, k = 0;
  for (const m of t.matchAll(re)) {
    if (m.index > last) out.push(t.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("![")) {
      const im = tok.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
      if (im && media(im[2])) {
        out.push(estVideo(im[2])
          ? <video key={k++} className="md-media" src={im[2]} controls preload="metadata" />
          : <img key={k++} className="md-media" src={im[2]} alt={im[1]} loading="lazy" />);
      } else out.push(tok);
    } else if (tok.startsWith("[[")) {
      const titre = tok.slice(2, -2).trim();
      out.push(<a key={k++} href="#" className="wikilink" onClick={ouvrirWiki(titre)}>{titre}</a>);
    } else if (tok.startsWith("**")) out.push(<strong key={k++}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) out.push(<code key={k++}>{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("[")) {
      const lm = tok.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      out.push(lm && sur(lm[2]) ? <a key={k++} href={lm[2]} target="_blank" rel="noopener noreferrer">{lm[1]}</a> : tok);
    } else if (/^https?:/i.test(tok)) out.push(<a key={k++} href={tok} target="_blank" rel="noopener noreferrer">{tok.replace(/^https?:\/\/(www\.)?/i, "")}</a>);
    else out.push(<em key={k++}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < t.length) out.push(t.slice(last));
  return out;
}

const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
const isSep = (l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);

// Mini-rendu Markdown : titres, listes, tableaux, gras, code en ligne.
function Markdown({ text, tag: Tag }) {
  const lines = text.replace(/^\n+|\n+$/g, "").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (!l.trim()) { i++; continue; }
    if (l.includes("|") && i + 1 < lines.length && isSep(lines[i + 1])) {
      const head = cells(l);
      const rows = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
      blocks.push(
        <div className="md-tablewrap" key={blocks.length}>
          <table className="md-table">
            <thead><tr>{head.map((h, j) => <th key={j}>{inline(h)}</th>)}</tr></thead>
            <tbody>{rows.map((r, a) => <tr key={a}>{r.map((c, b) => <td key={b}>{inline(c)}</td>)}</tr>)}</tbody>
          </table>
        </div>
      );
      continue;
    }
    if (/^\s*>\s?/.test(l)) {
      const q = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) q.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push(<blockquote className="md-quote" key={blocks.length}>{inline(q.join("\n"))}</blockquote>);
      continue;
    }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(l)) { blocks.push(<hr className="md-hr" key={blocks.length} />); i++; continue; }
    const h = l.match(/^(#{1,4})\s+(.*)$/);
    if (h) { blocks.push(<div className={`md-h md-h${h[1].length}`} key={blocks.length}>{inline(h[2])}</div>); i++; continue; }
    if (/^\s*([-*•]|\d+[.)])\s+/.test(l)) {
      const ordered = /^\s*\d/.test(l);
      const items = [];
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*([-*•]|\d+[.)])\s+/, ""));
      const L = ordered ? "ol" : "ul";
      blocks.push(<L className="md-list" key={blocks.length}>{items.map((t, j) => <li key={j}>{inline(t)}</li>)}</L>);
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4})\s/.test(lines[i]) && !/^\s*([-*•]|\d+[.)])\s+/.test(lines[i])
           && !(lines[i].includes("|") && i + 1 < lines.length && isSep(lines[i + 1]))) para.push(lines[i++]);
    blocks.push(<Tag key={blocks.length}>{inline(para.join("\n"))}</Tag>);
  }
  return <>{blocks}</>;
}

// Texte d'une réponse : les blocs ``` deviennent des blocs de code (exécutables si Python),
// le reste est rendu en Markdown léger (tableaux, listes, titres, gras).
export default function MessageText({ text, tag: Tag = "p" }) {
  const parts = [];
  let last = 0;
  for (const m of text.matchAll(FENCE)) {
    if (m.index > last) parts.push({ t: "text", v: text.slice(last, m.index) });
    parts.push({ t: "code", lang: m[1], v: m[2].replace(/\n$/, "") });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ t: "text", v: text.slice(last) });
  return (
    <>
      {parts.map((p, i) => p.t === "code"
        ? <CodeBlock key={i} lang={p.lang} code={p.v} />
        : p.v.trim() ? <Markdown key={i} text={p.v} tag={Tag} /> : null)}
    </>
  );
}
