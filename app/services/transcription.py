from functools import lru_cache

from faster_whisper import WhisperModel

from app.config import settings

# Segments Whisper is unsure contain speech at all (background music,
# sound effects, silence) get this probability high -- skip them instead
# of transcribing whatever it guessed.
_NO_SPEECH_PROB_THRESHOLD = 0.6

# Whisper tends to hallucinate repeated/garbled text over music or noise;
# those segments usually come back with very low average log-probability.
_MIN_AVG_LOGPROB = -1.0


@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    return WhisperModel(settings.whisper_model_size, device="cpu", compute_type="int8")


def transcribe_audio(media_path: str) -> str:
    """Transcribe spoken narration only.

    Uses Silero VAD (bundled with faster-whisper) to skip music/silence
    stretches, and drops any segment Whisper itself flags as low-confidence
    or probably-not-speech, since those are almost always hallucinated
    lyrics/noise rather than real narration.
    """
    model = get_model()
    segments, _ = model.transcribe(
        media_path,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,
    )

    kept: list[str] = []
    for segment in segments:
        if segment.no_speech_prob > _NO_SPEECH_PROB_THRESHOLD:
            continue
        if segment.avg_logprob < _MIN_AVG_LOGPROB:
            continue
        text = segment.text.strip()
        if text:
            kept.append(text)
    return " ".join(kept).strip()
