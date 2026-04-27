# Real Estate Investment Analyzer — Austin TX

Automated due diligence tool for Austin real estate investment analysis.

## Quick Start

```bash
cd C:\Users\swatika\re-analyzer

# Basic analysis (TCAD + permits + comps)
python analyze_deal.py "1309 Perez St" --zip 78721

# Full analysis with deal parameters
python analyze_deal.py "1309 Perez St" --zip 78721 --purchase-price 500000 --build-sf 6400 --exit-psf 450

# Custom build cost
python analyze_deal.py "2100 E MLK Blvd" --zip 78702 --purchase-price 750000 --build-sf 4000 --exit-psf 500 --build-cost-psf 275
```

## What It Does

For any Austin address, the tool automatically:

1. **TCAD Lookup** — Pulls appraisal values, ownership, zoning, deed/transfer history
2. **Street Scan** — Finds ALL properties on the same street with owner info and deed records
3. **Permit Data** — Gets new construction permits (builder, size, date, status) from Austin Open Data API
4. **Sold Comps** — Scrapes Redfin for recently sold new construction in the zip code
5. **Risk Analysis** — Flags foreclosures, unsold developer inventory, competing construction
6. **Report** — Generates a formatted Word document with tables, color coding, and recommendation

## Output

A Word document saved to `~/Downloads/{Street}_St_Investment_Report.docx` containing:

- Subject property TCAD data & deed history
- All properties on the street (developer vs individual ownership)
- Construction permits (active + completed)
- Redfin sold comps with $/sf statistics
- Exit scenario analysis with profit/loss projections
- Risk assessment with auto-detected red flags
- GO / CAUTION / NO-GO recommendation

## Requirements

```bash
pip install requests playwright python-docx openpyxl
npx playwright install chromium
```

## Arguments

| Argument | Required | Description |
|---|---|---|
| `address` | Yes | Property address (e.g., "1309 Perez St") |
| `--zip` | Yes | ZIP code (e.g., 78721) |
| `--purchase-price` | No | Purchase price in dollars |
| `--build-sf` | No | Total planned build square footage |
| `--exit-psf` | No | Expected exit price per square foot |
| `--build-cost-psf` | No | Build cost per sf (default: $250) |
| `--output` | No | Custom output path for Word doc |

## Limitations

- **Austin/Travis County only** — uses TCAD and Austin Open Data APIs
- **Texas non-disclosure** — actual sale prices aren't in deed records; TCAD appraisals are proxies
- **Redfin may block** — headless browser scraping can be rate-limited
- **No MLS data** — CMA reports from agents provide the best comp data; feed those in separately
