"""Launch NANTA: platform bots + Knowledge Graph desktop UI."""

import multiprocessing
import os
import sys
import time


def run_telegram(config):
    """Run the Telegram bot."""
    sys.path.insert(0, os.path.dirname(__file__))
    from platforms.telegram.bot import main
    main(config)


def run_discord(config):
    """Run the Discord bot."""
    sys.path.insert(0, os.path.dirname(__file__))
    from platforms.discord.bot import main
    main(config)


def run_web():
    """Run the FastAPI web server."""
    sys.path.insert(0, os.path.dirname(__file__))
    from web.server import start
    start()


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config import load_config

    config = load_config()
    port = int(os.environ.get("WEB_PORT", "8420"))
    url = f"http://127.0.0.1:{port}"

    platforms_active = []
    if config.telegram:
        platforms_active.append("Telegram")
    if config.discord:
        platforms_active.append("Discord")

    print("=" * 50)
    print("  NANTA")
    print("=" * 50)
    if platforms_active:
        print(f"  Platforms: {', '.join(platforms_active)}")
    else:
        print("  No platforms configured — opening setup...")
    print(f"  Web:  {url}")
    print("=" * 50)

    procs = []

    # Start web server
    web_proc = multiprocessing.Process(target=run_web, name="web", daemon=True)
    web_proc.start()
    procs.append(web_proc)

    # Start platform bots
    if config.telegram:
        p = multiprocessing.Process(target=run_telegram, args=(config,), name="telegram", daemon=True)
        p.start()
        procs.append(p)

    if config.discord:
        p = multiprocessing.Process(target=run_discord, args=(config,), name="discord", daemon=True)
        p.start()
        procs.append(p)

    # Wait for web server to be ready
    import httpx
    for _ in range(30):
        try:
            httpx.get(url, timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    # Open native desktop window
    import webview
    window = webview.create_window(
        "NANTA",
        url=url,
        width=1200,
        height=800,
        min_size=(800, 500),
    )
    webview.start()  # Blocks until window is closed

    # Window closed — clean up
    print("\nShutting down...")
    for p in procs:
        p.terminate()
    for p in procs:
        p.join(timeout=5)
    print("Done.")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
