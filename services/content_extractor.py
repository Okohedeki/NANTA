import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass, field

import httpx

from services.transcriber import transcribe

logger = logging.getLogger(__name__)

# Domains mapped to source types
_DOMAIN_MAP = {
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "tiktok.com": "tiktok",
    "instagram.com": "instagram",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "reddit.com": "reddit",
    "open.spotify.com": "audio",
    "soundcloud.com": "audio",
    "podcasts.apple.com": "audio",
    "arxiv.org": "article",
    "scholar.google.com": "article",
    "pubmed.ncbi.nlm.nih.gov": "article",
    "doi.org": "article",
}

# Source types where we should attempt audio download + transcription
_MEDIA_TYPES = {"youtube", "tiktok", "instagram", "twitter", "reddit", "audio", "media"}


@dataclass
class ExtractedContent:
    url: str
    source_type: str
    title: str
    content_text: str
    metadata: dict = field(default_factory=dict)
    success: bool = True
    error: str | None = None


def classify_url(url: str) -> str:
    """Classify a URL into a source type based on domain."""
    url_lower = url.lower().rstrip("/")
    # Check if URL points to a PDF
    if url_lower.endswith(".pdf"):
        return "pdf"
    # arxiv.org/pdf/ URLs are always PDFs
    if "arxiv.org/pdf/" in url_lower:
        return "pdf"
    for domain, stype in _DOMAIN_MAP.items():
        if domain in url_lower:
            return stype
    return "article"


async def extract_content(url: str, tmp_dir: str, whisper_model: str = "base") -> ExtractedContent:
    """Extract content from a URL. Main entry point."""
    source_type = classify_url(url)

    if source_type == "pdf":
        return await _extract_pdf(url, tmp_dir)
    elif source_type == "twitter":
        return await _extract_twitter(url, tmp_dir, whisper_model)
    elif source_type == "reddit":
        return await _extract_reddit(url, tmp_dir, whisper_model)
    elif source_type in _MEDIA_TYPES:
        return await _extract_media(url, source_type, tmp_dir, whisper_model)
    else:
        return await _extract_article(url)


async def _extract_media(
    url: str, source_type: str, tmp_dir: str, whisper_model: str
) -> ExtractedContent:
    """Extract content from media URLs using yt-dlp + optional whisper transcription."""
    try:
        # Step 1: Get metadata and try to get subtitles
        info = await _ytdlp_extract_info(url)
        if info is None:
            # yt-dlp failed, try article extraction as fallback
            return await _extract_article(url)

        title = info.get("title", "")
        description = info.get("description", "")

        # Step 2: Try to get subtitles/captions
        subtitle_text = _extract_subtitles_from_info(info)

        if subtitle_text:
            content = f"{description}\n\n--- Transcript ---\n{subtitle_text}" if description else subtitle_text
            return ExtractedContent(
                url=url,
                source_type=source_type,
                title=title,
                content_text=content,
                metadata=_extract_metadata(info),
            )

        # Step 3: No subtitles — download audio and transcribe
        transcript = await _download_and_transcribe(url, tmp_dir, whisper_model)

        if transcript:
            content = f"{description}\n\n--- Transcript ---\n{transcript}" if description else transcript
        elif description:
            content = description
        else:
            content = title

        return ExtractedContent(
            url=url,
            source_type=source_type,
            title=title,
            content_text=content,
            metadata=_extract_metadata(info),
        )

    except Exception as e:
        logger.exception("Media extraction failed for %s", url)
        # Fallback to article extraction
        try:
            return await _extract_article(url)
        except Exception:
            return ExtractedContent(
                url=url, source_type=source_type, title="", content_text="",
                success=False, error=str(e),
            )


async def _ytdlp_extract_info(url: str) -> dict | None:
    """Use yt-dlp to extract video/audio metadata without downloading."""
    try:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, _ytdlp_info_sync, url)
        return info
    except Exception as e:
        logger.warning("yt-dlp info extraction failed for %s: %s", url, e)
        return None


def _ytdlp_info_sync(url: str) -> dict | None:
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writeautomaticsub": True,
        "writesubtitles": True,
        "subtitleslangs": ["en", "en-US", "en-GB"],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


def _extract_subtitles_from_info(info: dict) -> str | None:
    """Try to extract subtitle text from yt-dlp info dict."""
    # Check for requested subtitles (auto or manual)
    for sub_key in ("requested_subtitles", "subtitles", "automatic_captions"):
        subs = info.get(sub_key)
        if not subs:
            continue
        for lang in ("en", "en-US", "en-GB"):
            if lang in subs:
                sub_data = subs[lang]
                if isinstance(sub_data, list):
                    # List of subtitle format options
                    for fmt in sub_data:
                        if isinstance(fmt, dict) and fmt.get("ext") == "json3":
                            # Some formats embed the text directly
                            pass
                elif isinstance(sub_data, dict) and "data" in sub_data:
                    return sub_data["data"]
    return None


def _extract_metadata(info: dict) -> dict:
    """Pull useful metadata from yt-dlp info."""
    keys = [
        "uploader", "upload_date", "duration", "view_count",
        "like_count", "channel", "webpage_url",
    ]
    return {k: info[k] for k in keys if k in info and info[k] is not None}


async def _download_and_transcribe(
    url: str, tmp_dir: str, whisper_model: str
) -> str | None:
    """Download audio from URL via yt-dlp and transcribe with whisper."""
    os.makedirs(tmp_dir, exist_ok=True)
    audio_path = os.path.join(tmp_dir, f"audio_{id(url)}")

    try:
        loop = asyncio.get_running_loop()
        actual_path = await loop.run_in_executor(
            None, _ytdlp_download_audio_sync, url, audio_path
        )
        if actual_path and os.path.exists(actual_path):
            transcript = await transcribe(actual_path, model_size=whisper_model)
            return transcript
        return None
    except Exception as e:
        logger.warning("Download+transcribe failed for %s: %s", url, e)
        return None
    finally:
        # Clean up any downloaded file
        for ext in ("", ".opus", ".m4a", ".webm", ".mp3", ".wav", ".ogg"):
            p = audio_path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def _ytdlp_download_audio_sync(url: str, output_path: str) -> str | None:
    """Download audio-only via yt-dlp. Returns path to downloaded file."""
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "outtmpl": output_path + ".%(ext)s",
        "max_filesize": 100 * 1024 * 1024,  # 100MB limit
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info:
            # yt-dlp appends the extension
            ext = info.get("ext", "opus")
            return f"{output_path}.{ext}"
    return None


async def _extract_twitter(
    url: str, tmp_dir: str, whisper_model: str
) -> ExtractedContent:
    """Extract tweet content using the fxtwitter API, with yt-dlp fallback for video."""
    import re

    # Parse tweet ID and username from URL
    match = re.search(r"(?:twitter\.com|x\.com)/(\w+)/status/(\d+)", url)
    if not match:
        return await _extract_media(url, "twitter", tmp_dir, whisper_model)

    username, tweet_id = match.group(1), match.group(2)
    api_url = f"https://api.fxtwitter.com/{username}/status/{tweet_id}"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(api_url)
            resp.raise_for_status()
            data = resp.json()

        tweet = data.get("tweet", {})
        author_name = tweet.get("author", {}).get("name", username)
        author_handle = tweet.get("author", {}).get("screen_name", username)
        text = tweet.get("text", "")
        created = tweet.get("created_at", "")

        # Build content from tweet text
        parts = [f"@{author_handle} ({author_name})"]
        if created:
            parts.append(f"Posted: {created}")
        parts.append("")
        parts.append(text)

        # Include quote tweet if present
        quote = tweet.get("quote")
        if quote:
            qt_author = quote.get("author", {}).get("screen_name", "")
            qt_text = quote.get("text", "")
            parts.append(f"\n--- Quoted @{qt_author} ---\n{qt_text}")

        # If the tweet has video, also try to transcribe it
        media = tweet.get("media", {})
        videos = media.get("videos") or []
        if videos or media.get("video"):
            transcript = await _download_and_transcribe(url, tmp_dir, whisper_model)
            if transcript:
                parts.append(f"\n--- Video Transcript ---\n{transcript}")

        title = f"@{author_handle}: {text[:80]}{'...' if len(text) > 80 else ''}"

        return ExtractedContent(
            url=url,
            source_type="twitter",
            title=title,
            content_text="\n".join(parts),
            metadata={
                "author": author_handle,
                "likes": tweet.get("likes", 0),
                "retweets": tweet.get("retweets", 0),
                "replies": tweet.get("replies", 0),
            },
        )

    except Exception as e:
        logger.warning("fxtwitter extraction failed for %s: %s, trying yt-dlp", url, e)
        return await _extract_media(url, "twitter", tmp_dir, whisper_model)


async def _extract_reddit(
    url: str, tmp_dir: str, whisper_model: str
) -> ExtractedContent:
    """Extract Reddit post content using Reddit's JSON API, with yt-dlp fallback for video."""
    import re

    # Normalize URL: strip query params, ensure trailing slash
    clean_url = re.split(r"[?#]", url)[0].rstrip("/") + "/"

    # Use old.reddit.com which is more reliable for JSON API
    json_url = clean_url.replace("www.reddit.com", "old.reddit.com").replace("://reddit.com", "://old.reddit.com") + ".json"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(
                json_url,
                headers={"User-Agent": "Nexus/2.0"},
            )
            resp.raise_for_status()
            data = resp.json()

        # Reddit returns a list: [post_listing, comments_listing]
        if not isinstance(data, list) or len(data) < 1:
            return await _extract_media(url, "reddit", tmp_dir, whisper_model)

        post_data = data[0]["data"]["children"][0]["data"]
        title = post_data.get("title", "")
        selftext = post_data.get("selftext", "")
        author = post_data.get("author", "")
        subreddit = post_data.get("subreddit_name_prefixed", "")
        score = post_data.get("score", 0)

        parts = [f"{subreddit} - u/{author}"]
        parts.append(f"Score: {score}")
        parts.append(f"\n{title}")

        if selftext:
            parts.append(f"\n{selftext}")

        # If it's a link post (not self post), include the linked URL
        if not post_data.get("is_self") and post_data.get("url_overridden_by_dest"):
            parts.append(f"\nLinked: {post_data['url_overridden_by_dest']}")

        # If it's a video post, try to transcribe
        is_video = post_data.get("is_video", False)
        if is_video:
            transcript = await _download_and_transcribe(url, tmp_dir, whisper_model)
            if transcript:
                parts.append(f"\n--- Video Transcript ---\n{transcript}")

        # Include top comments
        if len(data) > 1:
            comments = data[1]["data"]["children"]
            top_comments = []
            for c in comments[:5]:
                if c["kind"] != "t1":
                    continue
                cdata = c["data"]
                cbody = cdata.get("body", "")
                cauthor = cdata.get("author", "")
                cscore = cdata.get("score", 0)
                if cbody:
                    top_comments.append(f"u/{cauthor} ({cscore} pts): {cbody[:500]}")

            if top_comments:
                parts.append("\n--- Top Comments ---")
                parts.extend(top_comments)

        return ExtractedContent(
            url=url,
            source_type="reddit",
            title=title,
            content_text="\n".join(parts),
            metadata={
                "author": author,
                "subreddit": subreddit,
                "score": score,
            },
        )

    except Exception as e:
        logger.warning("Reddit JSON extraction failed for %s: %s, trying yt-dlp", url, e)
        return await _extract_media(url, "reddit", tmp_dir, whisper_model)


async def _extract_pdf(url: str, tmp_dir: str) -> ExtractedContent:
    """Download a PDF and extract text from it using PyMuPDF."""
    os.makedirs(tmp_dir, exist_ok=True)
    pdf_path = os.path.join(tmp_dir, f"pdf_{id(url)}.pdf")

    try:
        # Download the PDF
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()

            # Verify it's actually a PDF (check content-type or magic bytes)
            content_type = resp.headers.get("content-type", "")
            if b"%PDF" not in resp.content[:10] and "pdf" not in content_type.lower():
                # Not a PDF — fall back to article extraction
                return await _extract_article(url)

            with open(pdf_path, "wb") as f:
                f.write(resp.content)

        # Extract text with PyMuPDF
        loop = asyncio.get_running_loop()
        title, text = await loop.run_in_executor(None, _pymupdf_extract_sync, pdf_path)

        if not text or not text.strip():
            return ExtractedContent(
                url=url, source_type="pdf", title="", content_text="",
                success=False, error="PDF contained no extractable text",
            )

        return ExtractedContent(
            url=url,
            source_type="pdf",
            title=title or "",
            content_text=text,
        )

    except Exception as e:
        logger.exception("PDF extraction failed for %s", url)
        return ExtractedContent(
            url=url, source_type="pdf", title="", content_text="",
            success=False, error=str(e),
        )
    finally:
        if os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass


def _pymupdf_extract_sync(pdf_path: str) -> tuple[str, str]:
    """Extract title and text from a PDF file."""
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    title = doc.metadata.get("title", "") if doc.metadata else ""

    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()

    return title, "\n".join(pages)


async def _extract_article(url: str) -> ExtractedContent:
    """Extract content from article/blog URLs using trafilatura."""
    try:
        import trafilatura

        loop = asyncio.get_running_loop()

        # Try trafilatura directly (it handles fetching)
        text = await loop.run_in_executor(None, _trafilatura_extract_sync, url)

        if text:
            # Try to get title
            downloaded = await loop.run_in_executor(None, trafilatura.fetch_url, url)
            metadata = None
            if downloaded:
                metadata = trafilatura.extract_metadata(downloaded)
            title = metadata.title if metadata and metadata.title else ""
            return ExtractedContent(
                url=url,
                source_type="article",
                title=title,
                content_text=text,
            )

        # Fallback: fetch with httpx and pass HTML to trafilatura
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            html = resp.text

        text = await loop.run_in_executor(
            None, trafilatura.extract, html,
        )

        if text:
            metadata = trafilatura.extract_metadata(html)
            title = metadata.title if metadata and metadata.title else ""
            return ExtractedContent(
                url=url, source_type="article", title=title, content_text=text,
            )

        return ExtractedContent(
            url=url, source_type="article", title="", content_text="",
            success=False, error="Could not extract text content",
        )

    except Exception as e:
        logger.exception("Article extraction failed for %s", url)
        return ExtractedContent(
            url=url, source_type="article", title="", content_text="",
            success=False, error=str(e),
        )


def _trafilatura_extract_sync(url: str) -> str | None:
    import trafilatura

    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        return trafilatura.extract(
            downloaded, include_tables=True, output_format="txt"
        )
    return None


async def extract_from_file(
    file_path: str, source_type: str, whisper_model: str = "base"
) -> ExtractedContent:
    """Extract content from a local file (voice message, audio, video)."""
    try:
        transcript = await transcribe(file_path, model_size=whisper_model)
        if transcript:
            return ExtractedContent(
                url=None,
                source_type=source_type,
                title=f"Direct {source_type}",
                content_text=transcript,
            )
        return ExtractedContent(
            url=None, source_type=source_type, title="", content_text="",
            success=False, error="Transcription returned empty result",
        )
    except Exception as e:
        logger.exception("File extraction failed for %s", file_path)
        return ExtractedContent(
            url=None, source_type=source_type, title="", content_text="",
            success=False, error=str(e),
        )
