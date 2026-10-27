// Plan de travail d'EVA : étapes cochées au fur et à mesure.
const ICONES = { a_faire: "○", en_cours: "◐", fait: "✓", abandonne: "✕" };

export default function PlanCard({ plan }) {
  if (!plan?.etapes?.length) return null;
  const faites = plan.etapes.filter((e) => e.etat === "fait").length;
  return (
    <div className="plan-carte" data-testid="plan-carte">
      <div className="plan-carte__tete"><b>📋 {plan.titre || "Plan"}</b><span>{faites}/{plan.etapes.length}</span></div>
      <div className="plan-carte__barre"><i style={{ width: `${(faites / plan.etapes.length) * 100}%` }} /></div>
      <ol>
        {plan.etapes.map((e, i) => (
          <li key={i} className={`is-${e.etat}`}><span className="plan-carte__ico">{ICONES[e.etat] || "○"}</span>{e.titre}</li>
        ))}
      </ol>
    </div>
  );
}
