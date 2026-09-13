from functools import lru_cache

from faster_whisper import WhisperModel

from app.config import settings


@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    return WhisperModel(settings.whisper_model_size, device="cpu", compute_type="int8")


def transcribe_audio(audio_path: str) -> str:
    model = get_model()
    segments, _ = model.transcribe(audio_path, beam_size=5)
    return " ".join(segment.text.strip() for segment in segments).strip()
