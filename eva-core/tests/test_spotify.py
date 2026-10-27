"""Spotify : liaison PKCE, lecture, commandes, playlist des morceaux reconnus (API simulée)."""
from urllib.parse import parse_qs, urlparse

from integration_pg import requiert_pg

pytestmark = requiert_pg


class Rep:
    def __init__(self, code=200, data=None):
        self.status_code, self._d = code, data
        self.content = b"" if data is None else b"x"

    def json(self):
        return self._d


def test_spotify(eva, monkeypatch):
    from app import spotify
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    A = H(t["alice"])
    jetons = []

    async def faux_jeton(d):
        jetons.append(d)
        return {"access_token": "acc", "refresh_token": "ref", "expires_in": 3600}
    appels = []
    playlist = {"items": []}

    async def faux_http(method, url, **kw):
        chemin = url.replace(spotify.API, "")
        appels.append((method, chemin, kw.get("params"), kw.get("json")))
        if chemin == "/me":
            return Rep(200, {"id": "amo", "display_name": "Paul", "product": "premium"})
        if chemin == "/search":
            q = kw["params"]["q"]
            if "daft" in q.lower():
                return Rep(200, {"artists": {"items": [{"name": "Daft Punk", "uri": "spotify:artist:dp"}]}, "tracks": {"items": [
                    {"name": "One More Time", "artists": [{"name": "Daft Punk"}], "album": {"name": "Discovery"}, "uri": "spotify:track:omt"}]}})
            return Rep(200, {"tracks": {"items": [{"name": "Bohemian Rhapsody", "artists": [{"name": "Queen"}], "album": {"name": "ANATO"},
                                                   "uri": "spotify:track:br"}]}})
        if chemin == "/me/player/devices":
            return Rep(200, {"devices": [{"id": "d1", "name": "Enceinte salon", "type": "Speaker", "is_active": True}]})
        if chemin.startswith("/users/amo/playlists"):
            return Rep(201, {"id": "pl1"})
        if chemin == "/playlists/pl1/tracks" and method == "GET":
            return Rep(200, playlist)
        if chemin == "/playlists/pl1/tracks":
            playlist["items"] += [{"track": {"uri": u}} for u in kw["json"]["uris"]]
            return Rep(201, {"snapshot_id": "s"})
        if chemin == "/me/player" and method == "GET":
            return Rep(200, {"is_playing": True, "device": {"name": "Enceinte salon", "volume_percent": 40},
                             "item": {"name": "One More Time", "artists": [{"name": "Daft Punk"}], "album": {"name": "Discovery"}}})
        return Rep(204)
    monkeypatch.setattr(spotify, "_jeton", faux_jeton)
    monkeypatch.setattr(spotify, "_http", faux_http)

    assert c.put("/api/spotify", json={"client_id": "pas-bon"}, headers=A).status_code == 400
    assert c.get("/api/spotify", headers=H(t["bob"])).status_code == 403
    c.put("/api/spotify", json={"client_id": "0123456789abcdef0123456789abcdef"}, headers=A)
    lien = c.post("/api/spotify/connecter", json={}, headers=A).json()["lien"]
    q = parse_qs(urlparse(lien).query)
    assert q["code_challenge_method"] == ["S256"] and q["redirect_uri"][0].endswith("/api/spotify/retour") and "user-modify-playback-state" in q["scope"][0]
    assert "expiré" in c.get("/api/spotify/retour?code=x&state=faux").text
    page = c.get(f"/api/spotify/retour?code=lecode&state={q['state'][0]}")
    assert "relié au compte « Paul »" in page.text
    assert jetons[0]["code_verifier"] and jetons[0]["code"] == "lecode" and "client_secret" not in jetons[0]
    assert c.get("/api/spotify", headers=A).json()["relie"] is True

    run = lambda nom, **kw: c.portal.call(lambda: m.registry.get(nom).execute(**kw))      # noqa: E731
    assert run("spotify_jouer", recherche="Daft Punk")["texte"] == "Je mets Daft Punk."
    assert appels[-1][:2] == ("PUT", "/me/player/play") and appels[-1][3] == {"context_uri": "spotify:artist:dp"}
    assert run("spotify_jouer", recherche="One more time daft", genre="morceau")["texte"] == "Je mets « One More Time » de Daft Punk."
    run("spotify_commande", action="volume", valeur="30", appareil="salon")
    assert appels[-1][2] == {"device_id": "d1", "volume_percent": 30}
    assert "Spotify" not in run("spotify_en_cours").get("error", "") and run("spotify_en_cours")["titre"] == "One More Time"

    r = c.portal.call(spotify.ajouter_reconnu, "Bohemian Rhapsody", "Queen")
    assert r["ajoute"] and playlist["items"] == [{"track": {"uri": "spotify:track:br"}}]
    assert c.portal.call(spotify.ajouter_reconnu, "Bohemian Rhapsody", "Queen")["deja"] is True
    c.put("/api/spotify", json={"playlist_auto": False}, headers=A)
    assert c.portal.call(spotify.ajouter_reconnu, "X", "Y") is None
