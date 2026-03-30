import asyncio
import logging

logger = logging.getLogger(__name__)

_model = None
_model_lock = asyncio.Lock()


def _get_model_sync(model_size: str):
    """Load the faster-whisper model (blocking). Called inside executor."""
    from faster_whisper import WhisperModel

    logger.info("Loading Whisper model '%s' (first-time download may take a moment)...", model_size)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    logger.info("Whisper model loaded")
    return model


async def _ensure_model(model_size: str):
    global _model
    if _model is None:
        async with _model_lock:
            if _model is None:
                loop = asyncio.get_running_loop()
                _model = await loop.run_in_executor(None, _get_model_sync, model_size)
    return _model


def _transcribe_sync(model, audio_path: str) -> str:
    """Run transcription (blocking CPU-bound work)."""
    segments, info = model.transcribe(audio_path, beam_size=5)
    logger.info("Transcribing %.1fs of %s audio", info.duration, info.language)
    text_parts = []
    for segment in segments:
        text_parts.append(segment.text.strip())
    return " ".join(text_parts)


async def transcribe(audio_path: str, model_size: str = "base") -> str:
    """Transcribe an audio file to text using faster-whisper.

    Runs the CPU-bound work in a thread executor to avoid blocking the event loop.
    """
    model = await _ensure_model(model_size)
    loop = asyncio.get_running_loop()
    text = await loop.run_in_executor(None, _transcribe_sync, model, audio_path)
    return text
