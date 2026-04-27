# RE Investment Analyzer — Agent Instructions

You are working in a real estate investment analysis tool for Austin, TX.

## Quick Start

When the user gives you a property address, run the analyzer:

```bash
pip install -r requirements.txt
npx playwright install chromium
python analyze_deal.py "ADDRESS" --zip ZIPCODE --purchase-price PRICE --build-sf SQFT --exit-psf EXIT_PSF
```

## Key Files

| File | Purpose |
|------|---------|
| `analyze_deal.py` | Main CLI tool — orchestrates TCAD, permits, Redfin, and report generation |
| `requirements.txt` | Python dependencies |
| `README.md` | User-facing documentation |

## Architecture

The tool has 4 modules:
1. **TCADClient** — Searches Travis County property records via Playwright + TrueProdigy API
2. **AustinPermits** — Queries Austin Open Data API (Socrata) for construction permits
3. **RedfinComps** — Downloads sold comps via Redfin's CSV API (no browser needed)
4. **InvestmentAnalyzer** — Orchestrates all modules, computes stats, generates Word report

## After Running

1. Check console output for the quick summary (TCAD value, median $/sf, permit counts)
2. The Word report is saved to Downloads/ — review it for detailed tables
3. Provide the user with a GO / CAUTION / NO-GO recommendation based on:
   - Is the exit $/sf realistic vs market comps?
   - Are there red flags (foreclosures, unsold inventory, competing construction)?
   - Does the deal have margin of safety (purchase below TCAD, exit below median)?
