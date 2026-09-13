import os
import tempfile
from dataclasses import dataclass

import yt_dlp


@dataclass
class DownloadedVideo:
    video_path: str
    title: str
    description: str
    duration: float | None


def download_video(tiktok_url: str) -> DownloadedVideo:
    """Download a TikTok video (video+audio muxed) and grab its title/caption.

    We keep the actual video file (rather than extracting audio-only) because
    the recipe extractor also OCRs a few frames for on-screen text overlays
    (ingredient cards, step captions) that a lot of recipe TikToks rely on
    instead of, or in addition to, narration.

    Caller is responsible for deleting the returned video file (and its
    parent temp directory) once done with it.
    """
    out_dir = tempfile.mkdtemp(prefix="tiktok_")
    out_template = os.path.join(out_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "mp4/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "noprogress": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(tiktok_url, download=True)
        video_path = ydl.prepare_filename(info)

    if not os.path.exists(video_path):
        raise RuntimeError("Couldn't download that TikTok video.")

    return DownloadedVideo(
        video_path=video_path,
        title=info.get("title") or "",
        description=info.get("description") or "",
        duration=info.get("duration"),
    )
