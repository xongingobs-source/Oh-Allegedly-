"""The newsroom loop.

    python -m pipeline.run            # check YouTube, write new stories, rebuild site
    python -m pipeline.run --build    # just rebuild the site from existing content
    python -m pipeline.run --video VIDEO_ID   # force-write one specific video

Safe to run as often as you like: state is kept in data/state.json so each
video is only written up once.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import youtube as yt
from .build import build_site, load_articles
from .writer import dumps, slugify, write_article, write_digest

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "state.json"
LIVE_FILE = ROOT / "data" / "live.json"
ARTICLES = ROOT / "content" / "articles"
DRAFTS = ROOT / "content" / "drafts"
DIGESTS = ROOT / "content" / "digests"
MAX_TRANSCRIPT_ATTEMPTS = 12  # livestream captions can take a few hours to appear


def log(*a):
    print("[newsroom]", *a, flush=True)


def load_cfg() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"videos": {}, "last_run": None}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(dumps(state))


def unique_slug(base: str) -> str:
    slug, n = base, 2
    while (ARTICLES / f"{slug}.json").exists() or (DRAFTS / f"{slug}.json").exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def gather_videos(cfg: dict) -> list[dict]:
    ids = list(cfg["youtube"]["channel_ids"]) + list(cfg["youtube"].get("extra_channel_ids") or [])
    videos = []
    for cid in ids:
        if not cid or "xxxx" in cid:
            log(f"⚠ skipping placeholder channel id '{cid}' — set it in config.yaml")
            continue
        try:
            feed = yt.fetch_channel_feed(cid)
            for v in feed:
                v["is_own_channel"] = cid in cfg["youtube"]["channel_ids"]
            videos += feed
            log(f"feed {cid}: {len(feed)} videos")
        except Exception as e:  # noqa: BLE001
            log(f"✗ feed {cid} failed: {e}")
    return yt.enrich_with_api(videos)


def process(cfg: dict, state: dict, only_video: str | None = None) -> int:
    videos = gather_videos(cfg)
    if only_video:
        videos = [v for v in videos if v["video_id"] == only_video] or [{
            "video_id": only_video, "title": only_video, "published": None, "description": "",
            "channel_name": cfg["site"]["name"], "channel_id": "", "url": f"https://www.youtube.com/watch?v={only_video}",
            "thumbnail": f"https://i.ytimg.com/vi/{only_video}/hqdefault.jpg", "is_short": False,
            "live_status": "none", "is_own_channel": True}]
        videos = yt.enrich_with_api(videos)
        state["videos"].pop(only_video, None)

    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg["youtube"]["backfill_days"])
    live_now, written = [], 0
    budget = cfg["newsroom"]["max_articles_per_run"]

    for v in sorted(videos, key=lambda x: x.get("published") or "", reverse=True):
        vid = v["video_id"]
        rec = state["videos"].setdefault(vid, {"status": "new", "attempts": 0,
                                               "first_seen": datetime.now(timezone.utc).isoformat()})
        rec["title"] = v["title"]

        # ── live & upcoming streams go on the LIVE banner, article comes after it ends
        if v["live_status"] in ("live", "upcoming"):
            live_now.append({k: v.get(k) for k in ("video_id", "title", "url", "thumbnail", "channel_name",
                                                    "live_status", "scheduled_start", "concurrent_viewers")})
            rec["status"] = "live"
            continue

        if rec["status"] in ("done", "skipped", "failed"):
            continue
        if not only_video and yt.parse_time(v.get("published")) < cutoff:
            rec["status"] = "skipped"; rec["reason"] = "older than backfill window"
            continue
        if cfg["youtube"]["skip_shorts"] and v.get("is_short") and not only_video:
            rec["status"] = "skipped"; rec["reason"] = "short"
            continue
        if written >= budget:
            log(f"budget reached; '{v['title']}' waits for next run")
            continue

        # ── transcript
        try:
            segs = yt.fetch_transcript(vid)
        except yt.TranscriptUnavailable as e:
            rec["attempts"] += 1
            rec["status"] = "failed" if rec["attempts"] >= MAX_TRANSCRIPT_ATTEMPTS else "pending"
            rec["reason"] = f"no transcript yet: {str(e)[:160]}"
            log(f"… no transcript for {vid} (attempt {rec['attempts']})")
            continue

        # ── write
        try:
            log(f"✎ writing: {v['title']}")
            art = write_article(v, yt.transcript_to_text(segs), cfg)
        except Exception as e:  # noqa: BLE001
            rec["attempts"] += 1
            rec["status"] = "pending"; rec["reason"] = f"writer error: {e}"
            log(f"✗ writer failed for {vid}: {e}")
            continue

        slug = unique_slug(slugify(art["headline"]))
        art.update({
            "slug": slug,
            "video_id": vid,
            "video_url": v["url"],
            "video_title": v["title"],
            "thumbnail": v["thumbnail"],
            "source_channel": v["channel_name"],
            "is_own_channel": v.get("is_own_channel", True),
            "was_livestream": bool(v.get("was_livestream")),
            "published": v.get("actual_end") or v.get("published") or datetime.now(timezone.utc).isoformat(),
            "updated": datetime.now(timezone.utc).isoformat(),
            "duration": v.get("duration"),
        })
        to_drafts = cfg["newsroom"]["mode"] == "draft" or art.get("legal_risk") == "high"
        folder = DRAFTS if to_drafts else ARTICLES
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{slug}.json").write_text(dumps(art))
        rec.update(status="done", article_slug=slug, location="drafts" if to_drafts else "live")
        written += 1
        log(f"✓ {'DRAFT (needs review)' if to_drafts else 'PUBLISHED'}: {slug}")

    LIVE_FILE.write_text(dumps({"updated": datetime.now(timezone.utc).isoformat(), "streams": live_now}))
    return written


def maybe_write_digest(cfg: dict):
    """Once per day, write a 'Daily Tea' briefing of the last 24h."""
    tz_today = datetime.now(timezone.utc).date().isoformat()
    path = DIGESTS / f"{tz_today}.json"
    if path.exists():
        return
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = [a for a in load_articles(ARTICLES) if yt.parse_time(a["published"]) >= since and not a.get("demo")]
    if len(recent) < 2:
        return
    try:
        d = write_digest(recent, cfg)
        d["date"] = tz_today
        DIGESTS.mkdir(parents=True, exist_ok=True)
        path.write_text(dumps(d))
        log("✓ daily briefing written")
    except Exception as e:  # noqa: BLE001
        log(f"✗ digest failed: {e}")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--build", action="store_true", help="only rebuild the site")
    p.add_argument("--video", help="force-write one video id")
    args = p.parse_args(argv)
    cfg = load_cfg()

    if not args.build:
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            log("✗ ANTHROPIC_API_KEY not set — run with --build to only rebuild"); sys.exit(1)
        state = load_state()
        n = process(cfg, state, args.video)
        save_state(state)
        log(f"{n} new stor{'y' if n == 1 else 'ies'}")
        maybe_write_digest(cfg)

    build_site(cfg, ROOT)


if __name__ == "__main__":
    main()
