# TikTok Recipe Transcriber

Paste a TikTok recipe video URL and get back a clean, structured recipe:
title, ingredients, and numbered steps. Requires an account (email +
password login).

**No paid AI APIs.** Everything runs locally/for free — there's no
per-request bill, no API key to fund, nothing that can surprise you with a
usage invoice.

## How it works

Recipe TikToks convey the recipe three different ways, and a given video
might use only one of them, so this app pulls from all three:

1. **Download** &mdash; [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) downloads
   the video (plus its caption/title) from the TikTok URL. Free, no API key.
2. **Transcribe narration** &mdash; [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper)
   runs entirely on the server's CPU to turn spoken audio into text. It uses
   voice-activity detection and drops any segment Whisper itself flags as
   low-confidence or probably-not-speech, so a music-only stretch doesn't
   get transcribed into hallucinated lyrics/gibberish. Free, no external
   API, no per-minute charge.
3. **Read on-screen text** &mdash; a lot of recipe TikToks show the actual
   recipe as text cards with little or no narration. `app/services/ocr.py`
   samples a handful of frames spread across the video and runs them
   through Tesseract (local OCR, `pytesseract`) to pull that text out. Free,
   runs on-device.
4. **Read the caption** &mdash; the video's caption/description, fetched
   alongside the download in step 1, often already has the ingredient list.
5. **Structure** &mdash; a small rule-based parser
   (`app/services/recipe_extractor.py`) combines all three text sources:
   if the caption or on-screen text already has an explicit
   `Ingredients:` / `Instructions:` list, that's used directly; otherwise it
   scans everything with regex/keyword heuristics — quantity + unit phrases
   ("2 cups flour", "a pinch of salt") become ingredients, sentences with
   cooking verbs ("preheat", "whisk", "bake") become steps. Pure Python, no
   network call, free.
6. The recipe is saved to the signed-in user's account in Postgres.

Stack: FastAPI + Jinja2 templates (server-rendered, no separate frontend
build), SQLAlchemy, cookie-based sessions, bcrypt password hashing.

### Accuracy tradeoff

Because step 5 is a heuristic parser instead of an LLM, it's not as sharp
as one on messy, rambling narration — it works best when a video does at
least one of: speaks quantities clearly ("two cups of flour"), shows the
recipe as on-screen text, or has a caption with a written ingredient list.
If you outgrow this and want LLM-quality extraction, swap `extract_recipe()`
in `app/services/recipe_extractor.py` for a call to an AI API — that's the
only file that would need to change.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

You'll also need `ffmpeg` and `tesseract-ocr` installed locally
(`brew install ffmpeg tesseract` / `apt install ffmpeg tesseract-ocr`).

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
  `ffmpeg` and `tesseract-ocr` so audio extraction, transcription, and
  on-screen text OCR all work), and
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
  run at $0/month. Free-tier instances are capped at 512MB RAM and spin
  down when idle, so several things here are deliberately tuned to fit
  that ceiling: `WHISPER_MODEL_SIZE` defaults to `tiny` (smallest model),
  downloaded video is capped at 480p, Whisper runs single-threaded
  (`cpu_threads=1`), and **`ENABLE_OCR` is set to `false`** on the free
  blueprint. On-screen text OCR (`app/services/ocr.py`) spawns an `ffmpeg`
  frame-extraction subprocess and a `tesseract` subprocess per video on top
  of the already-resident Whisper model, and that combination is what was
  pushing the service over 512MB and getting restarted ("exceeded its
  memory limit" in the Render dashboard). With OCR off you lose on-screen
  text reading but keep narration + caption parsing, which is enough to
  run reliably on the free plan.
  - The service logs peak memory (`peak RSS after <stage>: ... MB`) after
    download, transcription, and OCR (when enabled) — check the Render
    **Logs** tab if you hit the memory limit again, it'll show which stage
    tipped it over.
  - To get OCR back, set `ENABLE_OCR=true` in the service's environment
    variables **and** upgrade the web service to a plan with more RAM
    (in `render.yaml` or the dashboard) — turning it on without more RAM
    will very likely reproduce the crash.
  - `WHISPER_MODEL_SIZE` can similarly be bumped to `base`/`small`/`medium`
    for better accuracy, but each step up roughly doubles memory use —
    only go past `tiny` alongside a bigger plan too.
- The Render free Postgres plan expires after 90 days of inactivity-free
  use per Render's current policy &mdash; fine to start with, upgrade later
  if this becomes a real product.

## Limitations (MVP)

- TikTok can change its site/API at any time; if downloads start failing,
  upgrading `yt-dlp` (`pip install -U yt-dlp`) is usually the fix.
- Recipe extraction is heuristic, not AI-based (see "Accuracy tradeoff"
  above) — it does best on videos with clear spoken quantities, on-screen
  text (when `ENABLE_OCR=true`), or a written ingredient list in the
  caption; free-form rambling narration with no explicit measurements and
  no visible text may come back thin.
- On the free Render plan, `ENABLE_OCR` is off (see "Deploying to Render"
  above), so on-screen text cards without matching narration/caption won't
  be picked up unless you enable OCR and size up the plan.
- OCR (when enabled) samples ~8 frames spread across the video, not every
  frame, so a very fast-cut recipe card on screen for only a fraction of a
  second between samples can be missed.
- Processing happens synchronously on the request (no background job
  queue), so the "Transcribe recipe" button can take 10-60 seconds
  depending on video length and instance size.
