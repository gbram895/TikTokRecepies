# TikTok Recipe Transcriber

Paste a TikTok recipe video URL and get back a clean, structured recipe:
title, ingredients, and numbered steps. Requires an account (email +
password login).

**No paid AI APIs.** Everything runs locally/for free — there's no
per-request bill, no API key to fund, nothing that can surprise you with a
usage invoice.

## How it works

1. **Download** &mdash; [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) pulls the
   audio track (and the video's caption/title) from the TikTok URL. Free,
   no API key.
2. **Transcribe** &mdash; [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper)
   runs entirely on the server's CPU to turn the audio into text. Free, no
   external API, no per-minute charge.
3. **Structure** &mdash; a small rule-based parser (`app/services/recipe_extractor.py`)
   scans the transcript and caption with regex/keyword heuristics: lines
   with quantities + units ("2 cups flour", "a pinch of salt") become
   ingredients, sentences with cooking verbs ("preheat", "whisk", "bake")
   become steps, and if the caption already has an explicit
   `Ingredients:` / `Instructions:` list (common on recipe TikToks), that's
   used directly. Pure Python, no network call, free.
4. The recipe is saved to the signed-in user's account in Postgres.

Stack: FastAPI + Jinja2 templates (server-rendered, no separate frontend
build), SQLAlchemy, cookie-based sessions, bcrypt password hashing.

### Accuracy tradeoff

Because step 3 is a heuristic parser instead of an LLM, it's not as sharp
as one on messy, rambling narration — it works best when a video either
speaks quantities clearly ("two cups of flour", "a pinch of salt") or has
a caption with a written ingredient list. If you outgrow this and want
LLM-quality extraction, swap `extract_recipe()` in
`app/services/recipe_extractor.py` for a call to an AI API — that's the
only file that would need to change.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

You'll also need `ffmpeg` installed locally (`brew install ffmpeg` /
`apt install ffmpeg`).

```bash
cp .env.example .env
```

The defaults in `.env.example` work out of the box — no keys required.

Run it:

```bash
uvicorn app.main:app --reload
```

Visit http://localhost:8000. Local dev defaults to a SQLite file
(`app.db`) so there's no database to set up.

## Deploying to Render

This repo includes a `render.yaml` Blueprint that provisions:

- a **web service** (built from the included `Dockerfile`, which installs
  `ffmpeg` so audio extraction/transcription works), and
- a **Postgres database**, wired up to the web service automatically via
  `DATABASE_URL`.

Steps:

1. Push this repo to GitHub.
2. In the Render dashboard: **New +** &rarr; **Blueprint**, point it at this
   repo.
3. Render reads `render.yaml`, creates both services, and auto-generates
   `SECRET_KEY` for you. No other secrets/API keys are needed.
4. Deploy. First boot will take a little longer than usual while
   `faster-whisper` downloads its model weights (a one-time download,
   cached after that).

Notes / tuning:

- The blueprint uses Render's **free** web + database plans, so this can
  run at $0/month. Whisper transcription is CPU-bound and free-tier
  instances have limited RAM/CPU and spin down when idle, so expect slower
  cold starts and transcriptions (well under a minute of audio is fine).
  Upgrade the web service to the `starter` plan in `render.yaml` (or in the
  dashboard) if you want consistent performance — that's the only paid
  piece in this whole stack, and it's optional.
- `WHISPER_MODEL_SIZE` defaults to `base` (good speed/accuracy tradeoff for
  short-form video). Bump it to `small` or `medium` for better accuracy at
  the cost of speed/memory, in the service's environment variables.
- The Render free Postgres plan expires after 90 days of inactivity-free
  use per Render's current policy &mdash; fine to start with, upgrade later
  if this becomes a real product.

## Limitations (MVP)

- TikTok can change its site/API at any time; if downloads start failing,
  upgrading `yt-dlp` (`pip install -U yt-dlp`) is usually the fix.
- Recipe extraction is heuristic, not AI-based (see "Accuracy tradeoff"
  above) — it does best on videos with clear spoken quantities or a
  written ingredient list in the caption; free-form rambling narration
  with no explicit measurements may come back thin.
- Processing happens synchronously on the request (no background job
  queue), so the "Transcribe recipe" button can take 10-60 seconds
  depending on video length and instance size.
