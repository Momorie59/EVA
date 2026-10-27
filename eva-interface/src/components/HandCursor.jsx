import { useEffect, useRef, useState } from "react";

// Curseur qui suit ta main (pouce + index) quand les gestes sont actifs ; se remplit quand tu pinces.
export default function HandCursor() {
  const [hands, setHands] = useState([]);
  const timer = useRef(null);
  useEffect(() => {
    const on = (e) => {
      setHands(e.detail.hands);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setHands([]), 500);
    };
    window.addEventListener("eva-hand", on);
    return () => { window.removeEventListener("eva-hand", on); clearTimeout(timer.current); };
  }, []);
  return hands.map((h, i) => (
    <div key={i} className={`hand-cursor ${h.pinch ? "is-pinch" : ""}`} data-testid="hand-cursor"
      style={{ left: `${h.x * 100}%`, top: `${h.y * 100}%` }} />
  ));
}
