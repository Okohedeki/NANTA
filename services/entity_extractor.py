import asyncio
import json
import logging
import re

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """Extract key entities and relationships from this {source_type} content.

Title: {title}

Content:
{content}

Return a JSON object with this exact structure:
{{
  "summary": "A thorough, detailed summary (1-2 paragraphs) covering all key points, arguments, and takeaways so a reader can fully understand the content without reading the original",
  "entities": [
    {{"name": "Entity Name", "type": "person|topic|concept|org|place|technology|event", "description": "brief description"}}
  ],
  "relationships": [
    {{"source": "Entity Name 1", "target": "Entity Name 2", "type": "related_to|created|works_at|part_of|discusses|mentions|caused_by|uses|compared_to"}}
  ]
}}

Rules:
- Normalize entity names (capitalize properly, use full names)
- Merge near-duplicates (e.g., "AI" and "Artificial Intelligence" -> "Artificial Intelligence")
- Include 3-15 entities depending on content length
- Only include clear, meaningful relationships
- Return ONLY valid JSON, no other text"""


async def extract_entities(
    content_text: str,
    title: str,
    source_type: str,
    model: str = "sonnet",
) -> dict:
    """Call Claude to extract entities and relationships from content.

    Returns dict with keys: summary, entities, relationships, cost_usd, success, error
    """
    # Truncate content to keep the call fast and cheap
    truncated = content_text[:8000]

    prompt = _PROMPT_TEMPLATE.format(
        source_type=source_type,
        title=title or "Untitled",
        content=truncated,
    )

    cmd = [
        "claude",
        "-p", prompt,
        "--output-format", "json",
        "--model", model,
        "--max-budget-usd", "0.50",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        raw = stdout.decode("utf-8", errors="replace").strip()

        if not raw:
            err = stderr.decode("utf-8", errors="replace").strip()
            return {
                "summary": "", "entities": [], "relationships": [],
                "cost_usd": 0.0, "success": False,
                "error": f"Claude returned empty output. Stderr: {err[:500]}",
            }

        # Parse the outer JSON (Claude CLI wrapper)
        cost_usd = 0.0
        result_text = raw
        try:
            outer = json.loads(raw)
            result_text = outer.get("result", raw)
            cost_usd = outer.get("cost_usd", 0.0)
        except json.JSONDecodeError:
            pass

        # Parse the inner JSON (entity extraction result)
        parsed = _parse_extraction_json(result_text)
        if parsed:
            parsed["cost_usd"] = cost_usd
            parsed["success"] = True
            parsed["error"] = None
            return parsed

        return {
            "summary": "", "entities": [], "relationships": [],
            "cost_usd": cost_usd, "success": False,
            "error": f"Could not parse Claude's response as JSON: {result_text[:300]}",
        }

    except asyncio.TimeoutError:
        return {
            "summary": "", "entities": [], "relationships": [],
            "cost_usd": 0.0, "success": False, "error": "Claude timed out after 120s",
        }
    except Exception as e:
        logger.exception("Entity extraction failed")
        return {
            "summary": "", "entities": [], "relationships": [],
            "cost_usd": 0.0, "success": False, "error": str(e),
        }


def _parse_extraction_json(text: str) -> dict | None:
    """Try to parse entity extraction JSON from Claude's response."""
    # Direct parse
    try:
        data = json.loads(text)
        if "entities" in data:
            return _validate_extraction(data)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON block from text (Claude sometimes wraps in markdown)
    match = re.search(r"\{[\s\S]*\"entities\"[\s\S]*\}", text)
    if match:
        try:
            data = json.loads(match.group())
            return _validate_extraction(data)
        except json.JSONDecodeError:
            pass

    return None


def _validate_extraction(data: dict) -> dict:
    """Ensure the extraction result has the expected structure."""
    return {
        "summary": data.get("summary", ""),
        "entities": [
            {
                "name": e.get("name", ""),
                "type": e.get("type", "concept"),
                "description": e.get("description", ""),
            }
            for e in data.get("entities", [])
            if e.get("name")
        ],
        "relationships": [
            {
                "source": r.get("source", ""),
                "target": r.get("target", ""),
                "type": r.get("type", "related_to"),
            }
            for r in data.get("relationships", [])
            if r.get("source") and r.get("target")
        ],
    }
