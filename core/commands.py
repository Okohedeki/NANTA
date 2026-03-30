"""Platform-agnostic command handlers.

All business logic extracted from the original Telegram-specific handlers.
Each function takes a PlatformContext and operates through the adapter protocol.
"""

import asyncio
import json
import logging
import os
import sys
import time

from core.auth import authorized
from services.claude_runner import (
    cancel_claude,
    get_session,
    is_running,
    reset_session,
    run_claude_streaming,
)
from services.content_extractor import extract_from_file
from services.entity_extractor import extract_entities
from services.ingestion_service import ingest_url
from services.knowledge_graph import (
    add_entity,
    add_relationship,
    add_source,
    get_entity_by_name,
    get_entity_relationships,
    get_graph_context_for_query,
    get_recent_sources,
    get_stats,
    get_top_entities,
    link_entity_to_source,
    search_entities,
)
from services.output_formatter import chunk_message, format_shell_output
from services.shell_runner import run_shell

logger = logging.getLogger(__name__)


# ── Admin Commands ───────────────────────────────────────────────


async def handle_start(ctx):
    """Welcome message with user ID (no auth required)."""
    await ctx.message.reply(
        f"Nexus Bot\n\n"
        f"Your ID: {ctx.user_id}\n\n"
        f"Add this ID to your platform's allowed IDs in .env to authorize access.\n"
        f"Then send /help for available commands."
    )


@authorized
async def handle_help(ctx):
    """List all commands."""
    await ctx.message.reply(
        "Just type a message to chat with Claude!\n\n"
        "/claude <prompt> - Send prompt to Claude Code\n"
        "/cl <prompt> - Short alias for /claude\n"
        "/sh <command> - Execute shell command\n"
        "/cancel - Kill running Claude process\n"
        "/status - Show session info\n"
        "/cwd [path] - Get/set working directory\n"
        "/model [name] - Get/set Claude model\n"
        "/newsession - Start fresh Claude session\n"
        "/mcp <subcommand> - Run claude mcp commands\n"
        "/commands - List all commands\n"
        "/restart - Restart the bot\n"
        "/start - Show your ID\n"
        "/help - This message\n\n"
        "Knowledge Graph:\n"
        "Send URLs or media to auto-ingest into your knowledge graph.\n"
        "/kg <question> - Query your knowledge graph\n"
        "/kgsearch <term> - Search entities by name\n"
        "/kgstats - Graph statistics\n"
        "/kgrecent - Recently ingested content"
    )


@authorized
async def handle_status(ctx):
    """Show session info."""
    config = ctx.get_config()
    session = get_session(ctx.user_id, config.default_cwd, config.default_model)
    running = is_running(ctx.user_id)
    cwd = ctx.get_cwd()

    await ctx.message.reply(
        f"Session: {session.session_id}\n"
        f"Model: {session.model}\n"
        f"Working dir: {cwd}\n"
        f"Running: {'yes' if running else 'no'}\n"
        f"Total cost: ${session.total_cost_usd:.4f}\n"
        f"Turn: {'first' if session.is_first_turn else 'follow-up'}"
    )


@authorized
async def handle_cwd(ctx):
    """Get or set working directory."""
    config = ctx.get_config()

    if not ctx.command_args:
        await ctx.message.reply(f"Current directory: {ctx.get_cwd()}")
        return

    new_path = " ".join(ctx.command_args)

    if not os.path.isdir(new_path):
        await ctx.message.reply(f"Directory not found: {new_path}")
        return

    new_path = os.path.abspath(new_path)
    ctx.set_cwd(new_path)

    # Also update Claude session working dir
    session = get_session(ctx.user_id, config.default_cwd, config.default_model)
    session.working_dir = new_path

    await ctx.message.reply(f"Working directory set to: {new_path}")


@authorized
async def handle_model(ctx):
    """Get or set Claude model."""
    config = ctx.get_config()
    session = get_session(ctx.user_id, config.default_cwd, config.default_model)

    if not ctx.command_args:
        await ctx.message.reply(f"Current model: {session.model}")
        return

    new_model = ctx.command_args[0]
    session.model = new_model
    await ctx.message.reply(f"Model set to: {new_model}")


@authorized
async def handle_newsession(ctx):
    """Start fresh Claude session."""
    config = ctx.get_config()
    cwd = ctx.get_cwd()
    session = reset_session(ctx.user_id, cwd, config.default_model)
    await ctx.message.reply(f"New session started: {session.session_id}")


@authorized
async def handle_commands(ctx):
    """List all available commands."""
    await ctx.message.reply(
        "Plain text - Send prompt to Claude (no command needed)\n"
        "/claude <prompt> - Send prompt to Claude Code\n"
        "/cl <prompt> - Short alias for /claude\n"
        "/sh <command> - Execute shell command\n"
        "/cancel - Kill running Claude process\n"
        "/status - Show session info\n"
        "/cwd [path] - Get/set working directory\n"
        "/model [name] - Get/set Claude model\n"
        "/newsession - Start fresh Claude session\n"
        "/mcp <subcommand> - Run claude mcp commands\n"
        "/commands - This message\n"
        "/restart - Restart the bot\n"
        "/start - Show your ID\n"
        "/help - Help message\n\n"
        "Knowledge Graph:\n"
        "Send URLs/media → auto-ingest\n"
        "/kg <question> - Query knowledge graph\n"
        "/kgsearch <term> - Search entities\n"
        "/kgstats - Graph stats\n"
        "/kgrecent - Recent ingestions"
    )


@authorized
async def handle_mcp(ctx):
    """Run claude mcp subcommands."""
    if not ctx.command_args:
        await ctx.message.reply(
            "Usage: /mcp <subcommand>\n\n"
            "Examples:\n"
            "/mcp list\n"
            "/mcp add <name> <command>\n"
            "/mcp remove <name>"
        )
        return

    args = " ".join(ctx.command_args)
    config = ctx.get_config()
    cwd = ctx.get_cwd()

    msg = await ctx.message.reply(f"Running: claude mcp {args}")

    return_code, output = await run_shell(f"claude mcp {args}", cwd, config.shell_timeout)
    result = format_shell_output(return_code, output)

    chunks = chunk_message(result, ctx.max_message_length)
    await msg.edit(chunks[0])
    for chunk in chunks[1:]:
        await ctx.message.reply(chunk)


@authorized
async def handle_restart(ctx):
    """Restart the bot process."""
    await ctx.message.reply("Restarting bot...")
    logger.info("Bot restart requested by %s", ctx.user_id)
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ── Claude Commands ──────────────────────────────────────────────


async def _run_claude_with_streaming(ctx, prompt: str):
    """Shared streaming logic for claude command and default messages."""
    config = ctx.get_config()

    if is_running(ctx.user_id):
        await ctx.message.reply("Claude is already running. Use /cancel to stop it.")
        return

    status_msg = await ctx.message.reply("Thinking...")

    accumulated = ""
    last_edit_time = 0.0
    final_cost = 0.0
    edit_interval = ctx.edit_interval
    max_preview = ctx.max_message_length - 600  # Leave room for edits

    async def on_text_delta(text: str):
        nonlocal accumulated, last_edit_time
        accumulated += text

        now = time.monotonic()
        if now - last_edit_time >= edit_interval:
            last_edit_time = now
            preview = accumulated[-max_preview:] if len(accumulated) > max_preview else accumulated
            if preview.strip():
                try:
                    await status_msg.edit(preview)
                except Exception:
                    pass

    async def on_result(full_text: str, cost_usd: float):
        nonlocal final_cost, accumulated
        final_cost = cost_usd
        if full_text:
            accumulated = full_text

    try:
        text, cost = await asyncio.wait_for(
            run_claude_streaming(
                ctx.user_id, prompt, config,
                on_text_delta=on_text_delta,
                on_result=on_result,
            ),
            timeout=config.claude_timeout,
        )
    except asyncio.TimeoutError:
        await cancel_claude(ctx.user_id)
        await status_msg.edit(
            f"Claude timed out after {config.claude_timeout}s. Process killed."
        )
        return
    except RuntimeError as e:
        await status_msg.edit(str(e))
        return
    except Exception:
        logger.exception("Claude command failed")
        await status_msg.edit("Claude encountered an error.")
        return

    if not accumulated:
        accumulated = text or "(no output)"
    cost = final_cost or cost

    footer = f"\n\n[cost: ${cost:.4f}]"
    result_text = accumulated.rstrip() + footer

    chunks = chunk_message(result_text, ctx.max_message_length)

    try:
        await status_msg.edit(chunks[0])
    except Exception:
        pass

    for chunk in chunks[1:]:
        await ctx.message.reply(chunk)


@authorized
async def handle_claude(ctx):
    """Handle /claude <prompt> and /cl <prompt>."""
    if not ctx.command_args:
        await ctx.message.reply("Usage: /claude <prompt>")
        return
    prompt = " ".join(ctx.command_args)
    await _run_claude_with_streaming(ctx, prompt)


@authorized
async def handle_default_message(ctx):
    """Handle plain text messages as Claude prompts."""
    prompt = ctx.raw_text
    if not prompt or not prompt.strip():
        return
    await _run_claude_with_streaming(ctx, prompt)


@authorized
async def handle_cancel(ctx):
    """Kill running Claude process."""
    killed = await cancel_claude(ctx.user_id)
    if killed:
        await ctx.message.reply("Claude process cancelled.")
    else:
        await ctx.message.reply("No Claude process is running.")


# ── Shell Command ────────────────────────────────────────────────


@authorized
async def handle_shell(ctx):
    """Execute a shell command."""
    if not ctx.command_args:
        await ctx.message.reply("Usage: /sh <command>")
        return

    command = " ".join(ctx.command_args)
    config = ctx.get_config()
    cwd = ctx.get_cwd()

    msg = await ctx.message.reply(f"Running: {command}")

    return_code, output = await run_shell(command, cwd, config.shell_timeout)
    result = format_shell_output(return_code, output)

    chunks = chunk_message(result, ctx.max_message_length)
    await msg.edit(chunks[0])
    for chunk in chunks[1:]:
        await ctx.message.reply(chunk)


# ── Knowledge Graph: Ingestion ───────────────────────────────────


@authorized
async def handle_url_message(ctx):
    """Handle messages containing URLs — extract, analyze, and store."""
    urls = ctx.extract_urls()
    if not urls:
        return

    config = ctx.get_config()
    db = ctx.get_db()
    tmp_dir = os.path.join(os.path.dirname(config.kg_db_path), "tmp")

    status_msg = await ctx.message.reply(f"Found {len(urls)} URL(s). Processing...")

    total_entities = 0
    total_rels = 0
    total_cost = 0.0

    for i, url in enumerate(urls):
        label = f"[{i + 1}/{len(urls)}]"
        try:
            await status_msg.edit(f"{label} Processing: {url}")

            result = await ingest_url(
                db, url,
                model=config.default_model,
                whisper_model=config.whisper_model,
                tmp_dir=tmp_dir,
                chat_id=0,
            )

            if not result["success"]:
                await ctx.message.reply(f"{label} Failed: {result.get('error', 'Unknown error')}")
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
                await status_msg.edit("\n".join(result_lines))
            except Exception:
                await ctx.message.reply("\n".join(result_lines))

        except Exception as e:
            logger.exception("Failed to process URL: %s", url)
            await ctx.message.reply(f"{label} Error processing {url}: {e}")

    if len(urls) > 1:
        await ctx.message.reply(
            f"Done. Totals: {total_entities} entities, {total_rels} relationships, ${total_cost:.4f}"
        )


@authorized
async def handle_media_message(ctx):
    """Handle voice, audio, video messages — transcribe and store."""
    config = ctx.get_config()
    db = ctx.get_db()
    tmp_dir = os.path.join(os.path.dirname(config.kg_db_path), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    attachment = await ctx.download_attachment(tmp_dir)
    if not attachment:
        return

    file_path, source_type = attachment
    status_msg = await ctx.message.reply(f"Transcribing {source_type}...")

    try:
        content = await extract_from_file(file_path, source_type, config.whisper_model)

        if not content.success:
            await status_msg.edit(f"Transcription failed: {content.error}")
            return

        if not content.content_text.strip():
            await status_msg.edit("Transcription returned empty text.")
            return

        await status_msg.edit("Analyzing content...")

        extraction = await extract_entities(
            content.content_text,
            content.title,
            content.source_type,
            model=config.default_model,
        )

        summary = extraction.get("summary", "")
        source_id = await add_source(
            db, content.url, content.title, content.source_type,
            content.content_text, summary, 0,
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

        cost = extraction.get("cost_usd", 0.0)

        result_lines = [
            f"Ingested: {source_type} message",
            f"Entities: {entity_count} | Relationships: {rel_count}",
            f"Cost: ${cost:.4f}",
        ]
        if summary:
            result_lines.append(f"\nSummary: {summary}")

        transcript_preview = content.content_text[:300]
        if len(content.content_text) > 300:
            transcript_preview += "..."
        result_lines.append(f"\nTranscript: {transcript_preview}")

        chunks = chunk_message("\n".join(result_lines), ctx.max_message_length)
        try:
            await status_msg.edit(chunks[0])
        except Exception:
            await ctx.message.reply(chunks[0])
        for chunk in chunks[1:]:
            await ctx.message.reply(chunk)

    except Exception as e:
        logger.exception("Media processing failed")
        await status_msg.edit(f"Error: {e}")
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


# ── Knowledge Graph: Query Commands ──────────────────────────────


@authorized
async def handle_kg(ctx):
    """Query the knowledge graph with natural language."""
    if not ctx.command_args:
        await ctx.message.reply(
            "Usage:\n"
            "/kg <question> — ask about your knowledge graph\n"
            "/kgsearch <term> — search entities by name\n"
            "/kgstats — graph statistics\n"
            "/kgrecent — recently ingested content"
        )
        return

    query = " ".join(ctx.command_args)
    config = ctx.get_config()
    db = ctx.get_db()

    status_msg = await ctx.message.reply("Querying knowledge graph...")

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

        cost = 0.0
        text = raw
        try:
            data = json.loads(raw)
            text = data.get("result", raw)
            cost = data.get("cost_usd", 0.0)
        except json.JSONDecodeError:
            pass

        result_text = text.rstrip() + f"\n\n[cost: ${cost:.4f}]"
        chunks = chunk_message(result_text, ctx.max_message_length)

        try:
            await status_msg.edit(chunks[0])
        except Exception:
            await ctx.message.reply(chunks[0])
        for chunk in chunks[1:]:
            await ctx.message.reply(chunk)

    except asyncio.TimeoutError:
        await status_msg.edit("Query timed out.")
    except Exception as e:
        logger.exception("KG query failed")
        await status_msg.edit(f"Error: {e}")


@authorized
async def handle_kgsearch(ctx):
    """Search entities by name."""
    if not ctx.command_args:
        await ctx.message.reply("Usage: /kgsearch <term>")
        return

    query = " ".join(ctx.command_args)
    db = ctx.get_db()

    results = await search_entities(db, query, limit=15)

    if not results:
        await ctx.message.reply(f"No entities matching '{query}'")
        return

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

    chunks = chunk_message("\n".join(lines), ctx.max_message_length)
    for chunk in chunks:
        await ctx.message.reply(chunk)


@authorized
async def handle_kgstats(ctx):
    """Show knowledge graph statistics."""
    db = ctx.get_db()

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

    await ctx.message.reply("\n".join(lines))


@authorized
async def handle_kgrecent(ctx):
    """Show recently ingested content."""
    db = ctx.get_db()

    sources = await get_recent_sources(db, limit=10)

    if not sources:
        await ctx.message.reply("No content ingested yet.")
        return

    lines = ["Recent Ingestions:\n"]
    for s in sources:
        title = s["title"] or s.get("url") or "Direct media"
        lines.append(f"• [{s['source_type']}] {title}")
        if s.get("summary"):
            lines.append(f"  {s['summary'][:150]}")
        lines.append(f"  {s['entity_count']} entities | {s['ingested_at']}")
        lines.append("")

    chunks = chunk_message("\n".join(lines), ctx.max_message_length)
    for chunk in chunks:
        await ctx.message.reply(chunk)
