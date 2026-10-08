# CuriousScan Deal Radar

An open-source keyword watcher for deal hunters. Point it at public deal
communities, give it the words you care about — it prints matching posts as
they appear.

```bash
# one scan, right now
python deal_radar.py --once --keywords free,giveaway,"promo code"

# keep watching every 5 minutes
python deal_radar.py --watch --interval 300 --subreddits deals,buildapcsales,GameDeals

# machine-readable output
python deal_radar.py --once --json > hits.json
```

## How it works

- Polls subreddits' public RSS feeds (no API key, no account needed)
- Matches keywords case-insensitively against post titles and bodies
- Dedupes by post ID within a run; `--watch` keeps polling forever

## Options

| Flag | Default | What it does |
|---|---|---|
| `--subreddits` | deals, buildapcsales, FreeEBOOKS, GameDeals, frugalmalefashion | comma-separated list to watch |
| `--keywords` | free, giveaway, promo code, coupon, 100% off | comma-separated keywords |
| `--once` | — | single scan pass, then exit |
| `--watch` | — | poll continuously until Ctrl+C |
| `--interval` | 300 | seconds between passes in watch mode |
| `--json` | — | emit hits as JSON |

## Requirements

Python 3.8+. Stdlib only — zero dependencies.

## Roadmap

- Telegram/Discord alert sink
- Threads/Instagram public-post watchers
- Price-drop tracking for watched products

## License

MIT — see `LICENSE`.

---
Built by [CuriousScan](https://curiousscan.in) — *Less noise. More signal.*
