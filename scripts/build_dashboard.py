#!/usr/bin/env python3
"""Build public/capex-dashboard.html from data/fred.json + data/manual.json.

The page is plain, server-rendered HTML with no JavaScript, so it loads fast,
works with screen readers and keyboard only, and can't break in the browser.
Usage:  python scripts/build_dashboard.py
"""
import datetime as dt
import html
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
esc = html.escape
MINUS = "−"

# Display order. `manual` rows come from data/manual.json, the rest from data/fred.json.
SERIES = [
    dict(key="NEWORDER", name="Core capital-goods orders", unit="$ millions", dec=0, role="Leading", src="FRED NEWORDER"),
    dict(key="ANXAUO", name="Unfilled capital-goods orders", unit="$ millions", dec=0, role="Coincident / leading", src="FRED ANXAUO"),
    dict(key="UDEFNO", name="Defense capital-goods orders", unit="$ millions, not seasonally adjusted", dec=0, role="Leading, noisy", src="FRED UDEFNO"),
    dict(key="PNFI", name="Private nonresidential fixed investment", unit="$ billions, annual rate", dec=1, role="Lagging, the benchmark", src="FRED PNFI"),
    dict(key="ISM_PMI", manual=True, name="ISM Manufacturing PMI", unit="index, 50 = no change", dec=1, role="Leading, fastest", src="ismworld.org"),
    dict(key="USMTO", manual=True, name="Machine tool orders", unit="$ millions", dec=1, role="Leading, most direct", src="AMT USMTO"),
    dict(key="MCUMFN", name="Manufacturing capacity utilization", unit="% of capacity", dec=1, role="Coincident", src="FRED MCUMFN"),
    dict(key="SEAT653MFGN", name="Manufacturing employment, Seattle metro", unit="thousands of jobs", dec=1, role="Lagging, contrary", src="FRED SEAT653MFGN"),
]

MANUAL_STALE_DAYS = 45


def load(name):
    return json.loads((ROOT / "data" / name).read_text())


def num(v, dec):
    return f"{v:,.{dec}f}"


def signed(p, dec=1):
    s = f"{abs(p):.{dec}f}"
    return f"+{s}%" if p >= 0 else f"{MINUS}{s}%"


def period_label(date_str, freq):
    if not date_str:
        return ""
    y, m, _ = (int(x) for x in date_str.split("-"))
    if freq == "Q":
        return f"Q{(m - 1) // 3 + 1} {y}"
    return dt.date(y, m, 1).strftime("%b %Y")


def qlabel(period):  # "2026-Q2" -> "Q2 2026"
    y, q = period.split("-")
    return f"{q} {y}"


def pretty_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


# ---------- vector arrow ----------
def arrow(yoy):
    """Direction = sign and steepness of change, length = size of change (capped at 40%)."""
    m = min(abs(yoy) / 40.0, 1.0)
    sgn = 1 if yoy >= 0 else -1
    ox, oy = 8.0, 24.0
    dx = 20 + 36 * m
    dy = -20 * m * sgn
    ex, ey = ox + dx, oy + dy
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    hs, hw = 9.0, 5.0
    bx, by = ex - ux * hs, ey - uy * hs
    pts = f"{ex:.1f},{ey:.1f} {bx + px * hw:.1f},{by + py * hw:.1f} {bx - px * hw:.1f},{by - py * hw:.1f}"
    cls = "arr up" if sgn > 0 else "arr down"
    return (f'<svg class="{cls}" viewBox="0 0 72 48" aria-hidden="true" focusable="false">'
            f'<line x1="{ox}" y1="{oy}" x2="{bx:.1f}" y2="{by:.1f}" />'
            f'<polygon points="{pts}" /><circle cx="{ox}" cy="{oy}" r="3.5" /></svg>')


# ---------- charts ----------
def pnfi_chart(rows):
    vals = [r["yoy"] for r in rows]
    W, H = 460, 230
    left, right, top, bottom = 12, 12, 34, 46
    lo, hi = min(0, min(vals)), max(0, max(vals))
    span = (hi - lo) or 1
    ph = H - top - bottom
    y = lambda v: top + (hi - v) / span * ph
    n = len(rows)
    slot = (W - left - right) / n
    bw = min(30, slot * 0.6)
    desc = "; ".join(f"{qlabel(r['period'])} {signed(r['yoy'])}" for r in rows)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="pn-t pn-d" class="chart">',
           '<title id="pn-t">Private nonresidential fixed investment, year-over-year growth by quarter</title>',
           f'<desc id="pn-d">{esc(desc)}.</desc>']
    # recessive grid: zero line only, plus one mid guide
    out.append(f'<line class="axis" x1="{left}" x2="{W - right}" y1="{y(0):.1f}" y2="{y(0):.1f}" />')
    for i, r in enumerate(rows):
        cx = left + slot * (i + 0.5)
        v = r["yoy"]
        top_y, bot_y = (y(v), y(0)) if v >= 0 else (y(0), y(v))
        h = max(bot_y - top_y, 1.5)
        latest = i == n - 1
        out.append(f'<g><title>{esc(qlabel(r["period"]))}: {signed(v)}</title>'
                   f'<rect class="bar{" latest" if latest else ""}" x="{cx - bw / 2:.1f}" y="{top_y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="3" /></g>')
        ty = top_y - 8 if v >= 0 else bot_y + 16
        out.append(f'<text class="val{" strong" if latest else ""}" x="{cx:.1f}" y="{ty:.1f}" text-anchor="middle">{signed(v)}</text>')
        yy, qq = r["period"].split("-")
        out.append(f'<text class="tick" x="{cx:.1f}" y="{H - 24}" text-anchor="middle">{qq}</text>'
                   f'<text class="tick" x="{cx:.1f}" y="{H - 8}" text-anchor="middle">{yy}</text>')
    out.append("</svg>")
    return "\n".join(out)


def pnfi_table(rows):
    body = "".join(f"<tr><th scope='row'>{esc(qlabel(r['period']))}</th><td>{signed(r['yoy'])}</td></tr>" for r in rows)
    return ("<details class='tableview'><summary>View as table</summary><div class='tscroll' role='region' aria-label='PNFI growth table' tabindex='0'>"
            "<table class='mini'><caption class='vh'>PNFI year-over-year growth by quarter</caption>"
            "<thead><tr><th scope='col'>Quarter</th><th scope='col'>YoY growth</th></tr></thead>"
            f"<tbody>{body}</tbody></table></div></details>")


def leadlag_chart(results):
    W, H = 460, 270
    left, right, top, bottom = 52, 16, 30, 62
    pw, ph = W - left - right, H - top - bottom
    ylo = min(0.0, math.floor(min(x["r"] for x in results) * 4) / 4)
    y = lambda r: top + (1 - r) / (1 - ylo) * ph
    slot = pw / len(results)
    peak = max(results, key=lambda x: x["r"])
    desc = "; ".join(f"{x['lag']}-quarter lead r = {x['r']:.2f}" for x in results)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="ll-t ll-d" class="chart">',
           '<title id="ll-t">Correlation between core orders growth and investment growth at 0 to 4 quarter leads</title>',
           f'<desc id="ll-d">{esc(desc)}. Strongest at a {peak["lag"]}-quarter lead.</desc>']
    ticks = [round(ylo + 0.25 * i, 2) for i in range(int(round((1 - ylo) / 0.25)) + 1)]
    for g in ticks:
        out.append(f'<line class="{"axis" if g == 0 else "grid"}" x1="{left}" x2="{W - right}" y1="{y(g):.1f}" y2="{y(g):.1f}" />')
        out.append(f'<text class="tick" x="{left - 8}" y="{y(g) + 4:.1f}" text-anchor="end">{g:.2f}</text>')
    for i, x in enumerate(results):
        cx = left + slot * (i + 0.5)
        is_peak = x is peak
        out.append(f'<g><title>{"Same quarter" if x["lag"] == 0 else str(x["lag"]) + "-quarter lead"}: r = {x["r"]:.3f} (n = {x["n"]})</title>'
                   f'<line class="stem{" peak" if is_peak else ""}" x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(0):.1f}" y2="{y(x["r"]):.1f}" />'
                   f'<circle class="dot{" peak" if is_peak else ""}" cx="{cx:.1f}" cy="{y(x["r"]):.1f}" r="{8 if is_peak else 6}" /></g>')
        out.append(f'<text class="val{" strong" if is_peak else ""}" x="{cx:.1f}" y="{y(x["r"]) - 14:.1f}" text-anchor="middle">{x["r"]:.2f}</text>')
        lbl = "Same qtr" if x["lag"] == 0 else f"{x['lag']}Q lead"
        out.append(f'<text class="tick" x="{cx:.1f}" y="{H - 30}" text-anchor="middle">{lbl}</text>')
    out.append(f'<text class="axislabel" x="{left + pw / 2:.1f}" y="{H - 8}" text-anchor="middle">Quarters orders lead investment</text>')
    out.append("</svg>")
    return "\n".join(out)


def leadlag_table(results):
    body = "".join(
        f"<tr><th scope='row'>{'Same quarter' if x['lag'] == 0 else str(x['lag']) + '-quarter lead'}</th><td>{x['r']:.3f}</td><td>{x['n']}</td></tr>"
        for x in results)
    return ("<details class='tableview'><summary>View as table</summary><div class='tscroll' role='region' aria-label='Lead-lag table' tabindex='0'>"
            "<table class='mini'><caption class='vh'>Correlation of orders growth with investment growth</caption>"
            "<thead><tr><th scope='col'>Lead</th><th scope='col'>Correlation (r)</th><th scope='col'>Quarters (n)</th></tr></thead>"
            f"<tbody>{body}</tbody></table></div></details>")


# ---------- page ----------
def build():
    fred, manual = load("fred.json"), load("manual.json")
    css = (ROOT / "templates" / "site.css").read_text() + (ROOT / "templates" / "dashboard.css").read_text()

    # rows
    rows_html = []
    for s in SERIES:
        if s.get("manual"):
            d = manual["indicators"][s["key"]]
            latest, prior = d["latest"], d["prior"]
            lp, pp = d.get("latest_period", ""), d.get("prior_period", "")
            flag = "<span class='flag'>hand-entered</span>"
        else:
            d = fred["series"][s["key"]]
            latest, prior = d["latest"], d["prior"]
            lp, pp = period_label(d.get("latest_date"), d["freq"]), period_label(d.get("prior_date"), d["freq"])
            flag = ""
        chg = (latest / prior - 1) * 100
        word = "up" if chg >= 0 else "down"
        rows_html.append(
            "<tr>"
            f"<th scope='row'><span class='nm'>{esc(s['name'])}{flag}</span>"
            f"<span class='meta'>{esc(s['role'])} &middot; {esc(s['src'])}</span>"
            f"<span class='meta'>{esc(s['unit'])}</span></th>"
            f"<td class='n'>{num(latest, s['dec'])}<span class='per'>{esc(lp)}</span></td>"
            f"<td class='n col-prior'>{num(prior, s['dec'])}<span class='per'>{esc(pp)}</span></td>"
            f"<td class='n chg {'up' if chg >= 0 else 'down'}'><span class='vh'>{word} </span>{signed(chg)}</td>"
            f"<td class='vec'>{arrow(chg)}</td>"
            "</tr>")

    # headline regime from PNFI growth history
    yo = fred["pnfi_yoy"]
    streak = 0
    for i in range(len(yo) - 1, 0, -1):
        if yo[i]["yoy"] > yo[i - 1]["yoy"]:
            streak += 1
        else:
            break
    latest_yoy = yo[-1]["yoy"]
    if latest_yoy <= 0:
        regime, sub = "Contraction", "Investment is shrinking year over year."
    elif streak >= 2:
        regime, sub = "Expansion", f"{streak} straight quarters of accelerating investment."
    elif streak == 1:
        regime, sub = "Expansion", "Investment growth picked up last quarter."
    else:
        regime, sub = "Expansion, cooling", "Investment is still growing, but more slowly than last quarter."

    ll = fred["leadlag"]
    peak = max(ll["results"], key=lambda x: x["r"])
    peak_word = "same-quarter" if peak["lag"] == 0 else f"{peak['lag']}-quarter lead"
    if peak["lag"] == 0:
        peak_sentence = f"Core orders and investment move together in the same quarter (n&nbsp;=&nbsp;{peak['n']})."
    else:
        q = "quarter" if peak["lag"] == 1 else "quarters"
        peak_sentence = f"Core orders lead investment by {peak['lag']} {q} (n&nbsp;=&nbsp;{peak['n']})."
    window_qtrs = ll["quarters"]

    # manual freshness
    approved = dt.date.fromisoformat(manual["approved"])
    age = (dt.date.today() - approved).days
    stale = age > MANUAL_STALE_DAYS
    stale_html = (f"<p class='notice' role='note'><strong>Review due.</strong> The hand-entered figures were last approved {age} days ago.</p>"
                  if stale else "")

    beige = "".join(
        f"<li><time datetime='{esc(b['iso'])}'>{esc(b['date'])}</time><p>{esc(b['text'])}</p></li>" for b in manual["beige"])

    header = ('<a class="skip" href="#main">Skip to main content</a>\n'
              '<header class="site-header"><div class="wrap">'
              '<a class="brand" href="index.html" aria-label="Truvector Industries, home">'
              '<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false"><polygon class="lg-b" points="3,5 37,5 20,37"/>'
              '<polygon class="lg-o" points="20,5 37,5 26.5,23"/><polygon class="lg-s" points="13,5 21,5 20,20"/></svg>'
              '<span><span class="brand-name">TRUVECTOR</span><span class="brand-sub">INDUSTRIES</span></span></a>'
              '<nav aria-label="Primary"><a class="keep" href="index.html">&larr; Home</a></nav></div></header>')

    footer = ('<footer><div class="wrap"><span>&copy; 2026 Truvector Industries. All rights reserved.</span>'
              '<span>Precision. Partnership. Progress.</span></div></footer>')

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>CapEx &amp; Industrial Demand | Truvector Industries</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Michroma&amp;family=Raleway:wght@400;500;600;800&amp;family=IBM+Plex+Mono:wght@400;600&amp;display=swap">
<style>body{{margin:0}}html{{-webkit-text-size-adjust:100%}}
{css}</style>
</head>
<body>
{header}
<main id="main" class="dash" tabindex="-1">
  <div class="pagehead">
    <div class="wrap">
      <p class="eyebrow">Industrial &amp; Capital Markets Research</p>
      <h1>U.S. CapEx &amp; Industrial Demand</h1>
      <p class="lede">Reading the national capital-spending cycle as a demand signal for precision manufacturing.</p>
      <dl class="meta-row">
        <div><dt>Data refreshed</dt><dd><time datetime="{esc(fred['generated'])}">{pretty_date(fred['generated'])}</time></dd></div>
        <div><dt>Hand-entered figures approved</dt><dd><time datetime="{esc(manual['approved'])}">{pretty_date(manual['approved'])}</time></dd></div>
        <div><dt>Sources</dt><dd>FRED, ISM, AMT, SF Fed</dd></div>
      </dl>
    </div>
  </div>

  <div class="wrap">
    {stale_html}
    <section class="reading" aria-labelledby="reading-h">
      <div class="reading-text">
        <h2 id="reading-h" class="eyebrow">Current reading</h2>
        <p class="regime">{esc(regime)}</p>
        <p class="regime-sub">{esc(sub)}</p>
        <p class="regime-sub">Investment growth is measured as private nonresidential fixed investment (<abbr title="Private nonresidential fixed investment">PNFI</abbr>), up {signed(latest_yoy)} from a year earlier.</p>
        <p class="bignum"><span>{peak['r']:.2f}</span> peak correlation</p>
        <p class="regime-sub">{peak_sentence}</p>
      </div>
      <figure class="reading-chart">
        <figcaption><span class="cap">Investment growth, year over year</span><span class="capsub">Last {len(yo)} quarters</span></figcaption>
        {pnfi_chart(yo)}
        {pnfi_table(yo)}
      </figure>
    </section>

    <section aria-labelledby="scorecard-h">
      <h2 id="scorecard-h" class="section-title">Executive scorecard</h2>
      <p class="section-note">Latest reading against the same period a year earlier. Each arrow is a vector: it points up or down with the direction of change, and grows longer and steeper as the change grows (capped at &plusmn;40%). <span class="flag">hand-entered</span> rows are typed in and approved manually rather than pulled by machine, so treat their trend with more caution.</p>
      <div class="tscroll" role="region" aria-labelledby="scorecard-h" tabindex="0">
        <table class="scorecard">
          <caption class="vh">Indicators: latest reading, year-earlier reading, change, and direction</caption>
          <thead><tr>
            <th scope="col">Indicator</th><th scope="col" class="r">Latest</th><th scope="col" class="r col-prior">Year earlier</th>
            <th scope="col" class="r"><abbr title="Year over year">YoY</abbr> change</th><th scope="col" class="c">Vector</th>
          </tr></thead>
          <tbody>
            {chr(10).join(rows_html)}
          </tbody>
        </table>
      </div>
    </section>

    <div class="two-col">
      <section aria-labelledby="ll-h">
        <h2 id="ll-h" class="section-title">Orders lead investment</h2>
        <p class="section-note">Core capital-goods orders (NEWORDER) growth correlated against investment growth at 0&ndash;4 quarter leads, {esc(ll['window'])} ({window_qtrs} quarters).</p>
        <figure class="panel">
          {leadlag_chart(ll['results'])}
          {leadlag_table(ll['results'])}
          <p class="callout">Best fit: <strong>{esc(peak_word)}, r&nbsp;=&nbsp;{peak['r']:.2f}</strong>. Orders move first; business investment follows.</p>
        </figure>
      </section>
      <section aria-labelledby="bb-h">
        <h2 id="bb-h" class="section-title">Regional: PNW Beige Book</h2>
        <p class="section-note">SF Fed Twelfth District, capital-equipment commentary.</p>
        <ol class="beige panel">{beige}</ol>
      </section>
    </div>

    <section class="notes" aria-labelledby="notes-h">
      <h2 id="notes-h" class="section-title">Sources &amp; limits</h2>
      <div class="footer-grid">
        <ul>
          <li>NEWORDER, ANXAUO, UDEFNO, PNFI, MCUMFN, SEAT653MFGN: Federal Reserve Economic Data (FRED), full history, refreshed automatically every Monday.</li>
          <li>ISM Manufacturing PMI (ismworld.org) and machine tool orders (AMT USMTO): single year-over-year comparison, entered by hand and approved before publishing.</li>
          <li>Beige Book excerpts: SF Fed Twelfth District, entered by hand.</li>
        </ul>
        <ul>
          <li>Defense orders (not seasonally adjusted) swing 30&ndash;40% month to month on single large program awards. Don't read one month as a trend.</li>
          <li>Year-over-year correlation between two upward-trending series can overstate true predictive power. No trend-controlled regression has been run.</li>
          <li>The SF Fed's 0.74 sentiment-index correlation remains unverified and is not tested here.</li>
        </ul>
      </div>
      <p class="corr-note"><strong>Data-quality note:</strong> PNW manufacturing employment was corrected after an earlier transcription error inverted its trend. Verify any employment figures reused elsewhere against FRED directly.</p>
    </section>
  </div>
</main>
{footer}
</body>
</html>
"""
    out = ROOT / "public" / "capex-dashboard.html"
    out.write_text(page)
    print(f"Wrote {out.relative_to(ROOT)} ({len(page):,} bytes)")


if __name__ == "__main__":
    build()
