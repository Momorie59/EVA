"""Agendas iCal : abonnement par personne, événements récurrents, journée entière, cloisonnement."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from integration_pg import requiert_pg

pytestmark = requiert_pg


def _ics():
    tz = ZoneInfo("Europe/Paris")
    d = datetime.now(tz) + timedelta(days=1)
    j = d.strftime("%Y%m%d")
    j2 = (d + timedelta(days=1)).strftime("%Y%m%d")
    return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//FR
BEGIN:VEVENT
UID:1
DTSTART;TZID=Europe/Paris:{j}T180000
DTEND;TZID=Europe/Paris:{j}T193000
RRULE:FREQ=WEEKLY;COUNT=4
SUMMARY:Entraînement de foot d'Léa
LOCATION:Stade municipal
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART;VALUE=DATE:{j2}
DTEND;VALUE=DATE:{(d + timedelta(days=2)).strftime('%Y%m%d')}
SUMMARY:Journée pédagogique
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").encode()


def test_agendas(eva, monkeypatch):
    from app import agendas
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]

    async def faux(url):
        if "pas-ics" in url:
            return b"<html>non</html>"
        return _ics()
    monkeypatch.setattr(agendas, "_http_get", faux)
    A, B = H(t["alice"]), H(t["bob"])
    assert c.post("/api/agendas", json={"nom": "X", "url": "ftp://x"}, headers=A).status_code == 400
    assert "iCal" in c.post("/api/agendas", json={"nom": "X", "url": "https://pas-ics.fr/a"}, headers=A).json()["detail"]
    r = c.post("/api/agendas", json={"nom": "Famille", "url": "webcal://exemple.fr/famille.ics"}, headers=A).json()
    assert r["agendas"] == [{"nom": "Famille", "url": "https://exemple.fr/famille.ics"}]
    assert c.get("/api/agendas", headers=B).json()["agendas"] == []                 # chacun les siens
    av = c.get("/api/agendas/a-venir?jours=30", headers=A).json()["evenements"]
    foot = [e for e in av if e["titre"].startswith("Entraînement")]
    assert len(foot) == 4 and foot[0]["lieu"] == "Stade municipal" and "T18:00:00+0" in foot[0]["debut"]
    jp = next(e for e in av if e["titre"] == "Journée pédagogique")
    assert jp["journee"] is True
    from app import profiles
    tok = profiles.user_var.set("alice")
    try:
        r = c.portal.call(lambda: m.registry.get("agenda_ics").execute(jours=3))
    finally:
        profiles.user_var.reset(tok)
    assert any(e["titre"] == "Journée pédagogique" for e in r["evenements"]) and len([e for e in r["evenements"] if "foot" in e["titre"]]) == 1
