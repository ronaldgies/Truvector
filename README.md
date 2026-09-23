# Truvector

Website for truvectorindustries.com, hosted on Cloudflare Pages.

## Layout

| Path | What it is |
|---|---|
| `public/` | The website. Cloudflare publishes only this folder. |
| `public/index.html` | Home page (edited by hand). |
| `public/capex-dashboard.html` | CapEx dashboard. **Generated. Do not edit by hand.** |
| `data/fred.json` | Numbers pulled from FRED. Written by the weekly job. |
| `data/manual.json` | Hand-entered figures (ISM PMI, machine tool orders, Beige Book). Changes only by approved edit. |
| `scripts/` | `update_data.py` (FRED pull) and `build_dashboard.py` (page builder). |
| `templates/` | Shared styling for the dashboard. |
| `.github/workflows/update-data.yml` | Runs every Monday, on demand, and whenever `data/manual.json` changes. |

## Cloudflare Pages settings

- Production branch: `main`
- Build command: *(leave empty)*
- Build output directory: `public`

## Approving a hand-entered update

1. Review the proposed values and their sources.
2. On GitHub, open `data/manual.json`, click the pencil icon, paste the new contents, and commit to `main`.
3. The workflow rebuilds the page and Cloudflare publishes it in about a minute.

That commit is the approval. Nothing hand-entered goes live without it. The page shows a
"Review due" notice if the hand-entered figures are more than 45 days old.

## If the weekly job fails

GitHub emails the repository owner. The job refuses to publish stale, missing or implausible
data and leaves the previous page in place, so a failure never puts bad numbers on the site.
Open the **Actions** tab to read the error. The most common cause is a missing or expired
`FRED_API_KEY` secret.
