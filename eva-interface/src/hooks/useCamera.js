import { useCallback, useEffect, useRef, useState } from "react";

const MAX_WIDTH = 1024; // limite la taille envoyée par WebSocket (et au modèle vision)
const JPEG_QUALITY = 0.8;

export function useCamera() {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [active, setActive] = useState(false);
  const [error, setError] = useState(null);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setActive(false);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setActive(true);
      return true;
    } catch (err) {
      setError("Caméra inaccessible : " + err.message);
      return false;
    }
  }, []);

  /** Capture l'image courante. Retourne { base64, previewUrl } ou null. */
  const capture = useCallback(() => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return null;

    const scale = Math.min(1, MAX_WIDTH / video.videoWidth);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);

    const dataUrl = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
    // Ollama attend le base64 brut, sans le préfixe "data:image/jpeg;base64,"
    return { base64: dataUrl.split(",")[1], previewUrl: dataUrl };
  }, []);

  useEffect(() => stop, [stop]);

  return { videoRef, active, error, start, stop, capture };
}
