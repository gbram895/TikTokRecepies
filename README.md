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

## Deploying to an Oracle Cloud free VM

Oracle Cloud's **Always Free** tier includes an Ampere A1 (ARM) VM with up
to 4 OCPUs / 24GB RAM, free forever — genuinely enough headroom to run the
full pipeline (Whisper + OCR) with room to spare, unlike a memory-capped
free web-service plan. This repo includes `docker-compose.yml` + a
`Caddyfile` that run the app, Postgres, and an HTTPS reverse proxy as three
containers on that VM.

### 1. Create the VM

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com) (free; a card is
   required for identity verification but Always Free resources aren't
   billed).
2. **Compute → Instances → Create Instance**.
3. Under **Image and shape**: pick **Ubuntu 22.04** (or newer), and change
   the shape to **VM.Standard.A1.Flex** (Ampere/ARM, Always Free eligible)
   — set it to e.g. 2 OCPU / 12GB or the full 4 OCPU / 24GB.
4. Under **Networking**, either use the default VCN or create one; note the
   instance will get a public IP (assign a **reserved/static** public IP if
   offered, so it doesn't change on restart).
5. Add your SSH public key (or let Oracle generate a key pair for you and
   download it).
6. Create the instance. Note its public IP once it's running.

### 2. Open ports 80/443

Two firewalls need opening — Oracle's cloud-level one and the VM's own:

- **Cloud level**: your VCN's default **Security List** (Networking →
  Virtual Cloud Networks → your VCN → Security Lists → Default Security
  List) → **Add Ingress Rules** → source `0.0.0.0/0`, TCP, destination port
  `80`; repeat for port `443`.
- **On the VM** (Oracle's Ubuntu images ship with iptables pre-configured
  to drop unlisted inbound traffic):
  ```bash
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
  sudo netfilter-persistent save   # or: sudo apt install -y iptables-persistent
  ```

### 3. Install Docker and deploy

SSH into the VM (`ssh ubuntu@<VM_PUBLIC_IP>`), then:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER && newgrp docker

git clone https://github.com/gbram895/TikTokRecepies.git
cd TikTokRecepies

cp .env.example .env
nano .env   # set SECRET_KEY and POSTGRES_PASSWORD to real random values

docker compose up -d --build
```

That's it — `docker compose` builds the app image (installing `ffmpeg` +
`tesseract-ocr`), starts Postgres, and starts Caddy as a reverse proxy in
front of the app. `restart: unless-stopped` means all three containers
come back automatically if the VM reboots (as long as Docker itself is
enabled at boot: `sudo systemctl enable docker`, on by default after
installing via apt).

**Get a domain (recommended) for HTTPS:** point a domain's A record at the
VM's public IP (a free option: [duckdns.org](https://www.duckdns.org)),
then edit `Caddyfile` — replace `:80` with your domain — and
`docker compose restart caddy`. Caddy issues and renews a Let's Encrypt
certificate automatically from there. No domain yet? Leave `Caddyfile` as
`:80` and the app is reachable over plain HTTP at `http://<VM_PUBLIC_IP>`
in the meantime.

### Why this is faster than the earlier Render setup

- No memory ceiling to work around: `.env.example` defaults to
  `WHISPER_MODEL_SIZE=small` (noticeably more accurate than `tiny`) with
  **`ENABLE_OCR=true`** (on-screen text reading works), both of which had
  to be dialed back or disabled on Render's free 512MB plan.
- No cold starts / spin-down: the containers just run continuously (a real
  VM, not a scale-to-zero web service), so there's no 30-60s wake-up delay
  on the first request after a quiet period.
- `docker compose logs -f app` shows the same peak-memory-per-stage logging
  described above, if you ever want to check headroom.

### Alternative: Render

`render.yaml` is still in the repo if you'd rather use Render — see the
git history for the tuning notes that were needed to fit its free 512MB
plan (smaller Whisper model, capped video resolution, OCR disabled). The
Oracle Cloud VM above avoids all of that by simply having enough RAM.

## Limitations (MVP)

- TikTok can change its site/API at any time; if downloads start failing,
  upgrading `yt-dlp` (`pip install -U yt-dlp`) is usually the fix.
- Recipe extraction is heuristic, not AI-based (see "Accuracy tradeoff"
  above) — it does best on videos with clear spoken quantities, on-screen
  text (when `ENABLE_OCR=true`), or a written ingredient list in the
  caption; free-form rambling narration with no explicit measurements and
  no visible text may come back thin.
- On a memory-capped host (e.g. Render's free plan, see "Alternative:
  Render" above), `ENABLE_OCR` should stay off, so on-screen text cards
  without matching narration/caption won't be picked up there.
- OCR (when enabled) samples ~8 frames spread across the video, not every
  frame, so a very fast-cut recipe card on screen for only a fraction of a
  second between samples can be missed.
- Processing happens synchronously on the request (no background job
  queue), so the "Transcribe recipe" button can take 10-60 seconds
  depending on video length and instance size.
