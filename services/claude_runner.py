import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Per-user sessions keyed by user_id (e.g. "telegram:123", "discord:456")
_sessions: dict[str, "ClaudeSession"] = {}


@dataclass
class ClaudeSession:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    process: asyncio.subprocess.Process | None = None
    working_dir: str = ""
    model: str = "sonnet"
    total_cost_usd: float = 0.0
    is_first_turn: bool = True


def get_session(user_id: str, default_cwd: str, default_model: str) -> ClaudeSession:
    """Get or create a session for a user."""
    if user_id not in _sessions:
        _sessions[user_id] = ClaudeSession(
            working_dir=default_cwd, model=default_model
        )
    return _sessions[user_id]


def reset_session(user_id: str, default_cwd: str, default_model: str) -> ClaudeSession:
    """Create a fresh session for a user."""
    _sessions[user_id] = ClaudeSession(
        working_dir=default_cwd, model=default_model
    )
    return _sessions[user_id]


async def cancel_claude(user_id: str) -> bool:
    """Kill the running Claude process for a user. Returns True if killed."""
    session = _sessions.get(user_id)
    if session and session.process and session.process.returncode is None:
        session.process.terminate()
        try:
            await asyncio.wait_for(session.process.wait(), timeout=5)
        except asyncio.TimeoutError:
            session.process.kill()
        session.process = None
        return True
    return False


def is_running(user_id: str) -> bool:
    session = _sessions.get(user_id)
    return bool(
        session and session.process and session.process.returncode is None
    )


async def run_claude_streaming(
    user_id: str,
    prompt: str,
    config,
    on_text_delta: callable = None,
    on_result: callable = None,
):
    """Run claude -p with stream-json output.

    Calls on_text_delta(text) for each content chunk.
    Calls on_result(full_text, cost_usd) when complete.
    """
    session = get_session(user_id, config.default_cwd, config.default_model)

    if is_running(user_id):
        raise RuntimeError("Claude is already running for this chat")

    cmd = [
        "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
        "--model", session.model,
        "--max-budget-usd", str(config.max_budget_usd),
    ]

    if session.is_first_turn:
        cmd.extend(["--session-id", session.session_id])
    else:
        cmd.extend(["--resume", session.session_id])

    logger.info("Claude cmd: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=session.working_dir,
    )
    session.process = proc

    accumulated_text = ""
    cost_usd = 0.0

    try:
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")

            if event_type == "assistant" and "message" in event:
                # Content block with text
                content_blocks = event["message"].get("content", [])
                for block in content_blocks:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        accumulated_text += text
                        if on_text_delta:
                            await on_text_delta(text)

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    accumulated_text += text
                    if on_text_delta:
                        await on_text_delta(text)

            elif event_type == "result":
                # Final result with cost
                cost_usd = event.get("cost_usd", 0.0)
                session.total_cost_usd += cost_usd
                result_text = event.get("result", "")
                if result_text and not accumulated_text:
                    accumulated_text = result_text
                if on_result:
                    await on_result(accumulated_text, cost_usd)

        await proc.wait()
        session.is_first_turn = False

    except asyncio.CancelledError:
        proc.terminate()
        raise

    finally:
        session.process = None

    # If we got no streaming text, try stderr for error info
    if not accumulated_text:
        stderr_data = await proc.stderr.read()
        err = stderr_data.decode("utf-8", errors="replace").strip()
        if err:
            accumulated_text = f"(No output)\n\nStderr:\n{err}"

    return accumulated_text, cost_usd


async def run_claude_simple(
    user_id: str, prompt: str, config
) -> tuple[str, float]:
    """Non-streaming fallback. Returns (text, cost_usd)."""
    session = get_session(user_id, config.default_cwd, config.default_model)

    if is_running(user_id):
        raise RuntimeError("Claude is already running for this chat")

    cmd = [
        "claude",
        "-p", prompt,
        "--output-format", "json",
        "--verbose",
        "--dangerously-skip-permissions",
        "--model", session.model,
        "--max-budget-usd", str(config.max_budget_usd),
    ]

    if session.is_first_turn:
        cmd.extend(["--session-id", session.session_id])
    else:
        cmd.extend(["--resume", session.session_id])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=session.working_dir,
    )
    session.process = proc

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=config.claude_timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        session.process = None
        return f"Claude timed out after {config.claude_timeout}s", 0.0
    finally:
        session.process = None

    session.is_first_turn = False

    raw = stdout.decode("utf-8", errors="replace").strip()
    cost_usd = 0.0

    try:
        data = json.loads(raw)
        text = data.get("result", raw)
        cost_usd = data.get("cost_usd", 0.0)
        session.total_cost_usd += cost_usd
    except json.JSONDecodeError:
        text = raw or stderr.decode("utf-8", errors="replace").strip()

    return text, cost_usd
