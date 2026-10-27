import { useWidgetData } from "../../hooks/useWidgetData";

export default function WeatherWidget() {
  const { data, error } = useWidgetData("/api/widgets/weather", { intervalMs: 10 * 60 * 1000 });

  const temp = data?.current?.temperature_c;
  if (error && !data) return null;      // pas de météo (Internet coupé…) : la carte disparaît plutôt qu'un « — »
  const condition = data?.current?.condition;

  return (
    <div className="widget">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="widget__icon">
        <path
          d="M7 17.5a4 4 0 0 1-.5-7.97A5.5 5.5 0 0 1 17.4 11 3.75 3.75 0 0 1 17 18.5H7Z"
          stroke="currentColor"
          strokeWidth="1.4"
        />
      </svg>
      <div className="widget__body">
        <span className="widget__value">{temp != null ? `${Math.round(temp)}°C` : error ? "—" : "…"}</span>
        <span className="widget__label">{condition || (error ? "indisponible" : "chargement…")}</span>
      </div>
    </div>
  );
}
