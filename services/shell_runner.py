import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_shell(command: str, cwd: str, timeout: int) -> tuple[int, str]:
    """Run a shell command and return (return_code, combined_output)."""
    logger.info("Shell: %s (cwd=%s, timeout=%ds)", command, cwd, timeout)

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
        )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        output = stdout.decode("utf-8", errors="replace")
        return proc.returncode, output

    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, f"Command timed out after {timeout}s"

    except Exception as e:
        logger.exception("Shell command failed")
        return -1, f"Error: {e}"
