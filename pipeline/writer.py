"""Turns a video transcript into a newsroom article using Claude."""
from __future__ import annotations

import json
import os
import re
import unicodedata

MAX_TRANSCRIPT_CHARS = 180_000  # ~45k tokens; long streams get trimmed in the middle

ARTICLE_TOOL = {
    "name": "file_story",
    "description": "File a finished news article to the Oh Allegedly newsroom CMS.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "Max ~90 chars. Punchy, accurate, no clickbait lies. Use 'allegedly'/'claims' where needed."},
            "dek": {"type": "string", "description": "One-sentence standfirst under the headline (max ~200 chars)."},
            "category": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            "is_breaking": {"type": "boolean", "description": "True only for genuinely new, fast-moving developments."},
            "key_points": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 6,
                           "description": "'The receipts' box: short bullet facts, each attributed."},
            "timeline": {
                "type": "array",
                "description": "Notable moments in the video, using the [mm:ss] markers from the transcript.",
                "items": {"type": "object", "properties": {
                    "seconds": {"type": "integer"},
                    "label": {"type": "string"}},
                    "required": ["seconds", "label"]},
                "maxItems": 10,
            },
            "body_markdown": {"type": "string", "description": "The article, 400-900 words, markdown, short paragraphs, may use ### subheads and > pull quotes (quotes must be verbatim from transcript)."},
            "people": {"type": "array", "items": {"type": "string"}},
            "legal_risk": {"type": "string", "enum": ["low", "medium", "high"],
                           "description": "high = serious unproven accusations (crimes, abuse, fraud) against named private or public people."},
        },
        "required": ["headline", "dek", "category", "tags", "is_breaking", "key_points",
                     "timeline", "body_markdown", "people", "legal_risk"],
    },
}

SYSTEM = """You are the overnight editor at OH ALLEGEDLY, an internet-culture and creator-news site that \
turns the channel's YouTube videos and livestreams into written news stories.

Rules you never break:
1. Only report what is in the transcript and video metadata. Do not add outside facts, dates, numbers or quotes.
2. Anything said about a real person that could harm their reputation is ATTRIBUTED and HEDGED: \
"allegedly", "according to the video", "X claimed". Never state an allegation as established fact.
3. Quotes must be verbatim from the transcript. If auto-captions are garbled, paraphrase instead of quoting.
4. Separate what was reported from the host's opinion/commentary — label commentary as such.
5. If the video is mostly chat, banter or a livestream Q&A, write it as a recap ("Livestream Recap") of the main talking points.
6. Never include anything sexual involving minors, doxxing details (addresses, phone numbers), or instructions for harassment.

House style: {style}
Allowed categories (pick exactly one): {categories}"""


def _trim(text: str) -> str:
    if len(text) <= MAX_TRANSCRIPT_CHARS:
        return text
    half = MAX_TRANSCRIPT_CHARS // 2
    return text[:half] + "\n\n[... middle of transcript trimmed for length ...]\n\n" + text[-half:]


def slugify(s: str, max_len: int = 70) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:max_len].rstrip("-") or "story"


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def write_article(video: dict, transcript_text: str, cfg: dict) -> dict:
    nr = cfg["newsroom"]
    system = SYSTEM.format(style=nr["style_notes"].strip(), categories=", ".join(nr["categories"]))
    kind = "LIVESTREAM (ended)" if video.get("was_livestream") else "VIDEO"
    user = (
        f"New {kind} from the channel \"{video['channel_name']}\".\n"
        f"Title: {video['title']}\n"
        f"Published: {video['published']}\n"
        f"Description:\n{(video.get('description') or '')[:3000]}\n\n"
        f"TRANSCRIPT (auto-captions, [mm:ss] markers):\n{_trim(transcript_text)}\n\n"
        "Write the story and file it with the file_story tool."
    )
    msg = _client().messages.create(
        model=nr["model"],
        max_tokens=4000,
        system=system,
        tools=[ARTICLE_TOOL],
        tool_choice={"type": "tool", "name": "file_story"},
        messages=[{"role": "user", "content": user}],
    )
    data = next(b.input for b in msg.content if b.type == "tool_use")
    if data["category"] not in nr["categories"]:
        data["category"] = "Livestream Recap" if video.get("was_livestream") else nr["categories"][1]
    return data


DIGEST_TOOL = {
    "name": "file_digest",
    "description": "File today's briefing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string"},
            "intro": {"type": "string", "description": "2-3 sentence intro."},
            "items": {"type": "array", "items": {"type": "object", "properties": {
                "slug": {"type": "string"}, "blurb": {"type": "string"}},
                "required": ["slug", "blurb"]}},
        },
        "required": ["headline", "intro", "items"],
    },
}


def write_digest(articles: list[dict], cfg: dict) -> dict:
    """A short 'Daily Tea' briefing that rounds up the last 24h of stories."""
    listing = "\n".join(f"- slug={a['slug']} | {a['headline']} — {a['dek']}" for a in articles)
    msg = _client().messages.create(
        model=cfg["newsroom"]["model"],
        max_tokens=1500,
        system="You write the daily briefing for OH ALLEGEDLY. Only use the stories given. Keep allegations attributed. "
               + cfg["newsroom"]["style_notes"],
        tools=[DIGEST_TOOL],
        tool_choice={"type": "tool", "name": "file_digest"},
        messages=[{"role": "user", "content": f"Today's stories:\n{listing}\n\nWrite a one-line blurb for each, most important first."}],
    )
    return next(b.input for b in msg.content if b.type == "tool_use")


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
