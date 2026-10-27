"""EVA serveur MCP : jetons, droits du compte, outils cochés, actions, journal."""
from integration_pg import requiert_pg

pytestmark = requiert_pg


def rpc(c, jeton, methode, params=None, mid=1):
    return c.post("/api/serveur-mcp", json={"jsonrpc": "2.0", "id": mid, "method": methode, **({"params": params} if params else {})},
                  headers={"Authorization": f"Bearer {jeton}"} if jeton else {})


def test_serveur_mcp(eva):
    c, H, t = eva["c"], eva["H"], eva["t"]
    A = H(t["alice"])
    assert c.get("/api/mcp/serveur", headers=H(t["bob"])).status_code == 403
    st = c.get("/api/mcp/serveur", headers=A).json()
    noms = {o["nom"]: o for o in st["outils"]}
    assert "weather_get" in noms and noms["obs_action"]["action"] and not noms["list_add"]["action"] and not any(n.startswith("mcp_") for n in noms)
    assert c.post("/api/mcp/serveur/jetons", json={"nom": "Claude", "compte": "bob", "outils": []}, headers=A).status_code == 400
    j = c.post("/api/mcp/serveur/jetons", json={"nom": "Claude portable", "compte": "bob",
                                                "outils": ["list_show", "list_add", "papiers_echeances", "inexistant"]}, headers=A).json()
    jeton = j["jeton"]
    assert jeton.startswith("evamcp_") and j["outils"] == ["list_add", "list_show", "papiers_echeances"]
    assert jeton not in c.get("/api/mcp/serveur", headers=A).text                       # montré une seule fois

    assert rpc(c, None, "initialize").status_code == 401
    assert rpc(c, "evamcp_faux", "tools/list").status_code == 401
    ini = rpc(c, jeton, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}).json()
    assert ini["result"]["protocolVersion"] == "2025-06-18" and "tools" in ini["result"]["capabilities"]
    assert c.post("/api/serveur-mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                  headers={"Authorization": f"Bearer {jeton}"}).status_code == 202
    outils = {o["name"]: o for o in rpc(c, jeton, "tools/list").json()["result"]["tools"]}
    assert set(outils) == {"list_show", "list_add"}                                     # papiers : interdit au compte de bob
    assert outils["list_show"]["annotations"]["readOnlyHint"] is True and "inputSchema" in outils["list_add"]

    r = rpc(c, jeton, "tools/call", {"name": "list_add", "arguments": {"list": "courses", "items": ["pain"]}}).json()["result"]
    assert r["isError"] is False, r
    r = rpc(c, jeton, "tools/call", {"name": "list_show", "arguments": {"list": "courses"}}).json()["result"]
    assert "pain" in r["content"][0]["text"]
    e = rpc(c, jeton, "tools/call", {"name": "papiers_echeances", "arguments": {}}).json()
    assert e["error"]["code"] == -32602
    assert rpc(c, jeton, "resources/list").json()["error"]["code"] == -32601
    lot = c.post("/api/serveur-mcp", json=[{"jsonrpc": "2.0", "id": 7, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/x"}],
                 headers={"Authorization": f"Bearer {jeton}"}).json()
    assert lot == [{"jsonrpc": "2.0", "id": 7, "result": {}}]

    journal = c.get("/api/auth/audit?q=MCP", headers=A)
    assert journal.status_code == 200 and "MCP list_add" in journal.text and "Claude portable" in journal.text
    lst = c.get("/api/mcp/serveur", headers=A).json()["jetons"]
    assert lst[0]["appels"] >= 2 and lst[0]["dernier"]
    c.put(f"/api/mcp/serveur/jetons/{j['id']}", json={"outils": ["list_show"]}, headers=A)
    assert [o["name"] for o in rpc(c, jeton, "tools/list").json()["result"]["tools"]] == ["list_show"]
    c.delete(f"/api/mcp/serveur/jetons/{j['id']}", headers=A)
    assert rpc(c, jeton, "tools/list").status_code == 401
