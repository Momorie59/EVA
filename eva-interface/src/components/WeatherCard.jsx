const ICONS = [
  [/orage/, "⛈️"], [/neige|grains/, "❄️"], [/verglaç/, "🌨️"], [/pluie|averse|bruine/, "🌧️"],
  [/brouillard/, "🌫️"], [/couvert/, "☁️"], [/partiellement|plutôt/, "⛅"], [/dégagé/, "☀️"],
];
export const iconFor = (c = "") => (ICONS.find(([re]) => re.test(c.toLowerCase())) || [0, "🌡️"])[1];
const DAYS = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."];
function dayLabel(iso, i) {
  if (i === 0) return "Aujourd'hui";
  if (i === 1) return "Demain";
  const d = new Date(iso + "T12:00:00");
  return `${DAYS[d.getDay()]} ${d.getDate()}`;
}

export default function WeatherCard({ data, big }) {
  if (!data || data.error) return null;
  const cur = data.current || {};
  const fc = data.forecast || [];
  return (
    <div className={`wcard ${big ? "wcard--big" : ""}`} data-testid={big ? "weather-big" : "weather-card"}>
      <div className="wcard__now">
        <div className="wcard__icon">{iconFor(cur.condition)}</div>
        <div>
          <div className="wcard__city">{data.city}{data.country ? `, ${data.country}` : ""}</div>
          <div className="wcard__temp">{cur.temperature_c != null ? `${Math.round(cur.temperature_c)}°` : "–"}</div>
          <div className="wcard__cond">{cur.condition}{cur.windspeed_kmh != null ? ` · vent ${Math.round(cur.windspeed_kmh)} km/h` : ""}</div>
        </div>
      </div>
      {fc.length > 0 && (
        <div className="wcard__days">
          {fc.map((d, i) => (
            <div className="wcard__day" key={d.date}>
              <span className="wcard__dn">{dayLabel(d.date, i)}</span>
              <span className="wcard__di" title={d.condition}>{iconFor(d.condition)}</span>
              <span className="wcard__dt"><b>{d.temp_max != null ? Math.round(d.temp_max) : "–"}°</b> <i>{d.temp_min != null ? Math.round(d.temp_min) : "–"}°</i></span>
              <span className="wcard__dp">💧 {d.precipitation_probability_max ?? "–"}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
