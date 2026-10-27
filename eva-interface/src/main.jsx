import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import AuthGate from './components/AuthGate.jsx'
import { ConfirmHost } from './confirmer.jsx'

// Tout appel d'API refusé (401) prévient l'AuthGate, qui revérifie la session et affiche la connexion si besoin.
const rawFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const res = await rawFetch(...args);
  try {
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
    if (res.status === 401 && url.includes('/api/') && !url.includes('/api/auth/')) window.dispatchEvent(new Event('eva:unauthorized'));
  } catch { /* ignoré */ }
  return res;
};

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthGate>
      <App />
    </AuthGate>
    <ConfirmHost />
  </StrictMode>,
)

// Application installable + ouverture même hors ligne (enveloppe de l'interface en cache).
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => {}); });
}
