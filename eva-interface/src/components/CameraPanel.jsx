import { useEffect } from "react";
import { useCamera } from "../hooks/useCamera";

export default function CameraPanel({ open, onCapture, onClose }) {
  const { videoRef, active, error, start, stop, capture } = useCamera();

  useEffect(() => {
    if (open) start();
    else stop();
  }, [open, start, stop]);

  if (!open) return null;

  function handleCapture() {
    const shot = capture();
    if (shot) {
      onCapture(shot);
      onClose();
    }
  }

  return (
    <div className="dash-overlay" role="dialog" aria-label="Caméra">
      <div className="dash-panel camera-panel">
        <div className="dash-header">
          <span className="camera-panel__title">Montre quelque chose à EVA</span>
          <button className="dash-close" onClick={onClose} aria-label="Fermer">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="1.8" />
            </svg>
          </button>
        </div>
        <div className="camera-panel__body">
          {error ? (
            <p className="dash-empty">{error}</p>
          ) : (
            <video ref={videoRef} className="camera-panel__video" playsInline muted />
          )}
        </div>
        <div className="camera-panel__actions">
          <button className="camera-panel__shutter" onClick={handleCapture} disabled={!active} aria-label="Prendre la photo" />
        </div>
      </div>
    </div>
  );
}
