"""Auto-categorize a source into one of the existing categories using the LLM."""

import json
import logging
import re

from services.knowledge_graph import get_categories, set_source_categories
from services.providers.detection import get_provider

logger = logging.getLogger(__name__)


_PROMPT = """You categorize knowledge-graph items into ONE of the available categories.

CATEGORIES:
{cat_lines}

ITEM TITLE: {title}

ITEM CONTENT (excerpt):
{excerpt}

Pick the SINGLE category that best fits. Return ONLY a JSON object:
{{"category": "<exact name from list>"}}

If none clearly fits, pick "Society & Culture" as a default if it exists, else the
first category in the list. Do not invent new categories.
"""


async def auto_categorize_source(
    db,
    source_id: int,
    title: str,
    content_excerpt: str,
    model: str = "sonnet",
    force: bool = False,
) -> int | None:
    """Pick a category for the source via LLM, store it, return category_id (or None).

    If `force=True`, replaces any existing categories. Otherwise skips sources
    that already have at least one category (so manual picks are preserved).
    """
    cats = await get_categories(db)
    if not cats:
        return None

    if not force:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM source_categories WHERE source_id = ?", (source_id,)
        )
        (has_any,) = await cursor.fetchone()
        if has_any > 0:
            return None

    cat_lines = "\n".join(f"- {c['name']}" for c in cats)
    cat_by_name = {c["name"].lower(): c for c in cats}

    prompt = _PROMPT.format(
        cat_lines=cat_lines,
        title=title or "(untitled)",
        excerpt=(content_excerpt or "")[:1500],
    )

    provider = get_provider()
    try:
        raw, _cost = await provider.run_simple(prompt, model=model, timeout=45)
    except Exception as e:
        logger.warning("auto_categorize LLM call failed: %s", e)
        return None

    match = re.search(r"\{[\s\S]*?\}", raw or "")
    chosen = None
    if match:
        try:
            data = json.loads(match.group())
            chosen = (data.get("category") or "").strip().lower()
        except json.JSONDecodeError:
            pass

    if not chosen or chosen not in cat_by_name:
        for name, c in cat_by_name.items():
            if name in (raw or "").lower():
                chosen = name
                break

    if not chosen or chosen not in cat_by_name:
        return None

    cat_id = cat_by_name[chosen]["id"]
    await set_source_categories(db, source_id, [cat_id])
    logger.info("Categorized source %s → %s%s",
                source_id, cat_by_name[chosen]["name"], " (forced)" if force else "")
    return cat_id


async def reclassify_all_sources(db, model: str = "sonnet") -> dict:
    """Run the categorizer against every source in the DB, overriding prior picks."""
    cursor = await db.execute(
        "SELECT id, title, summary, content_text, source_type FROM sources ORDER BY id"
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    from services.knowledge_graph import log_event

    ok, fail = 0, 0
    for s in rows:
        excerpt = s.get("summary") or (s.get("content_text") or "")[:1500]
        try:
            cat_id = await auto_categorize_source(
                db, s["id"], s.get("title") or "", excerpt,
                model=model, force=True,
            )
            if cat_id:
                ok += 1
            else:
                fail += 1
        except Exception as e:
            logger.warning("Reclassify failed for source %s: %s", s["id"], e)
            fail += 1
    await log_event(db, "info",
                    f"Reclassified {ok}/{len(rows)} sources ({fail} unresolved)")
    return {"success": True, "total": len(rows), "categorized": ok, "unresolved": fail}
