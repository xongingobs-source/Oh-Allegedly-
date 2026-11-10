"""Turns a video transcript into a newsroom article — using FREE AI by default.

Providers are tried in the order listed in config.yaml (newsroom.providers):

  github  – GitHub Models. Free for every GitHub account, no key, no card.
            Inside GitHub Actions it uses the built-in GITHUB_TOKEN.
            Free tier: ~150 requests/day and ~8k input tokens per request on
            "low" tier models, so long transcripts are condensed in chunks first.
  gemini  – Google Gemini free tier. Needs a free key from aistudio.google.com
            (no card) saved as the GEMINI_API_KEY secret.
  claude  – Anthropic Claude (paid). Only used if ANTHROPIC_API_KEY is set.
  basic   – No AI at all. Builds a simple "video summary" post from the title,
            description and transcript. Always works, always free.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata

import requests

FIELDS_SPEC = """Return ONLY a JSON object with exactly these keys:
{
  "headline": string (max ~90 chars, punchy but accurate; use "allegedly"/"claims" where needed),
  "dek": string (one-sentence standfirst, max ~200 chars),
  "category": string (exactly one of the allowed categories),
  "tags": array of up to 8 short strings,
  "is_breaking": boolean (true only for genuinely new, fast-moving developments),
  "key_points": array of 3-6 short attributed bullet facts,
  "timeline": array of up to 10 {"seconds": integer, "label": string} using the [mm:ss] markers,
  "body_markdown": string (400-900 words, markdown, short paragraphs, may use ### subheads and > pull quotes that are verbatim from the transcript),
  "people": array of names mentioned,
  "legal_risk": "low" | "medium" | "high" (high = serious unproven accusations such as crimes, abuse or fraud against named people)
}"""

SYSTEM = """You are the overnight editor at OH ALLEGEDLY, an internet-culture and creator-news site that \
turns the channel's YouTube videos and livestreams into written news stories.

Rules you never break:
1. Only report what is in the transcript/notes and video metadata. Do not add outside facts, dates, numbers or quotes.
2. Anything said about a real person that could harm their reputation is ATTRIBUTED and HEDGED: \
"allegedly", "according to the video", "X claimed". Never state an allegation as established fact.
3. Quotes must be verbatim from the transcript. If auto-captions are garbled, paraphrase instead of quoting.
4. Separate what was reported from the host's opinion/commentary — label commentary as such.
5. If the video is mostly chat, banter or a livestream Q&A, write it as a recap ("Livestream Recap") of the main talking points.
6. Never include anything sexual involving minors, doxxing details (addresses, phone numbers), or instructions for harassment.

House style: {style}
Allowed categories (pick exactly one): {categories}"""


# ─────────────────────────── helpers
def slugify(s: str, max_len: int = 70) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:max_len].rstrip("-") or "story"


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


class ProviderError(Exception):
    pass


# ─────────────────────────── providers (all speak the OpenAI chat format)
def _openai_style(url: str, key: str, model: str, system: str, user: str, max_tokens: int, json_mode=True) -> str:
    body = {"model": model, "max_tokens": max_tokens, "temperature": 0.4,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    for attempt in range(3):
        r = requests.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json=body, timeout=180)
        if r.status_code == 429 and attempt < 2:  # free tiers rate-limit per minute: wait and retry
            time.sleep(int(r.headers.get("retry-after", "30") or 30) + 2)
            continue
        if r.status_code == 400 and json_mode and "response_format" in r.text:
            body.pop("response_format", None); json_mode = False
            continue
        if not r.ok:
            raise ProviderError(f"{r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]
    raise ProviderError("rate limited (429) — daily free quota may be used up")


def _call(provider: str, cfg: dict, system: str, user: str, max_tokens: int = 3000, json_mode=True) -> str:
    models = cfg["newsroom"].get("models", {})
    if provider == "github":
        key = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_MODELS_TOKEN")
        if not key:
            raise ProviderError("no GITHUB_TOKEN")
        return _openai_style("https://models.github.ai/inference/chat/completions", key,
                             models.get("github", "openai/gpt-4o-mini"), system, user, min(max_tokens, 4000), json_mode)
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ProviderError("no GEMINI_API_KEY")
        return _openai_style("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", key,
                             models.get("gemini", "gemini-flash-latest"), system, user, max_tokens, json_mode)
    if provider == "claude":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError("no ANTHROPIC_API_KEY")
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=180, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": models.get("claude", "claude-sonnet-5-5"), "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]})
        if not r.ok:
            raise ProviderError(f"{r.status_code}: {r.text[:300]}")
        return "".join(b.get("text", "") for b in r.json()["content"])
    raise ProviderError(f"unknown provider {provider}")


# Per-request input budget (characters). GitHub's free tier caps input at ~8k tokens.
CHAR_BUDGET = {"github": 18_000, "gemini": 400_000, "claude": 300_000}


def _condense(provider: str, cfg: dict, transcript: str, title: str) -> str:
    """Split a long transcript into chunks and turn each into dense timestamped notes."""
    budget = CHAR_BUDGET.get(provider, 18_000)
    if len(transcript) <= budget:
        return transcript
    chunk = budget - 2000
    pieces = [transcript[i:i + chunk] for i in range(0, len(transcript), chunk)]
    # Keep the number of free requests sensible for very long streams.
    if len(pieces) > 6:
        step = len(pieces) / 6
        pieces = [pieces[int(i * step)] for i in range(6)]
    notes = []
    for n, p in enumerate(pieces, 1):
        notes.append(_call(provider, cfg,
            "You take precise reporter's notes from a video transcript. Keep [mm:ss] markers, who said what, "
            "claims (attributed), numbers, names, and up to 3 short verbatim quotes. No outside facts. Plain text bullets.",
            f"Video: {title}\nPart {n} of {len(pieces)}:\n{p}", max_tokens=600, json_mode=False))
    out = "REPORTER'S NOTES (condensed from the full transcript):\n" + "\n".join(notes)
    return out[:budget]


def _normalise(data: dict, video: dict, cfg: dict) -> dict:
    cats = cfg["newsroom"]["categories"]
    data.setdefault("headline", video["title"])
    data.setdefault("dek", "")
    data.setdefault("tags", []); data.setdefault("people", []); data.setdefault("timeline", [])
    data.setdefault("key_points", []); data.setdefault("is_breaking", False)
    data.setdefault("legal_risk", "medium"); data.setdefault("body_markdown", "")
    if data.get("category") not in cats:
        data["category"] = "Livestream Recap" if video.get("was_livestream") and "Livestream Recap" in cats else cats[1]
    tl = []
    for t in data["timeline"] if isinstance(data["timeline"], list) else []:
        try:
            tl.append({"seconds": int(float(t["seconds"])), "label": str(t["label"])})
        except Exception:  # noqa: BLE001
            pass
    data["timeline"] = tl[:10]
    if data["legal_risk"] not in ("low", "medium", "high"):
        data["legal_risk"] = "medium"
    if len(data["body_markdown"]) < 200:
        raise ProviderError("article came back too short")
    return data


def _basic_article(video: dict, segments_text: str, cfg: dict) -> dict:
    """No-AI fallback: an honest 'new video' post built from the creator's own words."""
    desc = (video.get("description") or "").strip()
    first = next((l for l in desc.splitlines() if l.strip() and "http" not in l), "")
    excerpt = re.sub(r"\[\d+:\d{2}(?::\d{2})?\]\s*", "", segments_text)[:1500].rsplit(" ", 1)[0]
    body = (f"{desc[:1200]}\n\n" if desc else "") + \
           ("### From the video\n\n> " + excerpt + " …\n\n" if excerpt else "") + \
           f"Watch the full {'stream' if video.get('was_livestream') else 'video'} above for the whole story."
    return {
        "headline": video["title"], "dek": first[:200] or f"New from {video['channel_name']}.",
        "category": "Livestream Recap" if video.get("was_livestream") else cfg["newsroom"]["categories"][1],
        "tags": [], "is_breaking": False,
        "key_points": [f"New {'livestream' if video.get('was_livestream') else 'video'} from {video['channel_name']}",
                       "Full details in the video", "Story auto-filed by the newsroom robot"],
        "timeline": [], "body_markdown": body, "people": [], "legal_risk": "low", "auto_basic": True,
    }


# ─────────────────────────── public API
def write_article(video: dict, transcript_text: str, cfg: dict) -> dict:
    nr = cfg["newsroom"]
    system = SYSTEM.format(style=nr["style_notes"].strip(), categories=", ".join(nr["categories"])) + "\n\n" + FIELDS_SPEC
    kind = "LIVESTREAM (ended)" if video.get("was_livestream") else "VIDEO"
    errors = []
    for provider in nr.get("providers", ["github", "gemini", "basic"]):
        if provider == "basic":
            if not video.get("is_own_channel", True):
                break  # never auto-post other people's content without AI rewriting
            art = _basic_article(video, transcript_text, cfg)
            art["writer"] = "basic"
            return art
        try:
            material = _condense(provider, cfg, transcript_text, video["title"])
            user = (f"New {kind} from the channel \"{video['channel_name']}\".\n"
                    f"Title: {video['title']}\nPublished: {video.get('published')}\n"
                    f"Description:\n{(video.get('description') or '')[:1500]}\n\n"
                    f"TRANSCRIPT ([mm:ss] markers):\n{material}\n\nWrite the story as JSON.")
            data = _normalise(_parse_json(_call(provider, cfg, system, user, 3500)), video, cfg)
            data["writer"] = provider
            return data
        except Exception as e:  # noqa: BLE001 — try the next provider
            errors.append(f"{provider}: {e}")
            print(f"[writer] {provider} failed → trying next ({str(e)[:160]})", flush=True)
    raise ProviderError("; ".join(errors) or "no providers configured")


def write_digest(articles: list[dict], cfg: dict) -> dict:
    """A short 'Daily Tea' briefing that rounds up the last 24h of stories."""
    listing = "\n".join(f"- slug={a['slug']} | {a['headline']} — {a['dek']}" for a in articles[:25])
    system = ("You write the daily briefing for OH ALLEGEDLY. Only use the stories given. Keep allegations attributed. "
              + cfg["newsroom"]["style_notes"] +
              '\nReturn ONLY JSON: {"headline": string, "intro": "2-3 sentences", '
              '"items": [{"slug": string, "blurb": "one line"}]} — most important first.')
    for provider in [p for p in cfg["newsroom"].get("providers", []) if p != "basic"]:
        try:
            return _parse_json(_call(provider, cfg, system, f"Today's stories:\n{listing}", 1500))
        except Exception as e:  # noqa: BLE001
            print(f"[writer] digest via {provider} failed: {str(e)[:160]}")
    # No AI available: a plain list still works.
    return {"headline": f"{len(articles)} stories you might have missed",
            "intro": "Everything the channel covered in the last 24 hours.",
            "items": [{"slug": a["slug"], "blurb": a["dek"]} for a in articles]}
