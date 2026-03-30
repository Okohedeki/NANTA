MAX_MESSAGE_LENGTH = 4096


def chunk_message(text: str, max_len: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split text into chunks that fit within a platform's message limit.

    Splits on newline boundaries when possible.
    """
    if not text:
        return ["(empty output)"]

    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Find last newline within limit
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1 or split_at < max_len // 2:
            # No good newline break, hard-split
            split_at = max_len

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks


def format_shell_output(return_code: int, output: str) -> str:
    """Format shell command output with return code."""
    result = output.rstrip() if output.rstrip() else "(no output)"
    if return_code != 0:
        result += f"\n\n[exit code: {return_code}]"
    return result
