import { useEffect, useState } from "react";

export default function HudClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const time = now.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const date = now.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
  return (
    <div className="hud-clock">
      <span className="hud-clock__time">{time}</span>
      <span className="hud-clock__date">{date}</span>
    </div>
  );
}
