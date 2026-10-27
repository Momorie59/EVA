import { useWidgetData } from "../../hooks/useWidgetData";

export default function SystemWidget() {
  const { data, error } = useWidgetData("/api/widgets/system", { intervalMs: 15000 });

  const cpu = data?.cpu_percent;
  const mem = data?.memory?.percent;

  return (
    <div className="widget widget--data">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="widget__icon">
        <rect x="3" y="4" width="18" height="12" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
        <path d="M8 20h8M12 16v4" stroke="currentColor" strokeWidth="1.4" />
      </svg>
      <div className="widget__body">
        <span className="widget__value widget__value--mono">
          {cpu != null ? `CPU ${Math.round(cpu)}%` : error ? "—" : "…"}
        </span>
        <span className="widget__label widget__label--mono">
          {mem != null ? `RAM ${Math.round(mem)}%` : error ? "indisponible" : "chargement…"}
        </span>
      </div>
      <div className="widget__bars" aria-hidden="true">
        <i style={{ width: `${Math.min(100, cpu ?? 0)}%` }} />
        <i style={{ width: `${Math.min(100, mem ?? 0)}%` }} />
      </div>
    </div>
  );
}
