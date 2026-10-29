import asyncpg

from .config import settings

_pool: asyncpg.Pool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_session_created_idx
    ON messages (session_id, created_at);

-- Conversations (liste, titres). Les messages restent dans `messages`.
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO sessions (id, created_at, updated_at)
    SELECT session_id, min(created_at), max(created_at) FROM messages GROUP BY session_id
    ON CONFLICT (id) DO NOTHING;

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS model TEXT NOT NULL DEFAULT '';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS owner TEXT NOT NULL DEFAULT '';
-- Corbeille : une conversation supprimée y reste 30 jours (supprime_le), puis est effacée pour de bon.
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS supprime_le TIMESTAMPTZ;
-- Projet de rattachement et fil conducteur (résumé glissant des échanges anciens, voir fil.py).
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS project TEXT DEFAULT '';           -- NULL possible (anciennes sauvegardes) = aucun projet
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS resume TEXT DEFAULT '';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS resume_upto BIGINT DEFAULT 0;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS resume_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS sessions_project_idx ON sessions (project) WHERE coalesce(project, '') <> '';

ALTER TABLE messages ADD COLUMN IF NOT EXISTS trace_id BIGINT;

-- Avis de l'utilisateur sur les réponses d'EVA (apprentissage).
CREATE TABLE IF NOT EXISTS feedback (
    message_id BIGINT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    trace_id BIGINT,
    rating SMALLINT NOT NULL,                       -- 1 ou -1
    comment TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Propositions de modification du code d'EVA (validées par l'utilisateur).
CREATE TABLE IF NOT EXISTS proposals (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '',
    files JSONB NOT NULL,                           -- {chemin: {"old": str|null, "new": str}}
    diff TEXT NOT NULL DEFAULT '',
    checks JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending',         -- pending | applied | rejected | reverted | failed_checks
    commit_sha TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ
);

-- Réglages persistants (clé -> JSON).
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

-- Agents (à la demande, planifiés) et leur historique d'exécution.
CREATE TABLE IF NOT EXISTS agents (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    template TEXT NOT NULL DEFAULT 'custom',
    instruction TEXT NOT NULL,
    schedule_type TEXT NOT NULL DEFAULT 'manual',   -- manual | interval | cron
    schedule_value TEXT NOT NULL DEFAULT '',        -- secondes (interval) ou expression cron
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    next_run_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_runs (
    id BIGSERIAL PRIMARY KEY,
    agent_id BIGINT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',         -- running | ok | error
    output TEXT NOT NULL DEFAULT '',
    trace_id BIGINT
);
CREATE INDEX IF NOT EXISTS agent_runs_agent_idx ON agent_runs (agent_id, started_at DESC);

-- Documents indexés (embeddings stockés en REAL[], similarité calculée côté EVA).
CREATE TABLE IF NOT EXISTS doc_files (
    path TEXT PRIMARY KEY,
    mtime DOUBLE PRECISION NOT NULL,
    size BIGINT NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS doc_chunks (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,                           -- chemin de fichier ou "conversation:<session>"
    kind TEXT NOT NULL DEFAULT 'file',              -- file | message
    ref TEXT NOT NULL DEFAULT '',                   -- id de message pour kind=message
    chunk_index INT NOT NULL DEFAULT 0,
    content TEXT NOT NULL,
    embedding REAL[] NOT NULL
);
CREATE INDEX IF NOT EXISTS doc_chunks_source_idx ON doc_chunks (source);
CREATE INDEX IF NOT EXISTS doc_chunks_ref_idx ON doc_chunks (kind, ref);

-- Journal des modifications faites par EVA elle-même (fichiers, skills) : chacune peut être annulée.
CREATE TABLE IF NOT EXISTS changes (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL,                             -- fs_write | fs_append | fs_delete | skill_save | skill_install
    path TEXT NOT NULL,                             -- relatif au workspace
    before TEXT,                                    -- NULL = le fichier n'existait pas
    after TEXT,                                     -- NULL = le fichier a été supprimé
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    undone_at TIMESTAMPTZ
);

-- Sessions de connexion (jeton aléatoire : seule son empreinte est stockée).
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    created TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires TIMESTAMPTZ NOT NULL,
    agent TEXT NOT NULL DEFAULT ''
);

-- Comptes de connexion (plusieurs utilisateurs). role : admin | user. Mot de passe haché (scrypt).
CREATE TABLE IF NOT EXISTS auth_users (
    name TEXT PRIMARY KEY,
    display TEXT NOT NULL,
    salt TEXT NOT NULL,
    hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    disabled BOOLEAN NOT NULL DEFAULT false,
    created TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login TIMESTAMPTZ
);
ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS totp TEXT NOT NULL DEFAULT '';
ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS username TEXT NOT NULL DEFAULT '';

-- Journal d'accès (style bastion) : connexions, échecs, refus, actions qui modifient quelque chose.
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    username TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    status INT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS audit_log_ts ON audit_log (ts DESC);

-- Listes (courses, tâches…), appareils de la maison, scènes, imprimantes.
CREATE TABLE IF NOT EXISTS lists (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'custom',
    created TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Listes privées : owner = la personne (vide = liste de la famille, visible de tous).
ALTER TABLE lists ADD COLUMN IF NOT EXISTS owner TEXT NOT NULL DEFAULT '';
DROP INDEX IF EXISTS lists_name;
CREATE UNIQUE INDEX IF NOT EXISTS lists_name_owner ON lists (lower(name), lower(owner));
CREATE TABLE IF NOT EXISTS list_items (
    id SERIAL PRIMARY KEY,
    list_id INT NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    done BOOLEAN NOT NULL DEFAULT false,
    by TEXT NOT NULL DEFAULT '',
    created TIMESTAMPTZ NOT NULL DEFAULT now(),
    done_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS list_items_list ON list_items (list_id, done, id);
CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    room TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT 'switch',
    driver TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    aliases TEXT NOT NULL DEFAULT '',
    confirm BOOLEAN NOT NULL DEFAULT false,
    created TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS devices_name ON devices (lower(name));
CREATE TABLE IF NOT EXISTS scenes (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    created TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS scenes_name ON scenes (lower(name));
CREATE TABLE IF NOT EXISTS printers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    uri TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT false,
    created TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS printers_name ON printers (lower(name));

-- Machines du réseau enregistrées (accès SSH que l'utilisateur a fourni lui-même).
CREATE TABLE IF NOT EXISTS net_hosts (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    port INT NOT NULL DEFAULT 22,
    username TEXT NOT NULL DEFAULT 'root',
    auth TEXT NOT NULL DEFAULT 'password',
    secret TEXT NOT NULL DEFAULT '',
    host_key TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS net_hosts_name ON net_hosts (lower(name));

-- Post-it affichés à l'écran (créés par l'utilisateur ou par EVA). x/y : position en fraction de l'écran (0..1).
CREATE TABLE IF NOT EXISTS notes (
    id BIGSERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT 'jaune',
    x DOUBLE PRECISION NOT NULL DEFAULT 0.4,
    y DOUBLE PRECISION NOT NULL DEFAULT 0.2,
    done BOOLEAN NOT NULL DEFAULT FALSE,
    created_by TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE notes ADD COLUMN IF NOT EXISTS owner TEXT;                 -- NULL : ancien post-it, visible de tous
ALTER TABLE notes ADD COLUMN IF NOT EXISTS shared JSONB NOT NULL DEFAULT '[]'::jsonb;  -- noms des personnes (ou "*" : tout le monde) avec qui il est partagé
ALTER TABLE notes ADD COLUMN IF NOT EXISTS done_at TIMESTAMPTZ;  -- date de traitement (post-it validé = rangé dans la corbeille)

-- Traces : un enregistrement par tour de conversation ou exécution d'agent.
CREATE TABLE IF NOT EXISTS traces (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'chat',              -- chat | agent
    session_id TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_ms INT NOT NULL DEFAULT 0,
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    ok BOOLEAN NOT NULL DEFAULT TRUE,
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS traces_started_idx ON traces (started_at DESC);
"""


async def init_db() -> None:
    global _pool
    _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA)
        from .memoire import SCHEMA as SCHEMA_MEMOIRE
        await conn.execute(SCHEMA_MEMOIRE)
        from .wiki import SCHEMA as SCHEMA_WIKI
        await conn.execute(SCHEMA_WIKI)
        from .recettes import SCHEMA as SCHEMA_RECETTES
        await conn.execute(SCHEMA_RECETTES)
        from .finances import SCHEMA as SCHEMA_FINANCES
        await conn.execute(SCHEMA_FINANCES)
        from .contenus import SCHEMA as SCHEMA_CONTENUS
        await conn.execute(SCHEMA_CONTENUS)
        from .rappels import SCHEMA as SCHEMA_RAPPELS
        await conn.execute(SCHEMA_RAPPELS)
        from .lecons import SCHEMA as SCHEMA_LECONS
        await conn.execute(SCHEMA_LECONS)
        from .journal import SCHEMA as SCHEMA_JOURNAL
        await conn.execute(SCHEMA_JOURNAL)
        from .miroir import SCHEMA as SCHEMA_MIROIR
        await conn.execute(SCHEMA_MIROIR)
        from .inventaire import SCHEMA as SCHEMA_INVENTAIRE
        await conn.execute(SCHEMA_INVENTAIRE)


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("La base de données n'est pas initialisée (init_db() jamais appelé).")
    return _pool
