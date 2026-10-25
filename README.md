# 🌲 HS Tariff Decision Tree Wire

An autonomous, zero-maintenance data infrastructure running entirely on GitHub Actions. It translates the World Customs Organization (WCO) Harmonized System nomenclature into deterministic classification trees.

## Token Reduction Metrics
- **Average Token Savings**: ~95%
- **Complexity**: Replaces linear $O(N)$ document scanning across 1,000+ tariff lines with an $O(\log N)$ 2-step decision path.

## Machine Feeds
- [`v1/index.json`](public/v1/index.json) (Catalog & stats)
- [`llms.txt`](public/llms.txt) (Token-efficient LLM digest)
- `trees.parquet` (Columnar database snapshot)

## Architecture
- **Source**: WCO Harmonized System 2022 dataset
- **Engine**: Python Tree Compiler + DuckDB
- **Ledger**: Append-only Git-committed JSONL in `/data/history`
- **Delivery**: GitHub Pages (Fastly CDN)
