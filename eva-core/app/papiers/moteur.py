"""Cœur métier : traitement des documents, alertes, résumés, questions."""
import json
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .clients import PaperlessClient, OllamaClient
from .dates import parse_date, date_action, seuil_applicable, fr_date, fr_delai
from .db import DB, now_iso
from .extraction import SYSTEM, SCHEMA, construire_message, normaliser

log = logging.getLogger("majordome")

TAG_OK = "majordome-traité"
TAG_VALIDER = "majordome-à-valider"
TAG_ERREUR = "majordome-erreur"

NATURE_FR = {
    "paiement": "paiement", "renouvellement": "renouvellement", "resiliation_limite": "limite de résiliation",
    "fin_garantie": "fin de garantie", "declaration": "déclaration", "rendez_vous": "rendez-vous",
    "expiration": "expiration", "autre": "échéance",
}


_MOTS_VIDES = set("""le la les l un une des du de d et ou que qui quoi quel quelle quels quelles est sont ce cet cette ces
mon ma mes ton ta tes son sa ses notre nos votre vos leur leurs je tu il elle on nous vous ils elles me te se y en a au aux
pour par sur dans avec sans plus moins tout tous toute toutes quand comment combien pourquoi dit dis disent raconte racontent
parle parlent papier papiers document documents est-ce qu est-ce eva il elle peux peut faut fait faire mais donc car ne pas
il lo gli che di del della per con mi ti ci si sono è come quanto quando dove the of and is are what my""".split())


def requete_paperless(texte: str) -> str:
    """Mots-clés de la question pour la recherche plein texte de Paperless (« OU » : un seul mot suffit)."""
    import re as _re
    mots = [m for m in _re.findall(r"[\w-]{3,}", (texte or "").lower()) if m not in _MOTS_VIDES]
    vus = []
    for m in mots:
        if m not in vus:
            vus.append(m)
    return " OR ".join(vus[:6])


class Majordome:
    def __init__(self, settings, db: DB, paperless: PaperlessClient, ollama: OllamaClient):
        """settings : objet de configuration (papiers.config.Reglages) — model, seuils, fuseau."""
        self.s = settings
        self.db = db
        self.paperless = paperless
        self.ollama = ollama
        self.tz = ZoneInfo(settings.timezone)

    def aujourd_hui(self) -> date:
        return datetime.now(self.tz).date()

    # ------------------------------------------------------------------ ingestion
    def ids_a_traiter(self) -> list[int]:
        tous = self.paperless.tous_les_ids()
        connus = {r["paperless_id"]: r for r in self.db.q("SELECT paperless_id, statut, tentatives FROM documents")}
        res = []
        for i in tous:
            r = connus.get(i)
            if r is None or r["statut"] == "a_refaire" or (r["statut"] == "erreur" and r["tentatives"] < self.s.max_retries):
                res.append(i)
        return res

    def tout_reanalyser(self) -> int:
        """Après un changement de modèle : tous les papiers seront réanalysés, petit à petit, par la boucle.
        Les échéances saisies ou corrigées à la main sont gardées (le retraitement ne remplace que celles de l'IA)."""
        self.db.x("UPDATE documents SET statut='a_refaire', tentatives=0, erreur=NULL")
        return self.db.one("SELECT COUNT(*) n FROM documents WHERE statut='a_refaire'")["n"]

    def modele_pret(self) -> bool:
        """Le modèle d'extraction est-il disponible sur Ollama ? Sinon on attend, sans compter d'échec."""
        try:
            noms = self.ollama.modeles()
        except Exception as e:
            log.warning("Ollama injoignable (%s) : analyse des documents en attente", e.__class__.__name__)
            return False
        m = self.s.ollama_model
        if m in noms or f"{m}:latest" in noms:
            return True
        log.warning("Modèle %s absent d'Ollama : analyse des documents en attente", m)
        return False

    def sonder(self, limite: int = 20) -> int:
        """Traite les nouveaux documents Paperless. Renvoie le nombre traité."""
        if not self.modele_pret():
            return 0
        n = 0
        for doc_id in self.ids_a_traiter()[:limite]:
            self.traiter_document(doc_id)
            n += 1
        return n

    def traiter_document(self, doc_id: int, aujourd_hui: date | None = None) -> dict:
        aujourd_hui = aujourd_hui or self.aujourd_hui()
        doc = None
        try:
            doc = self.paperless.document(doc_id)
            brut = self.ollama.chat_json(SYSTEM, construire_message(doc, aujourd_hui, self.s.max_chars), SCHEMA)
            ex = normaliser(brut, aujourd_hui, self.s.confidence_threshold)
        except Exception as e:  # on enregistre l'erreur et on réessaiera
            log.exception("Échec du traitement du document %s", doc_id)
            prev = self.db.one("SELECT tentatives FROM documents WHERE paperless_id=?", (doc_id,))
            tentatives = (prev["tentatives"] if prev else 0) + 1
            self.db.x("""INSERT INTO documents(paperless_id, titre, statut, erreur, tentatives, traite_le)
                         VALUES(?,?,?,?,?,?) ON CONFLICT(paperless_id) DO UPDATE SET
                         statut='erreur', erreur=excluded.erreur, tentatives=excluded.tentatives,
                         traite_le=excluded.traite_le""",
                      (doc_id, (doc or {}).get("title"), "erreur", str(e)[:500], tentatives, now_iso()))
            if tentatives >= self.s.max_retries:
                self._tag(doc_id, TAG_ERREUR)
            return {"paperless_id": doc_id, "statut": "erreur", "erreur": str(e)}

        with self.db.lock:
            # Un retraitement remplace les échéances issues de l'IA, jamais celles saisies à la main.
            self.db.x("DELETE FROM alertes_envoyees WHERE echeance_id IN "
                      "(SELECT id FROM echeances WHERE paperless_id=? AND origine='ia')", (doc_id,))
            self.db.x("DELETE FROM echeances WHERE paperless_id=? AND origine='ia'", (doc_id,))
            self.db.x("""INSERT INTO documents(paperless_id, titre, type_document, emetteur, pays, resume, montant,
                         devise, confiance, statut, erreur, tentatives, brut, traite_le)
                         VALUES(?,?,?,?,?,?,?,?,?,?,NULL,0,?,?)
                         ON CONFLICT(paperless_id) DO UPDATE SET titre=excluded.titre,
                         type_document=excluded.type_document, emetteur=excluded.emetteur, pays=excluded.pays,
                         resume=excluded.resume, montant=excluded.montant, devise=excluded.devise,
                         confiance=excluded.confiance, statut=excluded.statut, erreur=NULL, tentatives=0,
                         brut=excluded.brut, traite_le=excluded.traite_le""",
                      (doc_id, doc.get("title"), ex.type_document, ex.emetteur, ex.pays, ex.resume, ex.montant,
                       ex.devise, ex.confiance, ex.statut,
                       json.dumps({"llm": brut, "avertissements": ex.avertissements}, ensure_ascii=False),
                       now_iso()))
            for e in ex.echeances:
                self.db.x("""INSERT INTO echeances(paperless_id, nature, description, date_echeance, preavis_jours,
                             date_action, montant, devise, statut, origine, cree_le, maj_le)
                             VALUES(?,?,?,?,?,?,?,?,?,'ia',?,?)""",
                          (doc_id, e.nature, e.description, e.date_echeance.isoformat(), e.preavis_jours,
                           e.date_action.isoformat(), e.montant, ex.devise, e.statut, now_iso(), now_iso()))

        self._tag(doc_id, TAG_VALIDER if ex.statut == "a_valider" else TAG_OK)
        log.info("Document %s traité : %s, %d échéance(s)", doc_id, ex.statut, len(ex.echeances))
        return {"paperless_id": doc_id, "statut": ex.statut, "echeances": len(ex.echeances),
                "avertissements": ex.avertissements}

    def _tag(self, doc_id: int, tag: str):
        try:
            for t in (TAG_OK, TAG_VALIDER, TAG_ERREUR):
                if t != tag:
                    self.paperless.retirer_tag(doc_id, t)
            self.paperless.ajouter_tag(doc_id, tag)
        except Exception as e:  # le marquage est un confort, pas un blocage
            log.warning("Impossible de marquer le document %s : %s", doc_id, e)

    # ------------------------------------------------------------------ lecture
    def echeances(self, jours: int | None = None, statuts=("active", "a_valider"),
                  aujourd_hui: date | None = None) -> list[dict]:
        aujourd_hui = aujourd_hui or self.aujourd_hui()
        ph = ",".join("?" * len(statuts))
        sql = f"""SELECT e.*, d.titre, d.emetteur, d.type_document, d.pays FROM echeances e
                  LEFT JOIN documents d ON d.paperless_id = e.paperless_id
                  WHERE e.statut IN ({ph})"""
        params = list(statuts)
        if jours is not None:
            sql += " AND e.date_action <= ?"
            params.append((aujourd_hui + timedelta(days=jours)).isoformat())
        sql += " ORDER BY e.date_action, e.id"
        rows = self.db.q(sql, params)
        for r in rows:
            r["jours_restants"] = (parse_date(r["date_action"]) - aujourd_hui).days
            r["lien_document"] = self.paperless.lien(r["paperless_id"])
        return rows

    def documents_a_valider(self) -> list[dict]:
        rows = self.db.q("""SELECT paperless_id, titre, type_document, emetteur, pays, resume, confiance, statut,
                            erreur, brut, traite_le FROM documents WHERE statut IN ('a_valider','erreur')
                            ORDER BY traite_le DESC""")
        for r in rows:
            r["lien_document"] = self.paperless.lien(r["paperless_id"])
            r["echeances"] = self.db.q("SELECT * FROM echeances WHERE paperless_id=? ORDER BY date_echeance",
                                       (r["paperless_id"],))
            try:
                r["avertissements"] = json.loads(r.pop("brut") or "{}").get("avertissements", [])
            except ValueError:
                r["avertissements"] = []
        return rows

    def stats(self) -> dict:
        def c(sql, p=()):
            return self.db.one(sql, p)["n"]
        return {
            "documents": c("SELECT COUNT(*) n FROM documents"),
            "documents_a_valider": c("SELECT COUNT(*) n FROM documents WHERE statut='a_valider'"),
            "documents_en_erreur": c("SELECT COUNT(*) n FROM documents WHERE statut='erreur'"),
            "echeances_actives": c("SELECT COUNT(*) n FROM echeances WHERE statut='active'"),
            "echeances_a_valider": c("SELECT COUNT(*) n FROM echeances WHERE statut='a_valider'"),
            "a_refaire": c("SELECT COUNT(*) n FROM documents WHERE statut='a_refaire'"),
        }

    # ------------------------------------------------------------------ actions
    def changer_statut_echeance(self, ech_id: int, statut: str) -> dict | None:
        if statut not in ("active", "faite", "ignoree", "a_valider"):
            raise ValueError("statut invalide")
        self.db.x("UPDATE echeances SET statut=?, maj_le=? WHERE id=?", (statut, now_iso(), ech_id))
        r = self.db.one("SELECT * FROM echeances WHERE id=?", (ech_id,))
        if r:
            self._maj_statut_document(r["paperless_id"])
        return r

    def modifier_echeance(self, ech_id: int, champs: dict) -> dict | None:
        r = self.db.one("SELECT * FROM echeances WHERE id=?", (ech_id,))
        if not r:
            return None
        d = parse_date(champs.get("date_echeance")) or parse_date(r["date_echeance"])
        preavis = champs.get("preavis_jours", r["preavis_jours"])
        preavis = int(preavis) if preavis not in (None, "") else None
        desc = champs.get("description", r["description"])
        self.db.x("""UPDATE echeances SET date_echeance=?, preavis_jours=?, date_action=?, description=?,
                     statut='active', origine='manuel', maj_le=? WHERE id=?""",
                  (d.isoformat(), preavis, date_action(d, preavis).isoformat(), desc, now_iso(), ech_id))
        self.db.x("DELETE FROM alertes_envoyees WHERE echeance_id=?", (ech_id,))
        self._maj_statut_document(r["paperless_id"])
        return self.db.one("SELECT * FROM echeances WHERE id=?", (ech_id,))

    def ajouter_echeance(self, paperless_id: int, description: str, date_echeance: str,
                         preavis_jours: int | None = None, nature: str = "autre") -> int:
        d = parse_date(date_echeance)
        if d is None:
            raise ValueError("date invalide (AAAA-MM-JJ attendu)")
        if not self.db.one("SELECT 1 FROM documents WHERE paperless_id=?", (paperless_id,)):
            self.db.x("INSERT INTO documents(paperless_id, statut, traite_le) VALUES(?, 'traite', ?)",
                      (paperless_id, now_iso()))
        return self.db.x("""INSERT INTO echeances(paperless_id, nature, description, date_echeance, preavis_jours,
                            date_action, statut, origine, cree_le, maj_le) VALUES(?,?,?,?,?,?,'active','manuel',?,?)""",
                         (paperless_id, nature, description, d.isoformat(), preavis_jours,
                          date_action(d, preavis_jours).isoformat(), now_iso(), now_iso()))

    def valider_document(self, doc_id: int):
        """Valide d'un coup toutes les échéances en attente d'un document."""
        self.db.x("UPDATE echeances SET statut='active', maj_le=? WHERE paperless_id=? AND statut='a_valider'",
                  (now_iso(), doc_id))
        self.db.x("UPDATE documents SET statut='traite' WHERE paperless_id=?", (doc_id,))
        self._tag(doc_id, TAG_OK)

    def _maj_statut_document(self, doc_id: int):
        reste = self.db.one("SELECT COUNT(*) n FROM echeances WHERE paperless_id=? AND statut='a_valider'", (doc_id,))
        doc = self.db.one("SELECT statut FROM documents WHERE paperless_id=?", (doc_id,))
        if doc and doc["statut"] == "a_valider" and reste["n"] == 0:
            self.db.x("UPDATE documents SET statut='traite' WHERE paperless_id=?", (doc_id,))
            self._tag(doc_id, TAG_OK)

    # ------------------------------------------------------------------ alertes
    def verifier_alertes(self, aujourd_hui: date | None = None) -> list[dict]:
        aujourd_hui = aujourd_hui or self.aujourd_hui()
        envoyees = []
        # Les échéances dont la date est passée depuis plus de 7 jours sont archivées.
        limite = (aujourd_hui - timedelta(days=7)).isoformat()
        self.db.x("UPDATE echeances SET statut='passee', maj_le=? WHERE statut='active' AND date_echeance < ?",
                  (now_iso(), limite))
        for e in self.echeances(jours=max(self.s.alert_days or [0]), statuts=("active",), aujourd_hui=aujourd_hui):
            n = e["jours_restants"]
            seuil = seuil_applicable(n, self.s.alert_days)
            if seuil is None:
                continue
            if self.db.one("SELECT 1 FROM alertes_envoyees WHERE echeance_id=? AND seuil=?", (e["id"], seuil)):
                continue
            titre, msg, prio = self._texte_alerte(e, n)
            # EVA annonce l'alerte (monitor du matin) : on la marque comme envoyée pour ne jamais la répéter.
            self.db.x("INSERT OR IGNORE INTO alertes_envoyees VALUES(?,?,?)", (e["id"], seuil, now_iso()))
            envoyees.append({"echeance_id": e["id"], "seuil": seuil, "titre": titre, "message": msg, "priorite": prio,
                             "jours_restants": n, "lien": e["lien_document"]})
        return envoyees

    def _texte_alerte(self, e: dict, n: int):
        da = parse_date(e["date_action"])
        de = parse_date(e["date_echeance"])
        if e["preavis_jours"]:
            msg = (f"{e['description']} : échéance le {fr_date(de)}, préavis de {e['preavis_jours']} jours. "
                   f"Pour agir à temps : avant le {fr_date(da)} ({fr_delai(n)}).")
        else:
            msg = f"{e['description']} : {fr_date(de)} ({fr_delai(n)})."
        prio = 5 if n <= 1 else 4 if n <= 7 else 3
        titre = f"{NATURE_FR.get(e['nature'], 'échéance').capitalize()} {fr_delai(n)}"
        return titre, msg, prio

    # ------------------------------------------------------------------ résumés
    def resume(self, jours: int = 30, aujourd_hui: date | None = None) -> str:
        """Texte naturel, pensé pour être lu à voix haute par EVA."""
        aujourd_hui = aujourd_hui or self.aujourd_hui()
        items = self.echeances(jours=jours, statuts=("active",), aujourd_hui=aujourd_hui)
        a_valider = self.stats()["documents_a_valider"]
        if not items:
            txt = f"Rien d'administratif à prévoir dans les {jours} prochains jours."
        else:
            n = len(items)
            phrases = [f"Tu as {n} échéance{'s' if n > 1 else ''} dans les {jours} prochains jours."]
            for e in items[:8]:
                da, de = parse_date(e["date_action"]), parse_date(e["date_echeance"])
                if e["preavis_jours"]:
                    phrases.append(f"{e['description']} : à traiter avant le {fr_date(da)}, "
                                   f"{fr_delai(e['jours_restants'])}, pour une échéance le {fr_date(de)}.")
                else:
                    phrases.append(f"{e['description']} : le {fr_date(de)}, {fr_delai(e['jours_restants'])}.")
            if n > 8:
                phrases.append(f"Et {n - 8} autre{'s' if n - 8 > 1 else ''}.")
            txt = " ".join(phrases)
        if a_valider:
            txt += f" Il y a aussi {a_valider} document{'s' if a_valider > 1 else ''} à vérifier."
        return txt

    def question(self, texte: str) -> dict:
        """Répond à une question sur les papiers : recherche Paperless par mots-clés, inventaire des documents
        analysés (pour les questions générales comme « que racontent mes papiers ? ») et échéances connues."""
        inventaire = self.db.q("""SELECT paperless_id, titre, type_document, emetteur, pays, resume FROM documents
                                  WHERE statut <> 'erreur' ORDER BY traite_le DESC LIMIT 30""")
        docs = []
        requete = requete_paperless(texte)
        if requete:
            try:
                docs = self.paperless.recherche(requete, limite=3)
            except Exception as e:
                log.warning("Recherche Paperless impossible : %s", e)
        if not inventaire and not docs:
            return {"reponse": "Je n'ai encore analysé aucun de tes papiers. Dépose-les dans la page Papiers ou "
                               "dans un dossier surveillé : je pourrai en parler dès qu'ils seront lus.", "documents": []}
        contexte = []
        for d in docs:
            contenu = (d.get("content") or "")[:2500]
            contexte.append(f"[Document « {d.get('title')} » du {(d.get('created') or '')[:10]}]\n{contenu}")
        liste = [f"- « {d['titre']} » ({d['type_document'] or 'document'}"
                 + (f", {d['emetteur']}" if d['emetteur'] else "") + (f", {d['pays']}" if d['pays'] in ('FR', 'IT') else "")
                 + f") : {d['resume'] or 'pas de résumé'}" for d in inventaire]
        ech = self.echeances(jours=400, statuts=("active", "a_valider"))
        lignes = [f"- {e['description']} : échéance {e['date_echeance']}, agir avant {e['date_action']}"
                  for e in ech[:40]]
        user = (f"Date du jour : {self.aujourd_hui().isoformat()}\n\nPapiers analysés ({len(inventaire)}) :\n"
                + ("\n".join(liste) or "(aucun)") + "\n\nÉchéances connues :\n" + ("\n".join(lignes) or "(aucune)")
                + "\n\nExtraits des documents les plus proches de la question :\n" + ("\n\n".join(contexte) or "(aucun)")
                + f"\n\nQuestion : {texte}")
        system = ("Tu es EVA, l'assistante de la famille, et tu parles de ses papiers. Tutoie la personne et réponds dans sa langue. "
                  "Appuie-toi uniquement sur les informations fournies. Pour une question générale (« que disent mes papiers ? »), "
                  "fais un résumé court : combien de papiers, de quels types, ce qu'il faut retenir, les prochaines échéances. "
                  "Pour une question précise, réponds en trois phrases au plus et cite le document utilisé. "
                  "Si l'information n'y figure pas, dis-le simplement. Dates en toutes lettres (ex. « 4 novembre 2026 »).")
        reponse = self.ollama.chat(system, user)
        return {"reponse": reponse,
                "documents": [{"id": d["id"], "titre": d.get("title"), "lien": self.paperless.lien(d["id"])}
                              for d in docs]}
