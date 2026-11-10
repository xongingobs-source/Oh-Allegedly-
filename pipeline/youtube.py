"""Everything that talks to YouTube: channel feeds, live status, transcripts."""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
API_URL = "https://www.googleapis.com/youtube/v3/videos"
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
UA = {"User-Agent": "Mozilla/5.0 (OhAllegedlyNewsroom/1.0)"}


def fetch_channel_feed(channel_id: str) -> list[dict]:
    """Latest ~15 uploads, premieres and streams for a channel. No API key needed."""
    r = requests.get(FEED_URL.format(cid=channel_id), headers=UA, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    channel_name = root.findtext("a:title", default="", namespaces=NS)
    videos = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", namespaces=NS)
        link = e.find("a:link", NS)
        href = link.get("href") if link is not None else f"https://www.youtube.com/watch?v={vid}"
        group = e.find("media:group", NS)
        desc = group.findtext("media:description", default="", namespaces=NS) if group is not None else ""
        videos.append({
            "video_id": vid,
            "title": e.findtext("a:title", default="", namespaces=NS),
            "published": e.findtext("a:published", namespaces=NS),
            "description": desc,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "is_short": "/shorts/" in href,
            "live_status": "none",  # refined by enrich_with_api()
        })
    return videos


def _iso_duration_seconds(d: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    days, h, mi, s = (int(x or 0) for x in m.groups())
    return days * 86400 + h * 3600 + mi * 60 + s


def enrich_with_api(videos: list[dict]) -> list[dict]:
    """If YOUTUBE_API_KEY is set, add live status + duration (1 quota unit per 50 videos)."""
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key or not videos:
        return videos
    by_id = {v["video_id"]: v for v in videos}
    ids = list(by_id)
    for i in range(0, len(ids), 50):
        r = requests.get(API_URL, params={
            "part": "snippet,contentDetails,liveStreamingDetails,statistics",
            "id": ",".join(ids[i:i + 50]),
            "key": key,
        }, timeout=30)
        r.raise_for_status()
        for item in r.json().get("items", []):
            v = by_id[item["id"]]
            sn = item.get("snippet", {})
            v["live_status"] = sn.get("liveBroadcastContent", "none")  # live | upcoming | none
            v["description"] = sn.get("description", v["description"])
            v["duration"] = _iso_duration_seconds(item.get("contentDetails", {}).get("duration"))
            v["views"] = int(item.get("statistics", {}).get("viewCount", 0) or 0)
            lsd = item.get("liveStreamingDetails")
            if lsd:
                v["was_livestream"] = True
                v["scheduled_start"] = lsd.get("scheduledStartTime")
                v["actual_start"] = lsd.get("actualStartTime")
                v["actual_end"] = lsd.get("actualEndTime")
                v["concurrent_viewers"] = lsd.get("concurrentViewers")
            if 0 < v.get("duration", 0) <= 180 and not lsd:
                v["is_short"] = v["is_short"] or v["duration"] <= 60
    return videos


class TranscriptUnavailable(Exception):
    pass


def fetch_transcript(video_id: str) -> list[dict]:
    """Return [{start: seconds, text: str}, ...].

    Uses youtube-transcript-api. YouTube often blocks cloud/datacenter IPs
    (GitHub Actions included); set TRANSCRIPT_PROXY_URL to a residential
    proxy, e.g. http://user:pass@p.webshare.io:80, if you hit that.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    proxy_cfg = None
    proxy = os.environ.get("TRANSCRIPT_PROXY_URL")
    if proxy:
        from youtube_transcript_api.proxies import GenericProxyConfig
        proxy_cfg = GenericProxyConfig(http_url=proxy, https_url=proxy)

    api = YouTubeTranscriptApi(proxy_config=proxy_cfg)
    try:
        fetched = api.fetch(video_id, languages=["en", "en-GB", "en-US", "en-ZA"])
    except Exception:
        # Fall back to any available transcript, translated to English if possible.
        try:
            tlist = api.list(video_id)
            t = next(iter(tlist))
            if t.language_code[:2] != "en" and t.is_translatable:
                t = t.translate("en")
            fetched = t.fetch()
        except Exception as e:  # noqa: BLE001
            raise TranscriptUnavailable(str(e)) from e
    return [{"start": float(s.start), "text": s.text} for s in fetched]


def transcript_to_text(segments: list[dict], every: int = 60) -> str:
    """Readable transcript with a [mm:ss] marker roughly every `every` seconds."""
    out, last_mark = [], -every
    for s in segments:
        if s["start"] - last_mark >= every:
            out.append(f"\n[{fmt_ts(s['start'])}] ")
            last_mark = s["start"]
        out.append(s["text"].replace("\n", " ") + " ")
    return "".join(out).strip()


def fmt_ts(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_time(iso: str | None) -> datetime:
    if not iso:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))
