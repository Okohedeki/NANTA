import logging
import os

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT,
    title TEXT,
    source_type TEXT,
    content_text TEXT,
    summary TEXT,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    chat_id INTEGER
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    description TEXT,
    UNIQUE(name, entity_type)
);

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity_id INTEGER REFERENCES entities(id),
    target_entity_id INTEGER REFERENCES entities(id),
    relationship_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    UNIQUE(source_entity_id, target_entity_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS entity_sources (
    entity_id INTEGER REFERENCES entities(id),
    source_id INTEGER REFERENCES sources(id),
    PRIMARY KEY (entity_id, source_id)
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    parent_id INTEGER REFERENCES categories(id),
    color TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_categories (
    source_id INTEGER REFERENCES sources(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (source_id, category_id)
);

CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_sources_url ON sources(url);
CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_id);
CREATE INDEX IF NOT EXISTS idx_source_categories_source ON source_categories(source_id);
CREATE INDEX IF NOT EXISTS idx_source_categories_category ON source_categories(category_id);
"""


async def init_db(db_path: str) -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.executescript(_SCHEMA)
    await _run_migrations(conn)
    await conn.commit()
    logger.info("Knowledge graph DB ready at %s", db_path)
    return conn


async def _run_migrations(conn: aiosqlite.Connection):
    """Add columns to existing tables if missing."""
    cursor = await conn.execute("PRAGMA table_info(sources)")
    columns = {row[1] for row in await cursor.fetchall()}

    if "is_note" not in columns:
        await conn.execute("ALTER TABLE sources ADD COLUMN is_note INTEGER DEFAULT 0")
    if "updated_at" not in columns:
        await conn.execute("ALTER TABLE sources ADD COLUMN updated_at TIMESTAMP")

    await conn.commit()


async def close_db(conn: aiosqlite.Connection):
    await conn.close()


# ── Write operations ──────────────────────────────────────────────


async def add_source(
    conn: aiosqlite.Connection,
    url: str | None,
    title: str | None,
    source_type: str,
    content_text: str | None,
    summary: str | None,
    chat_id: int,
) -> int:
    cursor = await conn.execute(
        """INSERT INTO sources (url, title, source_type, content_text, summary, chat_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (url, title, source_type, content_text, summary, chat_id),
    )
    await conn.commit()
    return cursor.lastrowid


async def add_entity(
    conn: aiosqlite.Connection,
    name: str,
    entity_type: str,
    description: str | None = None,
) -> int:
    await conn.execute(
        """INSERT INTO entities (name, entity_type, description)
           VALUES (?, ?, ?)
           ON CONFLICT(name, entity_type) DO UPDATE SET
             description = COALESCE(NULLIF(excluded.description, ''), entities.description)""",
        (name, entity_type, description),
    )
    await conn.commit()
    cursor = await conn.execute(
        "SELECT id FROM entities WHERE name = ? AND entity_type = ?",
        (name, entity_type),
    )
    row = await cursor.fetchone()
    return row[0]


async def add_relationship(
    conn: aiosqlite.Connection,
    source_entity_id: int,
    target_entity_id: int,
    relationship_type: str,
) -> int:
    cursor = await conn.execute(
        """INSERT INTO relationships (source_entity_id, target_entity_id, relationship_type)
           VALUES (?, ?, ?)
           ON CONFLICT(source_entity_id, target_entity_id, relationship_type)
           DO UPDATE SET weight = relationships.weight + 1""",
        (source_entity_id, target_entity_id, relationship_type),
    )
    await conn.commit()
    return cursor.lastrowid


async def link_entity_to_source(
    conn: aiosqlite.Connection, entity_id: int, source_id: int
):
    await conn.execute(
        "INSERT OR IGNORE INTO entity_sources (entity_id, source_id) VALUES (?, ?)",
        (entity_id, source_id),
    )
    await conn.commit()


async def delete_source_by_url(conn: aiosqlite.Connection, url: str) -> int:
    """Delete a source and its orphaned entities/relationships by URL."""
    cursor = await conn.execute("SELECT id FROM sources WHERE url = ?", (url,))
    rows = await cursor.fetchall()
    if not rows:
        return 0
    for row in rows:
        await _delete_source_cascade(conn, row[0])
    await conn.commit()
    return len(rows)


async def delete_source_by_id(conn: aiosqlite.Connection, source_id: int) -> bool:
    """Delete a source/note by ID with orphan cleanup."""
    cursor = await conn.execute("SELECT id FROM sources WHERE id = ?", (source_id,))
    if not await cursor.fetchone():
        return False
    await _delete_source_cascade(conn, source_id)
    await conn.commit()
    return True


async def _delete_source_cascade(conn: aiosqlite.Connection, source_id: int):
    """Remove a source and clean up orphaned entities/relationships."""
    # Find entities linked ONLY to this source
    cursor = await conn.execute(
        """SELECT entity_id FROM entity_sources
           WHERE entity_id IN (
               SELECT entity_id FROM entity_sources WHERE source_id = ?
           )
           GROUP BY entity_id
           HAVING COUNT(source_id) = 1""",
        (source_id,),
    )
    orphan_ids = [r[0] for r in await cursor.fetchall()]

    await conn.execute("DELETE FROM entity_sources WHERE source_id = ?", (source_id,))
    await conn.execute("DELETE FROM source_categories WHERE source_id = ?", (source_id,))

    if orphan_ids:
        ph = ",".join("?" * len(orphan_ids))
        await conn.execute(
            f"DELETE FROM relationships WHERE source_entity_id IN ({ph}) "
            f"OR target_entity_id IN ({ph})",
            orphan_ids + orphan_ids,
        )
        await conn.execute(f"DELETE FROM entities WHERE id IN ({ph})", orphan_ids)

    await conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))


# ── Notes ─────────────────────────────────────────────────────────


async def create_note(
    conn: aiosqlite.Connection,
    title: str,
    content_text: str,
    summary: str | None = None,
) -> int:
    cursor = await conn.execute(
        """INSERT INTO sources (url, title, source_type, content_text, summary, chat_id, is_note)
           VALUES (NULL, ?, 'note', ?, ?, 0, 1)""",
        (title, content_text, summary),
    )
    await conn.commit()
    return cursor.lastrowid


async def update_note(
    conn: aiosqlite.Connection,
    source_id: int,
    title: str,
    content_text: str,
    summary: str | None = None,
) -> bool:
    cursor = await conn.execute(
        """UPDATE sources SET title = ?, content_text = ?, summary = ?,
           updated_at = CURRENT_TIMESTAMP
           WHERE id = ? AND is_note = 1""",
        (title, content_text, summary, source_id),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def clear_source_entities(conn: aiosqlite.Connection, source_id: int):
    """Remove all entity links for a source (before re-extraction)."""
    # Find entities that will become orphaned
    cursor = await conn.execute(
        """SELECT entity_id FROM entity_sources
           WHERE entity_id IN (
               SELECT entity_id FROM entity_sources WHERE source_id = ?
           )
           GROUP BY entity_id
           HAVING COUNT(source_id) = 1""",
        (source_id,),
    )
    orphan_ids = [r[0] for r in await cursor.fetchall()]

    await conn.execute("DELETE FROM entity_sources WHERE source_id = ?", (source_id,))

    if orphan_ids:
        ph = ",".join("?" * len(orphan_ids))
        await conn.execute(
            f"DELETE FROM relationships WHERE source_entity_id IN ({ph}) "
            f"OR target_entity_id IN ({ph})",
            orphan_ids + orphan_ids,
        )
        await conn.execute(f"DELETE FROM entities WHERE id IN ({ph})", orphan_ids)

    await conn.commit()


# ── Categories ────────────────────────────────────────────────────


async def create_category(
    conn: aiosqlite.Connection,
    name: str,
    parent_id: int | None = None,
    color: str | None = None,
) -> int:
    cursor = await conn.execute(
        "INSERT INTO categories (name, parent_id, color) VALUES (?, ?, ?)",
        (name, parent_id, color),
    )
    await conn.commit()
    return cursor.lastrowid


async def update_category(
    conn: aiosqlite.Connection,
    category_id: int,
    name: str | None = None,
    parent_id: int | None = None,
    color: str | None = None,
) -> bool:
    sets, vals = [], []
    if name is not None:
        sets.append("name = ?")
        vals.append(name)
    if parent_id is not None:
        sets.append("parent_id = ?")
        vals.append(parent_id if parent_id != 0 else None)
    if color is not None:
        sets.append("color = ?")
        vals.append(color)
    if not sets:
        return False
    vals.append(category_id)
    cursor = await conn.execute(
        f"UPDATE categories SET {', '.join(sets)} WHERE id = ?", vals
    )
    await conn.commit()
    return cursor.rowcount > 0


async def delete_category(conn: aiosqlite.Connection, category_id: int) -> bool:
    # Re-parent children to this category's parent
    cursor = await conn.execute(
        "SELECT parent_id FROM categories WHERE id = ?", (category_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return False
    parent = row[0]
    await conn.execute(
        "UPDATE categories SET parent_id = ? WHERE parent_id = ?",
        (parent, category_id),
    )
    await conn.execute("DELETE FROM source_categories WHERE category_id = ?", (category_id,))
    await conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    await conn.commit()
    return True


async def get_categories(conn: aiosqlite.Connection) -> list[dict]:
    cursor = await conn.execute(
        """SELECT c.id, c.name, c.parent_id, c.color, c.sort_order,
                  (SELECT COUNT(*) FROM source_categories sc WHERE sc.category_id = c.id) AS item_count
           FROM categories c
           ORDER BY c.sort_order, c.name"""
    )
    return [dict(r) for r in await cursor.fetchall()]


async def set_source_categories(
    conn: aiosqlite.Connection, source_id: int, category_ids: list[int]
):
    await conn.execute("DELETE FROM source_categories WHERE source_id = ?", (source_id,))
    for cid in category_ids:
        await conn.execute(
            "INSERT OR IGNORE INTO source_categories (source_id, category_id) VALUES (?, ?)",
            (source_id, cid),
        )
    await conn.commit()


async def get_source_categories(conn: aiosqlite.Connection, source_id: int) -> list[dict]:
    cursor = await conn.execute(
        """SELECT c.id, c.name, c.color FROM categories c
           JOIN source_categories sc ON sc.category_id = c.id
           WHERE sc.source_id = ?""",
        (source_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


# ── Read operations ───────────────────────────────────────────────


async def search_entities(
    conn: aiosqlite.Connection, query: str, limit: int = 20
) -> list[dict]:
    cursor = await conn.execute(
        """SELECT e.id, e.name, e.entity_type, e.description,
                  COUNT(es.source_id) AS source_count
           FROM entities e
           LEFT JOIN entity_sources es ON es.entity_id = e.id
           WHERE e.name LIKE ?
           GROUP BY e.id
           ORDER BY source_count DESC
           LIMIT ?""",
        (f"%{query}%", limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_entity_relationships(
    conn: aiosqlite.Connection, entity_id: int
) -> list[dict]:
    cursor = await conn.execute(
        """SELECT r.relationship_type, r.weight,
                  e1.name AS source_name, e1.entity_type AS source_type,
                  e2.name AS target_name, e2.entity_type AS target_type
           FROM relationships r
           JOIN entities e1 ON e1.id = r.source_entity_id
           JOIN entities e2 ON e2.id = r.target_entity_id
           WHERE r.source_entity_id = ? OR r.target_entity_id = ?""",
        (entity_id, entity_id),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_entity_by_name(
    conn: aiosqlite.Connection, name: str
) -> dict | None:
    cursor = await conn.execute(
        "SELECT id, name, entity_type, description FROM entities WHERE name = ?",
        (name,),
    )
    row = await cursor.fetchone()
    if row:
        return dict(row)
    cursor = await conn.execute(
        "SELECT id, name, entity_type, description FROM entities WHERE name LIKE ? LIMIT 1",
        (name,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_recent_sources(
    conn: aiosqlite.Connection, limit: int = 10, category_id: int | None = None
) -> list[dict]:
    if category_id:
        cursor = await conn.execute(
            """SELECT s.id, s.url, s.title, s.source_type, s.summary, s.ingested_at,
                      COALESCE(s.is_note, 0) AS is_note,
                      COUNT(es.entity_id) AS entity_count
               FROM sources s
               LEFT JOIN entity_sources es ON es.source_id = s.id
               JOIN source_categories sc ON sc.source_id = s.id
               WHERE sc.category_id = ?
               GROUP BY s.id
               ORDER BY s.ingested_at DESC
               LIMIT ?""",
            (category_id, limit),
        )
    else:
        cursor = await conn.execute(
            """SELECT s.id, s.url, s.title, s.source_type, s.summary, s.ingested_at,
                      COALESCE(s.is_note, 0) AS is_note,
                      COUNT(es.entity_id) AS entity_count
               FROM sources s
               LEFT JOIN entity_sources es ON es.source_id = s.id
               GROUP BY s.id
               ORDER BY s.ingested_at DESC
               LIMIT ?""",
            (limit,),
        )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_source_entities(
    conn: aiosqlite.Connection, source_id: int
) -> list[dict]:
    cursor = await conn.execute(
        """SELECT e.id, e.name, e.entity_type, e.description
           FROM entities e
           JOIN entity_sources es ON es.entity_id = e.id
           WHERE es.source_id = ?""",
        (source_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_stats(conn: aiosqlite.Connection) -> dict:
    counts = {}
    for table in ("sources", "entities", "relationships"):
        cursor = await conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        row = await cursor.fetchone()
        counts[table] = row[0]

    cursor = await conn.execute("SELECT COUNT(*) FROM sources WHERE is_note = 1")
    counts["notes"] = (await cursor.fetchone())[0]
    cursor = await conn.execute("SELECT COUNT(*) FROM categories")
    counts["categories"] = (await cursor.fetchone())[0]
    return counts


async def get_top_entities(
    conn: aiosqlite.Connection, limit: int = 20
) -> list[dict]:
    cursor = await conn.execute(
        """SELECT e.id, e.name, e.entity_type, e.description,
                  (SELECT COUNT(*) FROM relationships r
                   WHERE r.source_entity_id = e.id OR r.target_entity_id = e.id
                  ) AS rel_count,
                  (SELECT COUNT(*) FROM entity_sources es
                   WHERE es.entity_id = e.id
                  ) AS source_count
           FROM entities e
           ORDER BY rel_count DESC, source_count DESC
           LIMIT ?""",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_source_backlinks(
    conn: aiosqlite.Connection, source_id: int
) -> list[dict]:
    """Find other sources that share entities with this source."""
    cursor = await conn.execute(
        """SELECT s.id, s.title, s.source_type, s.url,
                  COALESCE(s.is_note, 0) AS is_note,
                  COUNT(DISTINCT es2.entity_id) AS shared_entities
           FROM entity_sources es1
           JOIN entity_sources es2 ON es2.entity_id = es1.entity_id AND es2.source_id != es1.source_id
           JOIN sources s ON s.id = es2.source_id
           WHERE es1.source_id = ?
           GROUP BY s.id
           ORDER BY shared_entities DESC""",
        (source_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_graph_context_for_query(
    conn: aiosqlite.Connection, query: str
) -> str:
    """Build a text context from the graph for Claude to answer questions."""
    parts = []

    matches = await search_entities(conn, query, limit=15)
    if matches:
        parts.append("== Matching Entities ==")
        for e in matches:
            rels = await get_entity_relationships(conn, e["id"])
            rel_strs = []
            for r in rels:
                if r["source_name"] == e["name"]:
                    rel_strs.append(f"  -> {r['relationship_type']} -> {r['target_name']} ({r['target_type']})")
                else:
                    rel_strs.append(f"  <- {r['relationship_type']} <- {r['source_name']} ({r['source_type']})")
            desc = f" - {e['description']}" if e.get("description") else ""
            parts.append(f"\n{e['name']} ({e['entity_type']}){desc}")
            parts.extend(rel_strs)

    top = await get_top_entities(conn, limit=15)
    if top:
        parts.append("\n== Top Entities (most connected) ==")
        for e in top:
            parts.append(f"- {e['name']} ({e['entity_type']}) [{e['rel_count']} rels, {e['source_count']} sources]")

    recent = await get_recent_sources(conn, limit=10)
    if recent:
        parts.append("\n== Recent Sources ==")
        for s in recent:
            title = s["title"] or s["url"] or "Direct media"
            summary = f" - {s['summary'][:200]}" if s.get("summary") else ""
            parts.append(f"- [{s['source_type']}] {title}{summary}")

    stats = await get_stats(conn)
    parts.append(
        f"\n== Graph Stats: {stats['entities']} entities, "
        f"{stats['relationships']} relationships, {stats['sources']} sources =="
    )

    return "\n".join(parts) if parts else "(Knowledge graph is empty)"
