import asyncio
import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from security import authorized
from services.content_extractor import extract_from_file
from services.entity_extractor import extract_entities
from services.ingestion_service import ingest_url
from services.knowledge_graph import (
    add_entity,
    add_relationship,
    add_source,
    get_entity_by_name,
    get_graph_context_for_query,
    get_recent_sources,
    get_stats,
    get_top_entities,
    link_entity_to_source,
    search_entities,
)
from services.output_formatter import chunk_message

logger = logging.getLogger(__name__)


def _extract_urls(message) -> list[str]:
    """Extract URLs from Telegram message entities."""
    urls = []
    if not message.entities:
        return urls
    for entity in message.entities:
        if entity.type == "url":
            urls.append(message.parse_entity(entity))
        elif entity.type == "text_link":
            urls.append(entity.url)
    return urls


async def _ingest_content(content, config, db, chat_id, status_msg, label: str):
    """Run entity extraction and store results in the knowledge graph.

    Returns (entity_count, rel_count, cost_usd, summary) or raises on failure.
    """
    await status_msg.edit_text(f"{label} Analyzing content...")

    extraction = await extract_entities(
        content.content_text,
        content.title,
        content.source_type,
        model=config.default_model,
    )

    summary = extraction.get("summary", "")
    source_id = await add_source(
        db,
        content.url,
        content.title,
        content.source_type,
        content.content_text,
        summary,
        chat_id,
    )

    entity_count = 0
    rel_count = 0

    if extraction["success"]:
        for ent in extraction["entities"]:
            ent_id = await add_entity(db, ent["name"], ent["type"], ent.get("description", ""))
            await link_entity_to_source(db, ent_id, source_id)
            entity_count += 1

        for rel in extraction["relationships"]:
            src_ent = await get_entity_by_name(db, rel["source"])
            tgt_ent = await get_entity_by_name(db, rel["target"])
            if src_ent and tgt_ent:
                await add_relationship(db, src_ent["id"], tgt_ent["id"], rel["type"])
                rel_count += 1

    return entity_count, rel_count, extraction.get("cost_usd", 0.0), summary


# ── URL Handler ───────────────────────────────────────────────────


@authorized
async def url_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages containing URLs — extract, analyze, and store in knowledge graph."""
    message = update.message
    urls = _extract_urls(message)

    if not urls:
        return

    config = context.bot_data["config"]
    db = context.bot_data["kg_db"]
    chat_id = update.effective_chat.id
    tmp_dir = os.path.join(os.path.dirname(config.kg_db_path), "tmp")

    status_msg = await message.reply_text(f"Found {len(urls)} URL(s). Processing...")

    total_entities = 0
    total_rels = 0
    total_cost = 0.0

    for i, url in enumerate(urls):
        label = f"[{i + 1}/{len(urls)}]"
        try:
            await status_msg.edit_text(f"{label} Processing: {url}")

            result = await ingest_url(
                db, url,
                model=config.default_model,
                whisper_model=config.whisper_model,
                tmp_dir=tmp_dir,
                chat_id=chat_id,
            )

            if not result["success"]:
                await message.reply_text(f"{label} Failed: {result.get('error', 'Unknown error')}")
                continue

            total_entities += result["entity_count"]
            total_rels += result["rel_count"]
            total_cost += result["cost_usd"]

            result_lines = [
                f"Ingested: {result['title'] or url}",
                f"Type: {result['source_type']}",
                f"Entities: {result['entity_count']} | Relationships: {result['rel_count']}",
                f"Cost: ${result['cost_usd']:.4f}",
            ]
            if result.get("summary"):
                result_lines.append(f"\nSummary: {result['summary']}")

            try:
                await status_msg.edit_text("\n".join(result_lines))
            except Exception:
                await message.reply_text("\n".join(result_lines))

        except Exception as e:
            logger.exception("Failed to process URL: %s", url)
            await message.reply_text(f"{label} Error processing {url}: {e}")

    if len(urls) > 1:
        await message.reply_text(
            f"Done. Totals: {total_entities} entities, {total_rels} relationships, ${total_cost:.4f}"
        )


# ── Media Handler ─────────────────────────────────────────────────


@authorized
async def media_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice, audio, video messages — transcribe and store in knowledge graph."""
    message = update.message
    config = context.bot_data["config"]
    db = context.bot_data["kg_db"]
    chat_id = update.effective_chat.id
    tmp_dir = os.path.join(os.path.dirname(config.kg_db_path), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    # Determine media type and get file
    if message.voice:
        media = message.voice
        source_type = "voice"
    elif message.audio:
        media = message.audio
        source_type = "audio"
    elif message.video:
        media = message.video
        source_type = "video"
    elif message.video_note:
        media = message.video_note
        source_type = "video"
    else:
        return

    status_msg = await message.reply_text(f"Downloading {source_type}...")

    file_path = os.path.join(tmp_dir, f"{source_type}_{media.file_unique_id}")

    try:
        # Download file from Telegram
        tg_file = await media.get_file()
        await tg_file.download_to_drive(file_path)

        await status_msg.edit_text(f"Transcribing {source_type}...")

        content = await extract_from_file(file_path, source_type, config.whisper_model)

        if not content.success:
            await status_msg.edit_text(f"Transcription failed: {content.error}")
            return

        if not content.content_text.strip():
            await status_msg.edit_text("Transcription returned empty text.")
            return

        ent_count, rel_count, cost, summary = await _ingest_content(
            content, config, db, chat_id, status_msg, ""
        )

        result_lines = [
            f"Ingested: {source_type} message",
            f"Entities: {ent_count} | Relationships: {rel_count}",
            f"Cost: ${cost:.4f}",
        ]
        if summary:
            result_lines.append(f"\nSummary: {summary}")

        # Show a snippet of the transcript
        transcript_preview = content.content_text[:300]
        if len(content.content_text) > 300:
            transcript_preview += "..."
        result_lines.append(f"\nTranscript: {transcript_preview}")

        chunks = chunk_message("\n".join(result_lines))
        try:
            await status_msg.edit_text(chunks[0])
        except Exception:
            await message.reply_text(chunks[0])
        for chunk in chunks[1:]:
            await message.reply_text(chunk)

    except Exception as e:
        logger.exception("Media processing failed")
        await status_msg.edit_text(f"Error: {e}")
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


# ── Query Commands ────────────────────────────────────────────────


@authorized
async def kg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /kg <question> — query the knowledge graph with natural language."""
    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/kg <question> — ask about your knowledge graph\n"
            "/kgsearch <term> — search entities by name\n"
            "/kgstats — graph statistics\n"
            "/kgrecent — recently ingested content"
        )
        return

    query = " ".join(context.args)
    config = context.bot_data["config"]
    db = context.bot_data["kg_db"]

    status_msg = await update.message.reply_text("Querying knowledge graph...")

    graph_context = await get_graph_context_for_query(db, query)

    prompt = (
        "You have access to a knowledge graph built from content the user has saved.\n\n"
        f"Graph context:\n{graph_context}\n\n"
        f"User's question: {query}\n\n"
        "Answer using ONLY the information from the graph context above. "
        "If the information isn't in the graph, say so. Be concise."
    )

    cmd = [
        "claude",
        "-p", prompt,
        "--output-format", "json",
        "--model", config.default_model,
        "--max-budget-usd", "0.50",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        raw = stdout.decode("utf-8", errors="replace").strip()

        import json

        cost = 0.0
        text = raw
        try:
            data = json.loads(raw)
            text = data.get("result", raw)
            cost = data.get("cost_usd", 0.0)
        except json.JSONDecodeError:
            pass

        result_text = text.rstrip() + f"\n\n[cost: ${cost:.4f}]"
        chunks = chunk_message(result_text)

        try:
            await status_msg.edit_text(chunks[0])
        except Exception:
            await update.message.reply_text(chunks[0])
        for chunk in chunks[1:]:
            await update.message.reply_text(chunk)

    except asyncio.TimeoutError:
        await status_msg.edit_text("Query timed out.")
    except Exception as e:
        logger.exception("KG query failed")
        await status_msg.edit_text(f"Error: {e}")


@authorized
async def kgsearch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /kgsearch <term> — search entities by name."""
    if not context.args:
        await update.message.reply_text("Usage: /kgsearch <term>")
        return

    query = " ".join(context.args)
    db = context.bot_data["kg_db"]

    results = await search_entities(db, query, limit=15)

    if not results:
        await update.message.reply_text(f"No entities matching '{query}'")
        return

    from services.knowledge_graph import get_entity_relationships

    lines = [f"Search results for '{query}':\n"]
    for e in results:
        lines.append(f"• {e['name']} ({e['entity_type']})")
        if e.get("description"):
            lines.append(f"  {e['description']}")

        rels = await get_entity_relationships(db, e["id"])
        if rels:
            for r in rels[:5]:
                if r["source_name"] == e["name"]:
                    lines.append(f"  → {r['relationship_type']} → {r['target_name']}")
                else:
                    lines.append(f"  ← {r['relationship_type']} ← {r['source_name']}")
            if len(rels) > 5:
                lines.append(f"  ...and {len(rels) - 5} more relationships")
        lines.append("")

    chunks = chunk_message("\n".join(lines))
    for chunk in chunks:
        await update.message.reply_text(chunk)


@authorized
async def kgstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /kgstats — show knowledge graph statistics."""
    db = context.bot_data["kg_db"]

    stats = await get_stats(db)
    top = await get_top_entities(db, limit=10)

    lines = [
        "Knowledge Graph Stats\n",
        f"Sources: {stats['sources']}",
        f"Entities: {stats['entities']}",
        f"Relationships: {stats['relationships']}",
    ]

    if top:
        lines.append("\nMost Connected Entities:")
        for e in top:
            lines.append(f"  • {e['name']} ({e['entity_type']}) — {e['rel_count']} rels, {e['source_count']} sources")

    await update.message.reply_text("\n".join(lines))


@authorized
async def kgrecent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /kgrecent — show recently ingested content."""
    db = context.bot_data["kg_db"]

    sources = await get_recent_sources(db, limit=10)

    if not sources:
        await update.message.reply_text("No content ingested yet.")
        return

    lines = ["Recent Ingestions:\n"]
    for s in sources:
        title = s["title"] or s["url"] or "Direct media"
        lines.append(f"• [{s['source_type']}] {title}")
        if s.get("summary"):
            lines.append(f"  {s['summary'][:150]}")
        lines.append(f"  {s['entity_count']} entities | {s['ingested_at']}")
        lines.append("")

    chunks = chunk_message("\n".join(lines))
    for chunk in chunks:
        await update.message.reply_text(chunk)
