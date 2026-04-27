# Copilot Instructions — RE Investment Analyzer

This repository contains an automated real estate investment analysis tool for Austin, TX properties.

## What This Tool Does

`analyze_deal.py` is a CLI tool that pulls public data from multiple sources and generates a Word report:
- **TCAD** (Travis County Appraisal District) — property values, ownership, deed/transfer history
- **Austin Open Data API** — new construction permits (builder, size, date, status)
- **Redfin CSV API** — recently sold comparable properties with $/sf

## How to Run

```bash
python analyze_deal.py "ADDRESS" --zip ZIPCODE [--purchase-price N] [--build-sf N] [--exit-psf N] [--build-cost-psf N]
```

### Examples
```bash
# Basic analysis
python analyze_deal.py "1309 Perez St" --zip 78721

# Full deal evaluation
python analyze_deal.py "1309 Perez St" --zip 78721 --purchase-price 500000 --build-sf 6400 --exit-psf 450

# Custom build cost
python analyze_deal.py "2100 E MLK Blvd" --zip 78702 --purchase-price 750000 --build-sf 4000 --exit-psf 500 --build-cost-psf 275
```

## When User Asks for Property Analysis

When a user provides an Austin address and asks for investment analysis, due diligence, or deal evaluation:

1. Run `analyze_deal.py` with the provided address and parameters
2. Review the console output summary
3. Open and review the generated Word report
4. Provide an investment recommendation based on these criteria:

### Decision Framework

| Signal | Threshold | Rating |
|--------|-----------|--------|
| Exit $/sf vs Redfin median | Within 10% | ✅ Realistic |
| Exit $/sf vs Redfin median | 10-20% above | ⚠️ Aggressive |
| Exit $/sf vs Redfin median | 20%+ above | ❌ Unrealistic |
| TCAD appraisal vs purchase | Below TCAD | ✅ Discount |
| TCAD appraisal vs purchase | At/above TCAD | ⚠️ No margin |
| Same-street foreclosures | Any found | ❌ Major red flag |
| Competing units under construction | 3+ units | ⚠️ Supply risk |
| Unsold developer inventory | $1M+ on street | ❌ Demand concern |

### Recommendation Scale
- **GO** — All signals green, realistic exit, margin of safety exists
- **CAUTION** — Some yellow flags, deal works at lower exit assumptions
- **NO-GO** — Red flags present, deal doesn't pencil at market rates

## Technical Notes

- Texas is a non-disclosure state — actual sale prices are NOT in deed records. TCAD appraisals are the best proxy.
- TCAD search requires Playwright (Node.js) for browser automation
- Redfin region_id lookup is automatic but may need manual override for some zip codes
- The tool generates a `.docx` report in the user's Downloads folder by default
