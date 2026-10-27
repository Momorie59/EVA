import { useEffect, useState } from "react";
import { CORE_URL, authHeaders } from "../urls";



export function useWidgetData(path, { intervalMs = 30000 } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchOnce() {
      try {
        const res = await fetch(`${CORE_URL}${path}`, { headers: authHeaders() });
        const json = await res.json();
        if (cancelled) return;
        if (json.error) {
          setError(json.error);
        } else {
          setData(json);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    }

    fetchOnce();
    const id = setInterval(fetchOnce, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [path, intervalMs]);

  return { data, error };
}
