import os
import tempfile
from dataclasses import dataclass

import yt_dlp


@dataclass
class DownloadedVideo:
    audio_path: str
    title: str
    description: str


def download_audio(tiktok_url: str) -> DownloadedVideo:
    """Download a TikTok video's audio track and grab its title/caption.

    Caller is responsible for deleting the returned audio file (and its
    parent temp directory) once done with it.
    """
    out_dir = tempfile.mkdtemp(prefix="tiktok_")
    out_template = os.path.join(out_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "noprogress": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(tiktok_url, download=True)
        video_id = info["id"]

    audio_path = os.path.join(out_dir, f"{video_id}.mp3")
    if not os.path.exists(audio_path):
        raise RuntimeError("Downloaded the video but could not extract its audio track.")

    return DownloadedVideo(
        audio_path=audio_path,
        title=info.get("title") or "",
        description=info.get("description") or "",
    )
