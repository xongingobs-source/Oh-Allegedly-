"""Writes fictional SAMPLE stories so the site looks alive before the first real run.

    python scripts/seed_demo.py          # add samples
    python scripts/seed_demo.py --clear  # remove them (do this before launch)

All people and brands below are invented.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "content" / "articles"
DIG = ROOT / "content" / "digests"
now = datetime.now(timezone.utc)


def t(hours):
    return (now - timedelta(hours=hours)).isoformat()


P = "This is a sample story with invented people, generated so you can see the layout before the robot files real ones."

STORIES = [
    dict(slug="glowbar-founder-addresses-refund-delays-on-stream", hours=0.6, breaking=True, cat="Breaking", live=True,
         headline="GlowBar founder addresses refund delays live on stream — fans say 'not good enough'",
         dek="In a tense 40-minute livestream, the fictional skincare founder blamed a payment processor for weeks of missing refunds. Chat was not convinced.",
         points=["Founder claimed a 'processor freeze' caused refund delays, according to the stream",
                 "Says all refunds will land 'within 10 working days'",
                 "Several viewers in chat alleged they'd waited since August",
                 "No documents were shown on stream to back the processor claim"],
         tags=["GlowBar", "refunds", "creator brands"]),
    dict(slug="duo-podcast-splits-after-five-years-host-hints-at-contract-row", hours=3, breaking=True, cat="Creators",
         headline="Five years, one mic: 'Two Mics Deep' splits as host hints at contract row",
         dek="One half of the fictional comedy podcast says he was 'locked out' of the channel — his co-host has yet to respond.",
         points=["Host claimed he lost access to the shared channel last week", "Alleges a dispute over revenue split",
                 "Co-host has not commented publicly, per the video", "Final episode had been recorded, he said"],
         tags=["podcasts", "Two Mics Deep"]),
    dict(slug="reality-star-denies-ghostwritten-memoir-claims", hours=7, cat="Celebrity",
         headline="Reality star denies her memoir was ghostwritten: 'Every comma is mine'",
         dek="A former contestant on a fictional dating show pushed back on claims that a ghostwriter did the heavy lifting.",
         points=["Claims emerged from an anonymous post, the video says", "Star denied the claims in a 12-minute response",
                 "Publisher has not commented, according to the host"],
         tags=["books", "reality TV"]),
    dict(slug="small-claims-court-date-set-in-gaming-sponsorship-dispute", hours=20, cat="Court & Legal",
         headline="Court date set in gaming sponsorship dispute, creator says",
         dek="The fictional streamer says a peripherals brand owes her three months of fees; the brand allegedly says she broke exclusivity.",
         points=["Hearing set for next month, per the streamer", "Brand allegedly claims an exclusivity breach",
                 "Neither side has shared the contract publicly"],
         tags=["sponsorships", "streaming", "legal"]),
    dict(slug="livestream-recap-sunday-tea-spill-q-and-a", hours=28, cat="Livestream Recap", live=True,
         headline="Sunday tea-spill recap: the five biggest moments from last night's three-hour stream",
         dek="Merch drops, a surprise call-in and a promise of 'receipts' next week — everything you missed.",
         points=["Host teased a 'big investigation' coming next week", "A surprise caller disputed an earlier story",
                 "Merch restock confirmed for Friday"],
         tags=["livestream", "recap"]),
    dict(slug="viral-diy-hack-pulled-after-safety-warnings", hours=40, cat="Internet Culture",
         headline="Viral DIY 'hack' pulled after safety warnings pile up",
         dek="The fictional home-reno account deleted the clip after electricians flooded the comments.",
         points=["Clip reached millions of views before deletion, according to the video",
                 "Creator apologised in a follow-up story", "Platform did not remove it — the creator did"],
         tags=["DIY", "viral"]),
    dict(slug="creator-collective-announces-union-style-charter", hours=55, cat="Creators",
         headline="Creator collective unveils 'fair pay' charter for brand deals",
         dek="Forty fictional mid-size creators say they'll refuse deals that don't meet a minimum rate card.",
         points=["Charter sets minimum rates by audience size", "Organisers claim 40 signatories",
                 "Brands named in the video have not responded"],
         tags=["creator economy", "brand deals"]),
]


def body(s):
    return (f"{P}\n\n"
            f"{s['dek']} The details below come from the source video and have not been independently verified.\n\n"
            "### What was said\n\n"
            "According to the video, the dispute had been building for weeks before it spilled into public view. "
            "The host walked viewers through a timeline of posts and screenshots, stressing that much of it remains unconfirmed.\n\n"
            "> \"I'm only telling you what I've been shown — make your own mind up.\"\n\n"
            "### What happens next\n\n"
            "The host said they had reached out for comment and would update viewers in a follow-up. "
            "Oh Allegedly will update this story if a response is received.\n\n"
            "### The commentary\n\n"
            "In the opinion section of the video, the host argued the situation was a lesson in transparency for creator-led brands.")


def main():
    if "--clear" in sys.argv:
        for f in list(ART.glob("*.json")) + list(DIG.glob("*.json")):
            if json.loads(f.read_text()).get("demo"):
                f.unlink()
        (ROOT / "data" / "live.json").unlink(missing_ok=True)
        print("samples removed"); return
    ART.mkdir(parents=True, exist_ok=True); DIG.mkdir(parents=True, exist_ok=True)
    for s in STORIES:
        a = {"demo": True, "slug": s["slug"], "headline": s["headline"], "dek": s["dek"], "category": s["cat"],
             "tags": s["tags"], "is_breaking": s.get("breaking", False), "key_points": s["points"],
             "timeline": [{"seconds": 15, "label": "Cold open"}, {"seconds": 312, "label": "The timeline begins"},
                          {"seconds": 1104, "label": "The big claim"}, {"seconds": 1890, "label": "Host's verdict"}],
             "body_markdown": body(s), "people": [], "legal_risk": "low", "video_id": None,
             "video_url": "https://www.youtube.com/", "video_title": "Sample video", "thumbnail": None,
             "source_channel": "Oh Allegedly", "is_own_channel": True, "was_livestream": s.get("live", False),
             "published": t(s["hours"]), "updated": t(s["hours"])}
        (ART / f"{s['slug']}.json").write_text(json.dumps(a, indent=2))
    today = now.date().isoformat()
    (DIG / f"{today}.json").write_text(json.dumps({
        "demo": True, "date": today, "headline": "Refund rage, a podcast split and a memoir row",
        "intro": "A busy day on the timeline. Here's everything the channel covered in the last 24 hours — allegedly.",
        "items": [{"slug": s["slug"], "blurb": s["dek"]} for s in STORIES[:4]]}, indent=2))
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "live.json").write_text(json.dumps({"streams": [{
        "video_id": "demo", "title": "SAMPLE: Late-night tea spill — your questions answered", "url": "https://www.youtube.com/",
        "live_status": "live", "channel_name": "Oh Allegedly"}]}))
    print(f"{len(STORIES)} sample stories written")


if __name__ == "__main__":
    main()
