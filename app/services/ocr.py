"""Pull on-screen text (ingredient cards, step captions, etc.) off a TikTok
video using local OCR. A lot of recipe TikToks show the actual recipe as
text overlays with little or no narration, so the transcript alone misses
them entirely. Runs Tesseract locally -- free, no API calls.
"""

import os
import re
import subprocess
import tempfile

import pytesseract
from PIL import Image

_MAX_FRAMES = 12
_MIN_INTERVAL_SECONDS = 1.0
_DEFAULT_DURATION = 18.0  # assume ~18s of interesting content if unknown


def extract_onscreen_text(video_path: str, duration: float | None = None) -> str:
    interval = max(_MIN_INTERVAL_SECONDS, (duration or _DEFAULT_DURATION) / _MAX_FRAMES)

    frame_dir = tempfile.mkdtemp(prefix="frames_")
    frame_pattern = os.path.join(frame_dir, "frame_%03d.jpg")

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", video_path,
                "-vf", f"fps=1/{interval},scale='min(720,iw)':-2",
                "-frames:v", str(_MAX_FRAMES),
                "-qscale:v", "4",
                frame_pattern,
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )

        seen_lines: dict[str, None] = {}
        for name in sorted(os.listdir(frame_dir)):
            frame_path = os.path.join(frame_dir, name)
            try:
                with Image.open(frame_path) as image:
                    text = pytesseract.image_to_string(image, config="--psm 6")
            except Exception:
                continue
            for raw_line in text.splitlines():
                line = re.sub(r'\s+', ' ', raw_line).strip(" -•*|")
                # Single/double-character OCR noise isn't useful and just
                # clutters the parser's input.
                if len(line) >= 3:
                    seen_lines.setdefault(line, None)
        return "\n".join(seen_lines.keys())
    except (subprocess.SubprocessError, OSError):
        # OCR is a bonus signal -- if ffmpeg/tesseract aren't cooperating,
        # fall back to whatever the transcript/caption gave us.
        return ""
    finally:
        for name in os.listdir(frame_dir):
            try:
                os.remove(os.path.join(frame_dir, name))
            except OSError:
                pass
        try:
            os.rmdir(frame_dir)
        except OSError:
            pass
