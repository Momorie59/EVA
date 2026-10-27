import { CORE_URL, authHeaders } from "./urls";

// Dépose un fichier (corps brut) dans le workspace d'EVA ; renvoie sa description (chemin, type, aperçu).
export async function uploadFile(file) {
  const res = await fetch(`${CORE_URL}/api/uploads?name=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });
  let data = null;
  try { data = await res.json(); } catch { /* corps vide */ }
  if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : `Dépôt impossible (erreur ${res.status})`);
  return data;
}

// Photo réduite à 1024 px (comme la caméra) pour le modèle vision.
export function imageToPending(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const sc = Math.min(1, 1024 / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * sc); c.height = Math.round(img.height * sc);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      const dataUrl = c.toDataURL("image/jpeg", 0.85);
      URL.revokeObjectURL(url);
      resolve({ base64: dataUrl.split(",")[1], previewUrl: dataUrl });
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Image illisible.")); };
    img.src = url;
  });
}
