# OH ALLEGEDLY — automated newsroom

A self-updating news site that turns your YouTube channel into a newsroom.

```
 YouTube channel ──► every 20 min ──► new upload / ended livestream?
                                          │
                                   fetch transcript
                                          │
                            Claude writes the article
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
- No server, no database: everything runs free on GitHub Actions + GitHub Pages. You only pay for Claude API usage (roughly a few US cents per article).

---

## Setup (about 15 minutes)

### 1. Put the code on GitHub
Create a new repository (e.g. `oh-allegedly`) and upload everything in this folder, including the hidden `.github` folder.

### 2. Configure `config.yaml`
- `channel_ids` — your channel ID (starts with `UC…`). Find it at **youtube.com/account_advanced**.
- `base_url` — `https://YOUR-USERNAME.github.io/oh-allegedly` (or your own domain later).
- `mode` — `publish` (fully automatic) or `draft` (you approve each story). See *Legal safety* below.

### 3. Add your secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Required? | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Yes** | console.anthropic.com → API keys |
| `YOUTUBE_API_KEY` | Recommended | console.cloud.google.com → enable *YouTube Data API v3* → Credentials → API key. Enables the LIVE banner, Shorts detection and stream recaps. Uses ~1 quota unit per run (free limit is 10,000/day). |
| `TRANSCRIPT_PROXY_URL` | Only if needed | See *Transcripts* below. |

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
2. **YouTube sometimes blocks cloud servers** (including GitHub) from fetching captions. If the Actions log keeps showing `no transcript yet: … blocked …`, get a cheap rotating *residential* proxy (e.g. Webshare "Residential", a few dollars a month) and save its URL as the `TRANSCRIPT_PROXY_URL` secret, e.g. `http://user:pass@p.webshare.io:80`.

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
export ANTHROPIC_API_KEY=sk-ant-...      # Windows: set ANTHROPIC_API_KEY=...
python -m pipeline.run                   # check channel, write stories, build
python -m pipeline.run --build           # rebuild only
python -m http.server -d _site 8000      # preview at http://localhost:8000
```

## Files
```
config.yaml              settings
pipeline/youtube.py      channel feed, live status, transcripts
pipeline/writer.py       Claude prompt → article / daily briefing
pipeline/run.py          the loop (state in data/state.json)
pipeline/build.py        static site generator → _site/
templates/, static/      the design
content/articles/        published stories (JSON)   content/drafts/  awaiting review
.github/workflows/       the 20-minute schedule + deploy
```
