"""Base SQLite des papiers (workspace/papiers/papiers.db, incluse dans la sauvegarde d'EVA) :
documents analysés, échéances, alertes annoncées, fichiers importés depuis les dossiers, réglages."""
import sqlite3
import threading
from datetime import datetime

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS documents(
    paperless_id INTEGER PRIMARY KEY,
    titre TEXT,
    type_document TEXT,
    emetteur TEXT,
    pays TEXT,
    resume TEXT,
    montant REAL,
    devise TEXT,
    confiance REAL,
    statut TEXT NOT NULL,          -- traite | a_valider | sans_echeance | erreur
    erreur TEXT,
    tentatives INTEGER NOT NULL DEFAULT 0,
    brut TEXT,
    traite_le TEXT
);
CREATE TABLE IF NOT EXISTS echeances(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paperless_id INTEGER NOT NULL,
    nature TEXT NOT NULL,
    description TEXT,
    date_echeance TEXT NOT NULL,
    preavis_jours INTEGER,
    date_action TEXT NOT NULL,     -- date à laquelle il faut agir (échéance - préavis)
    montant REAL,
    devise TEXT,
    statut TEXT NOT NULL,          -- a_valider | active | faite | ignoree | passee
    origine TEXT NOT NULL DEFAULT 'ia',   -- ia | manuel
    cree_le TEXT,
    maj_le TEXT
);
CREATE INDEX IF NOT EXISTS idx_ech_action ON echeances(date_action);
CREATE INDEX IF NOT EXISTS idx_ech_doc ON echeances(paperless_id);
CREATE TABLE IF NOT EXISTS alertes_envoyees(
    echeance_id INTEGER NOT NULL,
    seuil INTEGER NOT NULL,
    envoye_le TEXT,
    PRIMARY KEY(echeance_id, seuil)
);
CREATE TABLE IF NOT EXISTS kv(cle TEXT PRIMARY KEY, valeur TEXT);
CREATE TABLE IF NOT EXISTS imports(
    chemin TEXT PRIMARY KEY,       -- fichier repéré dans un dossier surveillé
    taille INTEGER,
    mtime REAL,
    statut TEXT NOT NULL,          -- envoye | erreur
    erreur TEXT,
    tentatives INTEGER NOT NULL DEFAULT 0,
    tache TEXT,
    devenu TEXT,                   -- où le fichier a été déplacé après l'envoi (vide = laissé ou supprimé)
    maj_le TEXT
);
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def q(self, sql: str, params=()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params=()):
        rows = self.q(sql, params)
        return rows[0] if rows else None

    def x(self, sql: str, params=()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid

    def get_kv(self, cle: str, defaut=None):
        r = self.one("SELECT valeur FROM kv WHERE cle=?", (cle,))
        return r["valeur"] if r else defaut

    def set_kv(self, cle: str, valeur: str):
        self.x("INSERT INTO kv(cle, valeur) VALUES(?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur",
               (cle, valeur))
