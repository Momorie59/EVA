import { useWidgetData } from "../../hooks/useWidgetData";

export default function DockerWidget() {
  const { data, error } = useWidgetData("/api/widgets/docker", { intervalMs: 20000 });

  if (error && !data) return null;      // Docker non joignable : la carte disparaît plutôt qu'un « — »
  return (
    <div className="widget">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="widget__icon">
        <path
          d="M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7Z"
          stroke="currentColor"
          strokeWidth="1.4"
        />
      </svg>
      <div className="widget__body">
        <span className="widget__value">
          {data ? `${data.running}/${data.total}` : error ? "—" : "…"}
        </span>
        <span className="widget__label">{error ? "Docker indisponible" : "conteneurs actifs"}</span>
      </div>
    </div>
  );
}
