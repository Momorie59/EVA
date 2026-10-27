"""Clients HTTP : Paperless-ngx, Ollama, ntfy."""
import json
import logging

import httpx

log = logging.getLogger("majordome.clients")


class PaperlessClient:
    def __init__(self, url: str, token: str, public_url: str, timeout: int = 60):
        self.url = url
        self.public_url = public_url
        self.http = httpx.Client(base_url=url, timeout=timeout,
                                 headers={"Authorization": f"Token {token}", "Accept": "application/json"})
        self._tags: dict[str, int] = {}

    def ping(self) -> bool:
        r = self.http.get("/api/documents/", params={"page_size": 1})
        r.raise_for_status()
        return True

    def tous_les_ids(self) -> list[int]:
        """Identifiants de tous les documents. On parcourt les pages : le champ « all » de Paperless
        n'existe plus à partir de la version 10 de son API, il ne faut donc pas compter dessus."""
        ids: list[int] = []
        params = {"page_size": 1000, "ordering": "id", "fields": "id", "page": 1}
        while True:
            r = self.http.get("/api/documents/", params=params)
            r.raise_for_status()
            j = r.json()
            ids += [d["id"] for d in j.get("results", []) if "id" in d]
            if not j.get("next"):
                break
            params["page"] += 1
        return sorted(set(ids))

    def document(self, doc_id: int) -> dict:
        r = self.http.get(f"/api/documents/{doc_id}/")
        r.raise_for_status()
        return r.json()

    def recherche(self, texte: str, limite: int = 5) -> list[dict]:
        r = self.http.get("/api/documents/", params={"query": texte, "page_size": limite})
        r.raise_for_status()
        return r.json().get("results", [])

    def deposer(self, nom: str, donnees: bytes, titre: str | None = None) -> str:
        """Envoie un fichier à Paperless (OCR puis archivage). Renvoie l'identifiant de la tâche d'import."""
        data = {"title": titre} if titre else {}
        r = self.http.post("/api/documents/post_document/", files={"document": (nom, donnees)}, data=data, timeout=120)
        r.raise_for_status()
        tache = r.json()
        return tache if isinstance(tache, str) else str(tache)

    def _tag_id(self, nom: str) -> int:
        if nom in self._tags:
            return self._tags[nom]
        r = self.http.get("/api/tags/", params={"name__iexact": nom})
        r.raise_for_status()
        res = r.json().get("results", [])
        if res:
            tid = res[0]["id"]
        else:
            r = self.http.post("/api/tags/", json={"name": nom, "matching_algorithm": 0})
            r.raise_for_status()
            tid = r.json()["id"]
        self._tags[nom] = tid
        return tid

    def _bulk(self, doc_id: int, methode: str, tag: str):
        r = self.http.post("/api/documents/bulk_edit/", json={
            "documents": [doc_id], "method": methode, "parameters": {"tag": self._tag_id(tag)}})
        r.raise_for_status()

    def ajouter_tag(self, doc_id: int, tag: str):
        self._bulk(doc_id, "add_tag", tag)

    def retirer_tag(self, doc_id: int, tag: str):
        self._bulk(doc_id, "remove_tag", tag)

    def lien(self, doc_id: int) -> str:
        return f"{self.public_url}/documents/{doc_id}/details"


class OllamaClient:
    def __init__(self, url: str, model: str, num_ctx: int = 8192, timeout: int = 600):
        self.model = model
        self.num_ctx = num_ctx
        self.http = httpx.Client(base_url=url, timeout=timeout)

    def modeles(self) -> list[str]:
        r = self.http.get("/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    def _chat(self, system: str, user: str, fmt=None) -> str:
        body = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0, "num_ctx": self.num_ctx},
        }
        if fmt is not None:
            body["format"] = fmt
        r = self.http.post("/api/chat", json=body)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def chat_json(self, system: str, user: str, schema: dict) -> dict:
        try:
            contenu = self._chat(system, user, schema)
        except httpx.HTTPStatusError as e:
            # Anciennes versions d'Ollama : pas de schéma JSON, on retombe sur le mode « json » simple.
            log.warning("Sortie structurée refusée (%s), repli sur format=json", e.response.status_code)
            contenu = self._chat(system, user + "\n\nRéponds uniquement avec le JSON demandé.", "json")
        return json.loads(contenu)

    def chat(self, system: str, user: str) -> str:
        return self._chat(system, user).strip()
