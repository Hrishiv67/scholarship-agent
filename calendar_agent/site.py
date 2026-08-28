"""Generate a standalone HTML dashboard for the program calendar."""
from __future__ import annotations

import html
import json
from datetime import date, timedelta

from .categories import TRACKS, label
from .dates import today_utc
from .render import _due_soon_confirmed, _sort_key

_TRACK_STYLE = {
    "ai": ("#a78bfa", "#7c3aed", "AI"),
    "engineering": ("#38bdf8", "#0284c7", "Engineering"),
    "business": ("#fbbf24", "#d97706", "Business"),
    "general": ("#94a3b8", "#64748b", "General"),
}


def _esc(text) -> str:
    return html.escape(str(text or ""), quote=True)


def _deadline_label(entry: dict) -> tuple[str, str, int | None]:
    """Return (display text, css class, days until deadline or None)."""
    if entry.get("deadline_confirmed") and entry.get("deadline"):
        try:
            d = date.fromisoformat(entry["deadline"])
            days = (d - today_utc()).days
            if days < 0:
                return entry["deadline"], "past", days
            if days <= 14:
                return entry["deadline"], "urgent", days
            if days <= 60:
                return entry["deadline"], "soon", days
            return entry["deadline"], "confirmed", days
        except ValueError:
            pass
    if entry.get("deadline"):
        return entry["deadline"], "unconfirmed", None
    return "No date on page", "none", None


def _card(entry: dict) -> str:
    cat = entry.get("category") or "general"
    accent, _, _ = _TRACK_STYLE.get(cat, _TRACK_STYLE["general"])
    deadline_txt, deadline_cls, days = _deadline_label(entry)
    status = entry.get("status") or "verify"
    name = _esc(entry.get("name"))
    url = _esc(entry.get("url"))
    award = _esc((entry.get("award") or "")[:140])
    elig = _esc((entry.get("eligibility") or "")[:160])
    quote = _esc((entry.get("deadline_quote") or "")[:200])
    days_badge = ""
    if days is not None and days >= 0:
        days_badge = f'<span class="days">{days}d left</span>'
    elif days is not None and days < 0:
        days_badge = '<span class="days past">passed</span>'

    status_chip = {
        "eligible": '<span class="chip ok">Eligible</span>',
        "verify": '<span class="chip warn">Verify</span>',
        "seniors_later": '<span class="chip later">Seniors 2027</span>',
        "ineligible": '<span class="chip skip">Skipped</span>',
    }.get(status, '<span class="chip warn">Verify</span>')

    conf = ""
    if entry.get("deadline_confirmed"):
        conf = '<span class="chip confirmed">Official date</span>'

    return f"""
    <article class="card" data-track="{_esc(cat)}" data-status="{_esc(status)}"
             data-deadline="{_esc(entry.get('deadline') or '')}"
             data-confirmed="{'1' if entry.get('deadline_confirmed') else '0'}"
             style="--accent:{accent}">
      <div class="card-top">
        <div class="deadline {deadline_cls}">{_esc(deadline_txt)}{days_badge}</div>
        <div class="chips">{conf}{status_chip}</div>
      </div>
      <h3><a href="{url}" target="_blank" rel="noopener">{name}</a></h3>
      <p class="award">{award or "See program site for award details."}</p>
      <p class="elig">{elig or "Eligibility not confirmed from official page yet."}</p>
      {f'<p class="quote">"{quote}"</p>' if quote else ''}
      <a class="apply" href="{url}" target="_blank" rel="noopener">Open official page →</a>
    </article>"""


def _events_json(entries: list[dict]) -> str:
    events = []
    for e in entries:
        if e.get("status") == "ineligible":
            continue
        dl = e.get("deadline")
        if not dl:
            continue
        try:
            date.fromisoformat(dl)
        except ValueError:
            continue
        events.append({
            "date": dl,
            "name": e.get("name") or "",
            "url": e.get("url") or "",
            "track": e.get("category") or "general",
            "confirmed": bool(e.get("deadline_confirmed")),
            "status": e.get("status") or "verify",
        })
    return json.dumps(events)


def build_calendar_html(entries: list[dict], generated_at: str) -> str:
    today = today_utc()
    due_soon = _due_soon_confirmed(entries, days=90)
    confirmed = sum(1 for e in entries if e.get("deadline_confirmed"))
    active = [e for e in entries if e.get("status") not in ("ineligible",)]

    by_track: dict[str, list] = {c: [] for c in TRACKS}
    general, seniors, skipped = [], [], []
    for e in entries:
        st = e.get("status") or "verify"
        if st == "ineligible":
            skipped.append(e)
            continue
        if st == "seniors_later":
            seniors.append(e)
            continue
        cat = e.get("category") or "general"
        if cat in TRACKS:
            by_track[cat].append(e)
        else:
            general.append(e)

    due_cards = "".join(_card(e) for e in sorted(due_soon, key=lambda x: x.get("deadline") or ""))

    track_sections = []
    for cat in TRACKS:
        group = sorted(by_track[cat], key=_sort_key)
        accent, accent2, title = _TRACK_STYLE[cat]
        cards = "".join(_card(e) for e in group) or '<p class="empty">No programs in this track yet.</p>'
        track_sections.append(f"""
        <section class="track-section" id="track-{cat}" data-track="{cat}">
          <div class="track-header" style="--accent:{accent};--accent2:{accent2}">
            <h2>{title}</h2>
            <span class="count">{len(group)} programs</span>
          </div>
          <div class="grid">{cards}</div>
        </section>""")

    general_cards = "".join(_card(e) for e in sorted(general, key=_sort_key))
    senior_items = "".join(
        f'<li><a href="{_esc(e.get("url"))}" target="_blank" rel="noopener">{_esc(e.get("name"))}</a>'
        f' <span class="muted">— {_esc(e.get("deadline") or "date TBA")}</span></li>'
        for e in sorted(seniors, key=_sort_key)
    )
    events_json = _events_json(entries)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Program Calendar — AI · Engineering · Business</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet"/>
  <style>
    :root {{
      --bg: #0b0f17;
      --bg2: #111827;
      --card: rgba(255,255,255,0.04);
      --border: rgba(255,255,255,0.08);
      --text: #f1f5f9;
      --muted: #94a3b8;
      --glow: rgba(56,189,248,0.15);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "DM Sans", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      background-image:
        radial-gradient(ellipse 80% 50% at 50% -20%, var(--glow), transparent),
        radial-gradient(ellipse 60% 40% at 100% 0%, rgba(167,139,250,0.12), transparent);
    }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
    header.hero {{
      padding: 2rem 0 2.5rem;
      border-bottom: 1px solid var(--border);
      margin-bottom: 2rem;
    }}
    .eyebrow {{
      font-size: 0.75rem; font-weight: 600; letter-spacing: 0.12em;
      text-transform: uppercase; color: #38bdf8; margin-bottom: 0.5rem;
    }}
    h1 {{ font-size: clamp(1.75rem, 4vw, 2.5rem); font-weight: 700; line-height: 1.15; }}
    .sub {{ color: var(--muted); margin-top: 0.75rem; max-width: 52ch; line-height: 1.55; }}
    .stats {{
      display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 1.75rem;
    }}
    .stat {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 1rem 1.25rem; min-width: 120px;
    }}
    .stat b {{ display: block; font-size: 1.75rem; font-weight: 700; }}
    .stat span {{ font-size: 0.8rem; color: var(--muted); }}
    .toolbar {{
      display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center;
      margin-bottom: 2rem; position: sticky; top: 0; z-index: 10;
      background: rgba(11,15,23,0.85); backdrop-filter: blur(12px);
      padding: 1rem 0; border-bottom: 1px solid var(--border);
    }}
    .search {{
      flex: 1; min-width: 200px; padding: 0.65rem 1rem;
      border-radius: 10px; border: 1px solid var(--border);
      background: var(--bg2); color: var(--text); font: inherit;
    }}
    .search:focus {{ outline: 2px solid #38bdf8; outline-offset: 1px; }}
    .filters {{ display: flex; flex-wrap: wrap; gap: 0.5rem; }}
    .filter {{
      padding: 0.5rem 1rem; border-radius: 999px; border: 1px solid var(--border);
      background: transparent; color: var(--muted); font: inherit; font-size: 0.85rem;
      cursor: pointer; transition: all 0.15s;
    }}
    .filter:hover {{ border-color: #64748b; color: var(--text); }}
    .filter.active {{ background: #1e293b; color: var(--text); border-color: #475569; }}
    .filter[data-t="ai"].active {{ border-color: #a78bfa; color: #c4b5fd; }}
    .filter[data-t="engineering"].active {{ border-color: #38bdf8; color: #7dd3fc; }}
    .filter[data-t="business"].active {{ border-color: #fbbf24; color: #fcd34d; }}
    h2.section-title {{ font-size: 1.25rem; margin-bottom: 1rem; }}
    .grid {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 1rem; margin-bottom: 2.5rem;
    }}
    .card {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 14px; padding: 1.15rem 1.25rem;
      border-left: 3px solid var(--accent, #64748b);
      transition: transform 0.15s, border-color 0.15s;
    }}
    .card:hover {{ transform: translateY(-2px); border-color: rgba(255,255,255,0.14); }}
    .card.hidden {{ display: none; }}
    .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.65rem; }}
    .deadline {{
      font-family: "JetBrains Mono", monospace; font-size: 0.8rem; font-weight: 500;
      padding: 0.25rem 0.5rem; border-radius: 6px; background: rgba(255,255,255,0.06);
    }}
    .deadline.confirmed {{ color: #86efac; }}
    .deadline.urgent {{ color: #fca5a5; background: rgba(248,113,113,0.12); }}
    .deadline.soon {{ color: #fcd34d; }}
    .deadline.unconfirmed {{ color: #fdba74; }}
    .deadline.none {{ color: var(--muted); }}
    .deadline.past {{ color: #64748b; text-decoration: line-through; }}
    .days {{ margin-left: 0.35rem; font-size: 0.7rem; opacity: 0.85; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 0.35rem; justify-content: flex-end; }}
    .chip {{
      font-size: 0.65rem; font-weight: 600; text-transform: uppercase;
      letter-spacing: 0.04em; padding: 0.2rem 0.45rem; border-radius: 4px;
      background: rgba(255,255,255,0.06); color: var(--muted);
    }}
    .chip.confirmed {{ background: rgba(34,197,94,0.15); color: #86efac; }}
    .chip.ok {{ background: rgba(56,189,248,0.12); color: #7dd3fc; }}
    .chip.warn {{ background: rgba(251,191,36,0.12); color: #fcd34d; }}
    .chip.later {{ background: rgba(167,139,250,0.12); color: #c4b5fd; }}
    .chip.skip {{ background: rgba(248,113,113,0.1); color: #fca5a5; }}
    .card h3 {{ font-size: 1rem; line-height: 1.35; margin-bottom: 0.5rem; }}
    .card h3 a {{ color: inherit; text-decoration: none; }}
    .card h3 a:hover {{ color: #7dd3fc; }}
    .award {{ font-size: 0.85rem; color: #cbd5e1; margin-bottom: 0.4rem; line-height: 1.45; }}
    .elig {{ font-size: 0.78rem; color: var(--muted); line-height: 1.4; margin-bottom: 0.5rem; }}
    .quote {{ font-size: 0.72rem; color: #64748b; font-style: italic; border-left: 2px solid var(--border); padding-left: 0.6rem; margin-bottom: 0.6rem; }}
    .apply {{
      display: inline-block; font-size: 0.8rem; font-weight: 600;
      color: #38bdf8; text-decoration: none; margin-top: 0.25rem;
    }}
    .apply:hover {{ text-decoration: underline; }}
    .track-header {{
      display: flex; align-items: baseline; gap: 1rem; margin-bottom: 1rem;
      padding-bottom: 0.5rem; border-bottom: 2px solid var(--accent);
    }}
    .track-header h2 {{ font-size: 1.35rem; }}
    .count {{ font-size: 0.85rem; color: var(--muted); }}
    .empty {{ color: var(--muted); grid-column: 1 / -1; padding: 1rem; }}
    .aside {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 14px; padding: 1.25rem; margin-bottom: 2rem;
    }}
    .aside h3 {{ font-size: 1rem; margin-bottom: 0.75rem; }}
    .aside ul {{ list-style: none; }}
    .aside li {{ padding: 0.35rem 0; font-size: 0.88rem; border-bottom: 1px solid var(--border); }}
    .aside li:last-child {{ border: none; }}
    .aside a {{ color: #c4b5fd; text-decoration: none; }}
    .aside a:hover {{ text-decoration: underline; }}
    .muted {{ color: var(--muted); }}
    footer {{
      margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid var(--border);
      font-size: 0.8rem; color: var(--muted); line-height: 1.6;
    }}
    .follow {{
      display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 1.25rem;
    }}
    .follow a {{
      display: inline-flex; align-items: center; gap: 0.35rem;
      padding: 0.55rem 1rem; border-radius: 10px; font-size: 0.85rem; font-weight: 600;
      text-decoration: none; border: 1px solid var(--border); color: var(--text);
      background: rgba(56,189,248,0.08);
    }}
    .follow a:hover {{ border-color: #38bdf8; background: rgba(56,189,248,0.15); }}
    .updated {{ font-size: 0.8rem; color: var(--muted); margin-top: 0.75rem; }}
    .view-tabs {{
      display: flex; gap: 0.5rem; margin-bottom: 1.5rem;
    }}
    .view-tab {{
      padding: 0.55rem 1.1rem; border-radius: 10px; border: 1px solid var(--border);
      background: transparent; color: var(--muted); font: inherit; font-weight: 600;
      cursor: pointer;
    }}
    .view-tab.active {{ background: #1e293b; color: var(--text); border-color: #475569; }}
    .month-panel {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 16px; padding: 1.25rem; margin-bottom: 2rem;
    }}
    .month-head {{
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 1rem; gap: 1rem;
    }}
    .month-head h2 {{ font-size: 1.2rem; }}
    .month-nav button {{
      background: var(--bg2); border: 1px solid var(--border); color: var(--text);
      border-radius: 8px; padding: 0.4rem 0.75rem; cursor: pointer; font: inherit;
    }}
    .month-nav button:hover {{ border-color: #64748b; }}
    .cal-grid {{
      display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px;
    }}
    .cal-dow {{
      font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
      color: var(--muted); text-align: center; padding: 0.35rem 0;
    }}
    .cal-day {{
      min-height: 72px; border: 1px solid var(--border); border-radius: 8px;
      padding: 0.35rem; background: rgba(255,255,255,0.02); font-size: 0.72rem;
    }}
    .cal-day.other {{ opacity: 0.35; }}
    .cal-day.today {{ border-color: #38bdf8; box-shadow: 0 0 0 1px rgba(56,189,248,0.25); }}
    .cal-num {{ font-weight: 700; font-size: 0.75rem; margin-bottom: 0.2rem; }}
    .cal-ev {{
      display: block; border-radius: 4px; padding: 0.15rem 0.3rem; margin-top: 0.15rem;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-decoration: none;
      color: #e2e8f0; background: rgba(56,189,248,0.15);
    }}
    .cal-ev.confirmed {{ background: rgba(34,197,94,0.2); color: #bbf7d0; }}
    .cal-ev.unconfirmed {{ background: rgba(251,191,36,0.15); color: #fde68a; }}
    .cal-ev:hover {{ filter: brightness(1.15); }}
    .cal-legend {{ display: flex; gap: 1rem; margin-top: 1rem; font-size: 0.75rem; color: var(--muted); }}
    .cal-legend span::before {{
      content: ''; display: inline-block; width: 10px; height: 10px;
      border-radius: 3px; margin-right: 0.35rem; vertical-align: middle;
    }}
    .cal-legend .c::before {{ background: rgba(34,197,94,0.5); }}
    .cal-legend .u::before {{ background: rgba(251,191,36,0.5); }}
    #list-view.hidden, #cal-view.hidden {{ display: none; }}
    @media (max-width: 600px) {{
      .card-top {{ flex-direction: column; }}
      .chips {{ justify-content: flex-start; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <p class="eyebrow">Class of 2028 · Rising Junior · Research calendar</p>
      <h1>Opportunity Calendar</h1>
      <p class="sub">
        Deep-researched AI, Engineering &amp; Business programs for Hrishiv Khatiwala.
        Deadlines appear only when confirmed on the official page this cycle.
      </p>
      <div class="stats">
        <div class="stat"><b>{confirmed}</b><span>Confirmed dates</span></div>
        <div class="stat"><b>{len(active)}</b><span>Active programs</span></div>
        <div class="stat"><b>{len(due_soon)}</b><span>Due in 90 days</span></div>
        <div class="stat"><b>{len(entries)}</b><span>Total tracked</span></div>
      </div>
      <p class="updated">Last updated {_esc(generated_at[:10])} · auto-refreshes every Monday via GitHub</p>
      <div class="follow">
        <a href="calendar.ics">📅 Download calendar (.ics)</a>
        <a id="apple-sub" href="calendar.ics">🍎 Subscribe (Apple Calendar)</a>
        <a id="gcal-sub" href="#" target="_blank" rel="noopener">➕ Add to Google Calendar</a>
        <a href="https://github.com/Hrishiv67/scholarship-agent" target="_blank" rel="noopener">↻ View on GitHub</a>
      </div>
    </header>

    <div class="view-tabs">
      <button class="view-tab active" data-view="cal">📅 Calendar</button>
      <button class="view-tab" data-view="list">📋 All programs</button>
    </div>

    <section id="cal-view" class="month-panel">
      <div class="month-head">
        <div class="month-nav">
          <button type="button" id="prev-month">←</button>
          <button type="button" id="today-btn" style="margin:0 0.35rem">Today</button>
          <button type="button" id="next-month">→</button>
        </div>
        <h2 id="month-label"></h2>
      </div>
      <div class="cal-grid" id="cal-dows"></div>
      <div class="cal-grid" id="cal-days"></div>
      <div class="cal-legend">
        <span class="c">Confirmed on official page</span>
        <span class="u">Unconfirmed / verify</span>
      </div>
    </section>

    <div id="list-view" class="hidden">
    <div class="toolbar">
      <input class="search" type="search" id="q" placeholder="Search programs…" autocomplete="off"/>
      <div class="filters">
        <button class="filter active" data-t="all">All</button>
        <button class="filter" data-t="ai">AI</button>
        <button class="filter" data-t="engineering">Engineering</button>
        <button class="filter" data-t="business">Business</button>
        <button class="filter" data-t="confirmed">Confirmed only</button>
      </div>
    </div>

    {"<section><h2 class='section-title'>Due soon (confirmed)</h2><div class='grid' id='due-soon'>" + due_cards + "</div></section>" if due_cards else ""}

    {"".join(track_sections)}

    {"<section class='track-section' id='track-general'><div class='track-header' style='--accent:#94a3b8'><h2>General</h2><span class='count'>" + str(len(general)) + " programs</span></div><div class='grid'>" + general_cards + "</div></section>" if general_cards else ""}

    {"<aside class='aside'><h3>Track for fall 2027 (seniors-only)</h3><ul>" + senior_items + "</ul></aside>" if senior_items else ""}
    </div>

    <footer>
      Generated {_esc(generated_at[:10])} from official program pages.
      Import <code>calendar.ics</code> for Google Calendar (confirmed dates only).
      Seniors-only, women-only, and need-only programs are filtered per your rules.
    </footer>
  </div>
  <script>
    (function() {{
      const ics = new URL('calendar.ics', location.href).href;
      const apple = document.getElementById('apple-sub');
      const gcal = document.getElementById('gcal-sub');
      if (apple) apple.href = ics.replace(/^https?:/, 'webcal:');
      if (gcal) gcal.href = 'https://calendar.google.com/calendar/r?cid=' + encodeURIComponent(ics);
    }})();

    const EVENTS = {events_json};
    const TRACK_COLORS = {{ ai: '#a78bfa', engineering: '#38bdf8', business: '#fbbf24', general: '#94a3b8' }};
    let viewMonth = new Date();
    viewMonth.setDate(1);

    document.querySelectorAll('.view-tab').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.view-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const cal = btn.dataset.view === 'cal';
        document.getElementById('cal-view').classList.toggle('hidden', !cal);
        document.getElementById('list-view').classList.toggle('hidden', cal);
      }});
    }});

    function renderMonth() {{
      const y = viewMonth.getFullYear();
      const m = viewMonth.getMonth();
      document.getElementById('month-label').textContent =
        viewMonth.toLocaleString('default', {{ month: 'long', year: 'numeric' }});
      const dows = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
      document.getElementById('cal-dows').innerHTML =
        dows.map(d => `<div class="cal-dow">${{d}}</div>`).join('');
      const first = new Date(y, m, 1);
      const start = new Date(first);
      start.setDate(start.getDate() - start.getDay());
      const today = new Date();
      today.setHours(0,0,0,0);
      let cells = '';
      for (let i = 0; i < 42; i++) {{
        const d = new Date(start);
        d.setDate(start.getDate() + i);
        const iso = d.toISOString().slice(0,10);
        const other = d.getMonth() !== m;
        const isToday = d.getTime() === today.getTime();
        const dayEvents = EVENTS.filter(e => e.date === iso);
        const evHtml = dayEvents.map(e => {{
          const cls = e.confirmed ? 'confirmed' : 'unconfirmed';
          const name = e.name.replace(/"/g, '&quot;');
          return `<a class="cal-ev ${{cls}}" href="${{e.url}}" target="_blank" rel="noopener" title="${{name}}">${{name.slice(0,28)}}${{name.length>28?'…':''}}</a>`;
        }}).join('');
        cells += `<div class="cal-day${{other?' other':''}}${{isToday?' today':''}}">
          <div class="cal-num">${{d.getDate()}}</div>${{evHtml}}</div>`;
      }}
      document.getElementById('cal-days').innerHTML = cells;
    }}
    document.getElementById('prev-month').onclick = () => {{ viewMonth.setMonth(viewMonth.getMonth()-1); renderMonth(); }};
    document.getElementById('next-month').onclick = () => {{ viewMonth.setMonth(viewMonth.getMonth()+1); renderMonth(); }};
    document.getElementById('today-btn').onclick = () => {{ viewMonth = new Date(); viewMonth.setDate(1); renderMonth(); }};
    renderMonth();

    const q = document.getElementById('q');
    const cards = () => document.querySelectorAll('.card');
    let track = 'all';
    document.querySelectorAll('.filter').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.filter').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        track = btn.dataset.t;
        applyFilters();
      }});
    }});
    q.addEventListener('input', applyFilters);
    function applyFilters() {{
      const term = (q.value || '').toLowerCase();
      cards().forEach(c => {{
        const text = c.textContent.toLowerCase();
        const t = c.dataset.track;
        const conf = c.dataset.confirmed === '1';
        const matchTrack = track === 'all' || track === t || (track === 'confirmed' && conf);
        const matchConf = track !== 'confirmed' || conf;
        const matchSearch = !term || text.includes(term);
        c.classList.toggle('hidden', !(matchTrack && matchConf && matchSearch));
      }});
      document.querySelectorAll('.track-section').forEach(sec => {{
        const visible = [...sec.querySelectorAll('.card')].some(c => !c.classList.contains('hidden'));
        sec.style.display = visible ? '' : 'none';
      }});
    }}
  </script>
</body>
</html>"""
