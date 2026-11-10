// OH ALLEGEDLY — tiny client: live relative times, live-stream polling, search, share, timestamp seeking.
(() => {
  const root = document.body.dataset.root || "";

  // "12 min ago" labels stay fresh while the page is open
  const ago = iso => {
    const s = (Date.now() - new Date(iso)) / 1000;
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)} min ago`;
    if (s < 86400) return `${Math.floor(s / 3600)} hr ago`;
    if (s < 604800) return `${Math.floor(s / 86400)} d ago`;
    return new Date(iso).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  };
  const tick = () => document.querySelectorAll("[data-ago]").forEach(el => (el.textContent = ago(el.dataset.ago)));
  tick(); setInterval(tick, 60_000);

  // Poll live.json so open tabs pick up a stream after the next automatic rebuild
  const banner = document.getElementById("liveBanner");
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  async function pollLive() {
    try {
      const r = await fetch(`${root}live.json?ts=${Date.now()}`, { cache: "no-store" });
      if (!r.ok) return;
      const { streams = [] } = await r.json();
      banner.hidden = streams.length === 0;
      banner.innerHTML = streams.map(s => `
        <a class="live-banner__item" href="${esc(s.url)}" target="_blank" rel="noopener">
          <span class="live-dot"></span><strong>${s.live_status === "live" ? "LIVE NOW" : "STARTING SOON"}</strong>
          <span>${esc(s.title)}</span><span class="mono">Watch on YouTube →</span></a>`).join("");
    } catch (_) { /* offline or file:// preview */ }
  }
  if (banner && location.protocol.startsWith("http")) setInterval(pollLive, 90_000);

  // Search (loads the index on first open)
  const dlg = document.getElementById("searchDlg"), input = document.getElementById("searchInput"),
        out = document.getElementById("searchResults");
  let index = null;
  document.getElementById("searchBtn")?.addEventListener("click", async () => {
    dlg.showModal(); input.focus();
    if (!index) { try { index = await (await fetch(`${root}search.json`)).json(); } catch { index = []; } }
  });
  dlg?.addEventListener("click", e => { if (e.target === dlg) dlg.close(); });
  input?.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    if (!q || !index) { out.innerHTML = ""; return; }
    out.innerHTML = index
      .filter(a => [a.h, a.d, a.c, ...(a.t || [])].join(" ").toLowerCase().includes(q))
      .slice(0, 20)
      .map(a => `<li><a href="${root}story/${a.s}/"><strong>${esc(a.h)}</strong><small>${esc(a.c || "")} — ${esc(a.d)}</small></a></li>`)
      .join("") || `<li><a>No stories match “${esc(q)}”.</a></li>`;
  });
  document.addEventListener("keydown", e => {
    if (e.key === "/" && !/input|textarea/i.test(document.activeElement.tagName)) { e.preventDefault(); document.getElementById("searchBtn").click(); }
  });

  // Share
  document.querySelectorAll("[data-share]").forEach(b => b.addEventListener("click", async () => {
    const data = { title: document.title, url: location.href };
    if (navigator.share) { try { await navigator.share(data); } catch {} }
    else { try { await navigator.clipboard.writeText(location.href); b.textContent = "Link copied ✓"; } catch {} }
  }));

  // Timeline: seek the embedded player instead of leaving the page
  const frame = document.getElementById("ytplayer");
  document.querySelectorAll("[data-seek]").forEach(a => a.addEventListener("click", e => {
    if (!frame) return;
    e.preventDefault();
    const t = +a.dataset.seek;
    frame.contentWindow.postMessage(JSON.stringify({ event: "command", func: "seekTo", args: [t, true] }), "*");
    frame.contentWindow.postMessage(JSON.stringify({ event: "command", func: "playVideo", args: [] }), "*");
    frame.scrollIntoView({ behavior: "smooth", block: "center" });
  }));
})();
