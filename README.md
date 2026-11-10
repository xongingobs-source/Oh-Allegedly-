# OH ALLEGEDLY — automated newsroom

A self-updating news site that turns your YouTube channel into a newsroom.

```
 YouTube channel ──► every 20 min ──► new upload / ended livestream?
                                          │
                                   fetch transcript
                                          │
                     FREE AI writes the article (GitHub Models)
                     (headline, standfirst, "The Receipts",
                      clickable timeline, body, category)
                                          │
                       publish ─── or ─── hold as draft (high legal risk)
                                          │
                     rebuild static site ──► GitHub Pages (free hosting)
```

**What you get**
- Breaking-news ticker, LIVE NOW banner while you stream, "Breaking" badges on fresh stories
- Every upload and finished livestream becomes a full article with the video embedded
- "Jump to the moment" timestamps that seek the embedded player
- **The Daily Tea** — an automatic daily briefing rounding up the last 24 hours
- Sections, search (press `/`), RSS feed, sitemap, social share cards, Google News-friendly markup
- **100% free**: no server, no database, no API bills. It runs on GitHub Actions + GitHub Pages, and the stories are written by GitHub Models' free AI using your repo's built-in token: no key, no card.

---

## Setup (about 15 minutes)

### 1. Put the code on GitHub
Create a new repository (e.g. `oh-allegedly`) and upload everything in this folder, including the hidden `.github` folder.

### 2. Configure `config.yaml`
- `channel_ids` — your channel ID (starts with `UC…`). Find it at **youtube.com/account_advanced**.
- `base_url` — `https://YOUR-USERNAME.github.io/oh-allegedly` (or your own domain later).
- `mode` — `publish` (fully automatic) or `draft` (you approve each story). See *Legal safety* below.

### 3. (Optional) Free extras
Nothing is required: the free AI writer works out of the box. Optional free secrets, added under repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | What it adds | Where to get it (free, no card) |
|---|---|---|
| `YOUTUBE_API_KEY` | LIVE banner, Shorts filtering, stream recaps | console.cloud.google.com → enable *YouTube Data API v3* → Credentials → API key |
| `GEMINI_API_KEY` | Backup AI writer if GitHub's free daily limit runs out | aistudio.google.com → Get API key |

**Free limits to know:** GitHub Models' free tier allows roughly 150 AI requests a day. A normal video uses 1–4, a long stream up to 7, so `max_articles_per_run: 3` keeps you comfortably inside it. If the AI is ever unavailable, the robot falls back to a simple no-AI "new video" post so the site keeps updating.

### 4. Switch on hosting
Repo → **Settings → Pages → Source: GitHub Actions**.

### 5. Go
Repo → **Actions → Newsroom robot → Run workflow**. After a minute or two your site is live at the URL in step 2. From then on it runs itself every 20 minutes.

> The repo ships with 7 **fictional sample stories** so you can see the design. Remove them before launch:
> `python scripts/seed_demo.py --clear` then commit.

---

## Transcripts — the one thing to know
Transcripts come from YouTube's captions (auto-captions are fine). Two gotchas:

1. **Livestreams**: captions appear a few hours after the stream ends. The robot keeps retrying (up to 12 runs ≈ 4 hours) and writes a *Livestream Recap* once they're ready.
2. **YouTube sometimes blocks cloud servers** (including GitHub) from fetching captions. If the Actions log keeps showing `no transcript yet: … blocked …`, the free fix is to run the robot from your own computer instead (home internet is rarely blocked), see below. The paid fix is a residential proxy saved as the `TRANSCRIPT_PROXY_URL` secret.

Alternative: run it on your own computer/server instead of GitHub (home internet is rarely blocked): `python -m pipeline.run` on a schedule (cron / Task Scheduler), then deploy `_site/` anywhere (Netlify, Cloudflare Pages, any host).

---

## Legal safety (please read — it's in the name)
Auto-publishing stories about real people carries defamation risk. The newsroom is built to keep you safer:
- The writing prompt forces attribution ("allegedly", "according to the video") and bans stating allegations as fact or quoting anything not in the transcript.
- Every story self-rates `legal_risk`. **High-risk stories always go to `content/drafts/`, even in publish mode.** Review them, then move the file to `content/articles/` and commit — the site rebuilds automatically.
- Every page links the source video and carries a disclaimer.
- For extra caution set `mode: draft` and approve everything.

This is not legal advice; if the channel covers serious accusations, a quick chat with a media lawyer is worth it.

---

## Everyday use
| I want to… | Do this |
|---|---|
| Refresh right now | Actions → Newsroom robot → Run workflow |
| Write up one specific video | Run workflow and paste the video ID |
| Fix a typo in a story | Edit `content/articles/<slug>.json` on GitHub → commit (site rebuilds) |
| Kill a story | Delete its file in `content/articles/` |
| Re-write a story | Delete it, then Run workflow with its video ID |
| Change look & feel | `static/style.css` and `templates/` |
| Also cover other creators | Add their channel IDs to `extra_channel_ids` (stories credit them) |

## Run locally
```bash
pip install -r requirements.txt
export GITHUB_TOKEN=github_pat_...      # free: github.com/settings/tokens → fine-grained → Models: Read
python -m pipeline.run                   # check channel, write stories, build
python -m pipeline.run --build           # rebuild only
python -m http.server -d _site 8000      # preview at http://localhost:8000
```

## Files
```
config.yaml              settings
pipeline/youtube.py      channel feed, live status, transcripts
pipeline/writer.py       free AI (GitHub Models / Gemini) → article / daily briefing
pipeline/run.py          the loop (state in data/state.json)
pipeline/build.py        static site generator → _site/
templates/, static/      the design
content/articles/        published stories (JSON)   content/drafts/  awaiting review
.github/workflows/       the 20-minute schedule + deploy
```
