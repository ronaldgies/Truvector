#!/usr/bin/env python3
"""Refresh data/fred.json from the FRED API (standard library only).

Usage:  FRED_API_KEY=... python scripts/update_data.py

Safety rules: if anything looks wrong (stale series, missing prior-year value,
absurd swing, API failure) the script exits with an error and leaves the
existing data/fred.json untouched, so a bad pull can never reach the site.
"""
import datetime as dt
import json
import math
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "fred.json"
API = "https://api.stlouisfed.org/fred/series/observations"

# key -> frequency ("M" monthly, "Q" quarterly) and the oldest latest-date we accept (days)
SERIES = {
    "NEWORDER": ("M", 120),      # core (nondefense ex-aircraft) capital goods new orders
    "ANXAUO": ("M", 120),        # unfilled orders, same category
    "UDEFNO": ("M", 120),        # defense capital goods new orders (not seasonally adjusted)
    "PNFI": ("Q", 240),          # private nonresidential fixed investment (quarter-start dates)
    "MCUMFN": ("M", 90),         # manufacturing capacity utilization
    "SEAT653MFGN": ("M", 150),   # manufacturing employment, Seattle-Tacoma-Bellevue MSA
}
MAX_ABS_YOY_PCT = 300.0          # anything larger is treated as a data error


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def fetch(series_id, key):
    q = urllib.parse.urlencode({"series_id": series_id, "api_key": key, "file_type": "json"})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(f"{API}?{q}", timeout=45) as r:
                payload = json.load(r)
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            time.sleep(2 ** attempt * 3)
    else:
        fail(f"{series_id}: FRED request failed after retries ({last})")
    obs = []
    for o in payload.get("observations", []):
        if o["value"] in (".", "", None):
            continue
        d = dt.date.fromisoformat(o["date"])
        v = float(o["value"])
        if not math.isfinite(v):
            fail(f"{series_id}: non-finite value on {o['date']}")
        obs.append((d, v))
    obs.sort()
    if len(obs) < 40:
        fail(f"{series_id}: only {len(obs)} observations returned")
    return obs


def latest_and_prior(series_id, obs, max_age_days):
    d, v = obs[-1]
    age = (dt.date.today() - d).days
    if age > max_age_days:
        fail(f"{series_id}: latest observation {d} is {age} days old (limit {max_age_days})")
    lookup = {(x.year, x.month): val for x, val in obs}
    pd_key = (d.year - 1, d.month)
    if pd_key not in lookup:
        fail(f"{series_id}: no observation for {pd_key[0]}-{pd_key[1]:02d} to compare against")
    prior = lookup[pd_key]
    prior_date = dt.date(pd_key[0], pd_key[1], 1)
    if prior == 0:
        fail(f"{series_id}: prior-year value is zero")
    yoy = (v / prior - 1) * 100
    if abs(yoy) > MAX_ABS_YOY_PCT:
        fail(f"{series_id}: year-over-year change of {yoy:.0f}% looks like a data error")
    return v, d, prior, prior_date


def quarter_index(d):
    return d.year * 4 + (d.month - 1) // 3


def quarterly_mean(obs):
    """Monthly observations -> {quarter_index: mean}, complete quarters only
    (the very first quarter is allowed to have 2 months, as the series starts in February)."""
    buckets = {}
    for d, v in obs:
        buckets.setdefault(quarter_index(d), []).append(v)
    first = min(buckets)
    return {q: sum(vs) / len(vs) for q, vs in buckets.items() if len(vs) == 3 or (q == first and len(vs) >= 2)}


def yoy_series(q_values):
    return {q: (v / q_values[q - 4] - 1) * 100 for q, v in q_values.items() if (q - 4) in q_values and q_values[q - 4]}


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def label(q):
    return f"{q // 4}-Q{q % 4 + 1}"


def pretty(q):
    return f"{q // 4} Q{q % 4 + 1}"


def main():
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        fail("FRED_API_KEY is not set (add it as a repository secret named FRED_API_KEY)")

    data = {}
    out_series = {}
    for sid, (freq, max_age) in SERIES.items():
        obs = fetch(sid, key)
        data[sid] = obs
        v, d, prior, pd_ = latest_and_prior(sid, obs, max_age)
        out_series[sid] = {
            "freq": freq,
            "latest": round(v, 3), "latest_date": d.isoformat(),
            "prior": round(prior, 3), "prior_date": pd_.isoformat(),
        }

    # PNFI year-over-year, last 8 quarters
    pnfi_q = {quarter_index(d): v for d, v in data["PNFI"]}
    pnfi_yoy = yoy_series(pnfi_q)
    recent = sorted(pnfi_yoy)[-8:]
    pnfi_recent = [{"period": label(q), "yoy": round(pnfi_yoy[q], 1)} for q in recent]

    # Lead-lag: NEWORDER YoY (quarterly mean) leading PNFI YoY by 0-4 quarters
    orders_yoy = yoy_series(quarterly_mean(data["NEWORDER"]))
    common = sorted(set(orders_yoy) & set(pnfi_yoy))
    if len(common) < 60:
        fail("not enough overlapping quarters for the lead-lag regression")
    results = []
    for lag in range(5):
        pairs = [(orders_yoy[q - lag], pnfi_yoy[q]) for q in pnfi_yoy if (q - lag) in orders_yoy]
        r = pearson([p[0] for p in pairs], [p[1] for p in pairs])
        results.append({"lag": lag, "r": round(r, 3), "n": len(pairs)})
    first_q = min(quarterly_mean(data["NEWORDER"]))
    last_q = max(common)

    new = {
        "series": out_series,
        "pnfi_yoy": pnfi_recent,
        "leadlag": {"window": f"{pretty(first_q)} – {pretty(last_q)}", "quarters": len(common), "results": results},
    }

    # Keep the old 'generated' date unless something actually changed (avoids a weekly no-op commit)
    old = {}
    if OUT.exists():
        old = json.loads(OUT.read_text())
    unchanged = all(old.get(k) == new[k] for k in new)
    new["generated"] = old.get("generated") if (unchanged and old.get("generated")) else dt.date.today().isoformat()
    new_ordered = {"generated": new["generated"], **{k: new[k] for k in ("series", "pnfi_yoy", "leadlag")}}

    OUT.write_text(json.dumps(new_ordered, indent=2, ensure_ascii=False) + "\n")
    peak = max(results, key=lambda x: x["r"])
    print(f"Updated {OUT.name}: unchanged={unchanged}; lead-lag peak r={peak['r']} at {peak['lag']}Q (n={peak['n']})")
    for x in results:
        print(f"  lag {x['lag']}: r={x['r']:.3f} n={x['n']}")


if __name__ == "__main__":
    main()
