"""
Austin Deal Analyzer PRO — Streamlit Web App
=============================================
Combined due diligence + financial modeling + BUY/DON'T BUY recommendation.
Pulls real market data, runs scenario analysis, and gives a clear verdict.
"""

import streamlit as st
import requests
import re
import io
import csv
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

# ── Page Config ──
st.set_page_config(
    page_title="Austin Deal Analyzer PRO",
    page_icon="🏡",
    layout="wide",
)

# ── Data Classes ──

@dataclass
class Permit:
    address: str = ""
    description: str = ""
    sqft: float = 0
    issue_date: str = ""
    permit_class: str = ""
    work_class: str = ""
    builder: str = ""
    housing_units: int = 0
    floors: int = 0
    status: str = ""

@dataclass
class AnalysisResult:
    street_permits: list = field(default_factory=list)
    zip_permits: list = field(default_factory=list)
    redfin_comps: list = field(default_factory=list)
    market_stats: dict = field(default_factory=dict)
    sources_status: dict = field(default_factory=dict)


# ── Austin Permits Module ──

class AustinPermits:
    BASE_URL = "https://data.austintexas.gov/resource/3syk-w9eu.json"

    def search_street(self, street_name: str, zip_code: str) -> list[Permit]:
        where = f"permit_location like '%{street_name.upper()}%' AND permittype='BP' AND work_class='New' AND original_zip='{zip_code}'"
        params = {"$where": where, "$order": "issue_date DESC", "$limit": 100}
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=15)
            if resp.status_code != 200:
                return []
            return self._parse_permits(resp.json())
        except Exception:
            return []

    def search_zip(self, zip_code: str, limit: int = 200) -> list[Permit]:
        where = f"original_zip='{zip_code}' AND permittype='BP' AND work_class='New'"
        params = {"$where": where, "$order": "issue_date DESC", "$limit": limit}
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=15)
            if resp.status_code != 200:
                return []
            permits = self._parse_permits(resp.json())
            return [p for p in permits if 'Single Family' in p.permit_class
                    or 'Two Family' in p.permit_class
                    or 'Secondary' in p.permit_class]
        except Exception:
            return []

    def _parse_permits(self, data: list) -> list[Permit]:
        permits = []
        for r in data:
            issue_date = ""
            if r.get("issue_date"):
                try:
                    dt = datetime.fromisoformat(r["issue_date"].replace("T", " ").split(".")[0])
                    issue_date = dt.strftime("%Y-%m-%d")
                except Exception:
                    issue_date = str(r["issue_date"])[:10]
            permits.append(Permit(
                address=r.get("permit_location", ""),
                description=r.get("description", ""),
                sqft=float(r.get("total_new_add_sqft", 0) or 0),
                issue_date=issue_date,
                permit_class=r.get("permit_class", ""),
                work_class=r.get("work_class", ""),
                builder=r.get("contractor_company_name", "Unknown"),
                housing_units=int(r.get("housing_units", 0) or 0),
                floors=int(r.get("number_of_floors", 0) or 0),
                status=r.get("status_current", ""),
            ))
        return permits


# ── Redfin Comps Module ──

class RedfinComps:
    REGION_CACHE = {}

    def _get_region_id(self, zip_code: str) -> Optional[str]:
        if zip_code in self.REGION_CACHE:
            return self.REGION_CACHE[zip_code]
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        }
        try:
            resp = requests.get(f'https://www.redfin.com/zipcode/{zip_code}', headers=headers, timeout=15)
            if resp.status_code == 200:
                matches = re.findall(r'region_id=(\d+)', resp.text)
                for rid in matches:
                    if rid != zip_code and len(rid) >= 4:
                        self.REGION_CACHE[zip_code] = rid
                        return rid
                match2 = re.search(r'"regionId"\s*:\s*(\d+)', resp.text)
                if match2 and match2.group(1) != zip_code:
                    rid = match2.group(1)
                    self.REGION_CACHE[zip_code] = rid
                    return rid
        except Exception:
            pass
        return None

    def get_sold_comps(self, zip_code: str) -> list[dict]:
        region_id = self._get_region_id(zip_code)
        if not region_id:
            return []
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        }
        url = (
            f'https://www.redfin.com/stingray/api/gis-csv?al=1&num_homes=200'
            f'&ord=redfin-recommended-asc&page_number=1'
            f'&region_id={region_id}&region_type=2'
            f'&sold_within_days=365&status=9&uipt=1&v=8&min_year_built=2020'
        )
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code != 200:
                return []
            lines = resp.text.strip().split('\n')
            header_idx = None
            for i, line in enumerate(lines):
                if line.startswith('SALE TYPE') or line.startswith('"SALE TYPE'):
                    header_idx = i
                    break
            if header_idx is None:
                return []
            reader = csv.DictReader(io.StringIO('\n'.join(lines[header_idx:])))
            comps = []
            for row in reader:
                try:
                    price_str = (row.get('PRICE') or '0').replace(',', '').replace('$', '')
                    price = int(float(price_str)) if price_str else 0
                    sqft_str = (row.get('SQUARE FEET') or '0').replace(',', '')
                    sqft = int(float(sqft_str)) if sqft_str else 0
                    year_str = row.get('YEAR BUILT') or '0'
                    year = int(float(year_str)) if year_str else 0
                    psf = round(price / sqft) if sqft > 0 else 0
                    if price > 0 and year >= 2020:
                        comps.append({
                            'address': f"{row.get('ADDRESS') or ''}, {row.get('CITY') or ''}",
                            'price': price, 'sqft': sqft, 'psf': psf,
                            'year_built': year,
                            'sold_date': row.get('SOLD DATE') or '',
                            'beds': row.get('BEDS') or '',
                            'baths': row.get('BATHS') or '',
                        })
                except (ValueError, ZeroDivisionError):
                    continue
            return comps
        except Exception:
            return []


# ── Report Generator (in-memory) ──

def generate_report_bytes(result: AnalysisResult, address: str, zip_code: str,
                          street_name: str, purchase_price: float,
                          build_sf: float, exit_psf: float, build_cost_psf: float) -> bytes:
    """Generate Word report and return as bytes."""
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(10)

    def set_cell_shading(cell, color):
        shading = OxmlElement('w:shd')
        shading.set(qn('w:fill'), color)
        shading.set(qn('w:val'), 'clear')
        cell._tc.get_or_add_tcPr().append(shading)

    def add_table(headers, rows, header_color='1F4E79'):
        table = doc.add_table(rows=1 + len(rows), cols=len(headers))
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, h in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = h
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in p.runs:
                    run.bold = True
                    run.font.size = Pt(8)
                    run.font.color.rgb = RGBColor(255, 255, 255)
            set_cell_shading(cell, header_color)
        for r_idx, row in enumerate(rows):
            for c_idx, val in enumerate(row):
                cell = table.rows[r_idx + 1].cells[c_idx]
                cell.text = str(val)
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.font.size = Pt(8)
                if r_idx % 2 == 1:
                    set_cell_shading(cell, 'F2F2F2')
        return table

    def fmt(val):
        return f"${val:,.0f}" if val else "N/A"

    # Title
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(f'{address}, {zip_code}')
    run.bold = True
    run.font.size = Pt(24)
    run.font.color.rgb = RGBColor(31, 78, 121)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run('Investment Analysis Report')
    run.font.size = Pt(16)
    run.font.color.rgb = RGBColor(89, 89, 89)

    date_p = doc.add_paragraph()
    date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_p.add_run(datetime.now().strftime('%B %Y'))
    doc.add_page_break()

    # Permits section
    doc.add_heading(f'Construction Permits — {street_name} St', level=1)
    if result.street_permits:
        active = [p for p in result.street_permits if p.status == 'Active']
        final = [p for p in result.street_permits if p.status == 'Final']
        if active:
            doc.add_heading('Under Construction (Active)', level=2)
            rows = [[p.address, f"{p.sqft:,.0f} sf", p.issue_date, p.builder, p.permit_class]
                    for p in active]
            add_table(['Address', 'Size', 'Permit Date', 'Builder', 'Type'], rows, header_color='D4A017')
        if final:
            doc.add_heading('Completed Projects', level=2)
            rows = [[p.address, f"{p.sqft:,.0f} sf", p.issue_date, p.builder, p.permit_class]
                    for p in final]
            add_table(['Address', 'Size', 'Permit Date', 'Builder', 'Type'], rows)
    else:
        doc.add_paragraph('No new construction permits found.')

    doc.add_page_break()

    # Redfin comps section
    doc.add_heading(f'Sold Comps — {zip_code} (New Construction)', level=1)
    if result.redfin_comps:
        stats = result.market_stats
        add_table(['Metric', 'Value'], [
            ['Median $/sf', f"${stats.get('median_psf', 0)}/sf"],
            ['Average $/sf', f"${stats.get('avg_psf', 0)}/sf"],
            ['Range', f"${stats.get('min_psf', 0)} — ${stats.get('max_psf', 0)}/sf"],
            ['Count', str(stats.get('count', 0))],
        ])
        doc.add_paragraph()
        comps_sorted = sorted(result.redfin_comps, key=lambda x: x.get("psf", 0), reverse=True)
        rows = [[c["address"], fmt(c.get("price", 0)), f"{c.get('sqft', 0):,} sf",
                 f"${c.get('psf', 0)}/sf", str(c.get('year_built', '')), c.get('sold_date', '')]
                for c in comps_sorted if c.get("psf", 0) > 0]
        add_table(['Address', 'Price', 'Size', '$/sf', 'Built', 'Sold'], rows)
    else:
        doc.add_paragraph('No Redfin comps available.')

    doc.add_page_break()

    # Investment analysis
    if purchase_price > 0 and build_sf > 0:
        doc.add_heading('Investment Analysis', level=1)
        total_build_cost = build_cost_psf * build_sf
        median_psf = result.market_stats.get("median_psf", 0)

        add_table(['Parameter', 'Value'], [
            ['Purchase Price', fmt(purchase_price)],
            ['Build Size', f"{build_sf:,.0f} sf"],
            [f'Build Cost @ ${build_cost_psf:,.0f}/sf', fmt(total_build_cost)],
            ['Exit Assumption', f"${exit_psf}/sf" if exit_psf else "N/A"],
            ['Market Median', f"${median_psf}/sf" if median_psf else "N/A"],
        ])

        doc.add_heading('Exit Scenarios', level=2)
        scenarios = []
        test_psfs = set()
        if median_psf:
            test_psfs.update([median_psf, median_psf + 25, median_psf + 50])
        if exit_psf:
            test_psfs.add(exit_psf)
        for psf in sorted(test_psfs):
            if psf > 0:
                revenue = psf * build_sf
                total_cost = purchase_price + total_build_cost + (total_build_cost * 0.10)
                profit = revenue - total_cost
                margin = (profit / total_cost) * 100
                scenarios.append([f"${psf}/sf", fmt(revenue), fmt(total_cost), fmt(profit),
                                  f"{margin:.1f}%", "✅" if margin > 10 else ("⚠" if margin > 0 else "❌")])
        add_table(['Exit $/sf', 'Revenue', 'Total Cost', 'Profit', 'Margin', ''], scenarios)

    # Sources
    doc.add_page_break()
    doc.add_heading('Data Sources', level=1)
    for name, desc, status in [
        ('Austin Open Data', 'Construction Permits API', result.sources_status.get('permits', '✅')),
        ('Redfin', 'Sold comps CSV API', result.sources_status.get('redfin', '✅')),
        ('TCAD', 'Property appraisals & deeds', '⚠ Run locally with CLI tool for TCAD data'),
    ]:
        p = doc.add_paragraph()
        run = p.add_run(f'{status} {name}: ')
        run.bold = True
        p.add_run(desc)

    p = doc.add_paragraph()
    run = p.add_run('\nDisclaimer: ')
    run.bold = True
    p.add_run('Texas is a non-disclosure state. Actual sale prices are not in public deed records. '
              'This report is for informational purposes only.')

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── Analysis Runner ──

@st.cache_data(ttl=3600, show_spinner=False)
def run_analysis(address: str, zip_code: str, street_name: str):
    """Run permits + Redfin analysis (cached for 1 hour)."""
    result = AnalysisResult()
    permits_api = AustinPermits()
    redfin_api = RedfinComps()

    # Permits
    result.street_permits = permits_api.search_street(street_name, zip_code)
    result.zip_permits = permits_api.search_zip(zip_code)
    result.sources_status['permits'] = '✅' if result.street_permits or result.zip_permits else '⚠'

    # Redfin
    result.redfin_comps = redfin_api.get_sold_comps(zip_code)
    if result.redfin_comps:
        psf_values = sorted([c["psf"] for c in result.redfin_comps if c.get("psf", 0) > 0])
        if psf_values:
            mid = len(psf_values) // 2
            result.market_stats = {
                "median_psf": psf_values[mid],
                "avg_psf": round(sum(psf_values) / len(psf_values)),
                "min_psf": min(psf_values),
                "max_psf": max(psf_values),
                "count": len(psf_values),
            }
        result.sources_status['redfin'] = '✅'
    else:
        result.sources_status['redfin'] = '⚠ No data'

    return result


def extract_street_name(address: str) -> str:
    parts = address.upper().replace(",", "").split()
    suffixes = {"ST", "AVE", "DR", "LN", "BLVD", "CT", "WAY", "RD", "CIR", "PL"}
    street_parts = [p for p in parts[1:] if p not in suffixes]
    return " ".join(street_parts) if street_parts else (parts[1] if len(parts) > 1 else parts[0])


# ══════════════════════════════════════════════════════════════
#  STREAMLIT UI — Combined Due Diligence + Financial Modeling
# ══════════════════════════════════════════════════════════════

st.title("🏡 Austin Deal Analyzer PRO")
st.caption("Real market data + financial modeling → **Should you buy or not?**")

# ── Sidebar: Input Form ──
with st.sidebar:
    st.header("📥 Deal Inputs")

    with st.form("deal_form"):
        st.subheader("🏠 Property")
        address = st.text_input("Property Address", placeholder="e.g., 2613 Nottingham Ln")
        zip_code = st.text_input("ZIP Code", placeholder="e.g., 78704")

        st.divider()
        st.subheader("💵 Deal Numbers")
        purchase_price = st.number_input("Purchase Price ($)", min_value=0, value=450000, step=25000)
        build_sf = st.number_input("Total Build Size (sf)", min_value=0, value=3000, step=500)
        units = st.number_input("Number of Units", min_value=1, value=2, step=1)
        build_cost_psf = st.number_input("Build Cost ($/sf)", min_value=0, value=250, step=25)
        exit_psf = st.number_input("Exit Price ($/sf)", min_value=0, value=575, step=10)

        st.divider()
        st.subheader("💵 Cost Details")
        hard_contingency_pct = st.slider("Hard Cost Contingency (%)", 0, 15, 6)
        soft_cost_pct = st.slider("Soft Costs (arch/eng/permits) (%)", 0, 20, 10)
        soft_contingency = st.number_input("Soft Contingency ($)", min_value=0, value=20000, step=5000)

        st.divider()
        st.subheader("💰 Construction Financing")
        ltv = st.slider("Loan to Cost (%)", 0, 100, 70)
        interest_rate = st.slider("Construction Interest Rate (%)", 3.0, 14.0, 8.5, step=0.5)
        draw_factor = st.slider("Draw Factor (%)", 40, 80, 60,
                                help="Avg % of loan funded during construction")

        st.divider()
        st.subheader("📅 Timeline")
        build_months = st.slider("Build Duration (months)", 6, 24, 12)
        hold_months = st.slider("Hold Period After Build (months)", 0, 36, 0,
                                help="0 = flip immediately, 24 = rent then sell")
        delay_months = st.slider("Expected Delays (months)", 0, 12, 0)

        st.divider()
        st.subheader("🏘️ Rental (Hold Strategy)")
        rent_per_unit = st.number_input("Monthly Rent / Unit ($)", min_value=0, value=3950, step=100)
        vacancy_pct = st.slider("Vacancy / Credit Loss (%)", 0, 15, 5)
        mgmt_fee_pct = st.slider("Management Fee (%)", 0, 15, 7)

        st.divider()
        st.subheader("📉 Market Risk")
        price_decline = st.slider("Annual Price Change (%)", -15, 10, 0)
        exit_cost_pct = st.slider("Exit Costs (realtor/title/closing) (%)", 0, 10, 5)

        submitted = st.form_submit_button("🔍 Analyze — Should I Buy?", use_container_width=True, type="primary")


# ── Main Content ──
if submitted and address and zip_code:
    street_name = extract_street_name(address)

    # ══════════════════════════════════════════════
    # STEP 1: Pull real market data
    # ══════════════════════════════════════════════
    with st.spinner(f"Pulling real market data for {address}, {zip_code}..."):
        result = run_analysis(address, zip_code, street_name)

    # ══════════════════════════════════════════════
    # STEP 2: Financial calculations
    # ══════════════════════════════════════════════
    hard_cost = build_cost_psf * build_sf
    hard_contingency = hard_cost * (hard_contingency_pct / 100)
    soft_costs = hard_cost * (soft_cost_pct / 100)
    total_dev_cost = hard_cost + hard_contingency + soft_costs + soft_contingency
    total_project_cost = purchase_price + total_dev_cost

    # Construction financing
    loan_amount = total_dev_cost * (ltv / 100)  # LTC on development costs (not land)
    equity = total_project_cost - loan_amount
    total_months = build_months + hold_months + delay_months
    timeline_years = total_months / 12

    # Construction interest (draw factor applies during build only)
    construction_interest = loan_amount * (interest_rate / 100) * (draw_factor / 100) * (build_months + delay_months) / 12

    # Holding costs during rental period
    if hold_months > 0:
        # Permanent loan interest during hold (full balance, no draw factor)
        hold_interest = loan_amount * (interest_rate / 100) * hold_months / 12
        # Rental income during hold
        gross_rent = rent_per_unit * units * hold_months
        effective_rent = gross_rent * (1 - vacancy_pct / 100)
        mgmt_cost = effective_rent * (mgmt_fee_pct / 100)
        # Property tax during hold
        prop_tax = (purchase_price + hard_cost * 0.5) * 0.02 * hold_months / 12
        # Insurance, repairs, misc during hold
        insurance = 375 * hold_months
        repairs = 150 * units * hold_months
        misc = 250 * hold_months
        total_hold_expenses = hold_interest + mgmt_cost + prop_tax + insurance + repairs + misc
        net_rental_income = effective_rent - total_hold_expenses
    else:
        hold_interest = 0
        gross_rent = 0
        effective_rent = 0
        net_rental_income = 0
        total_hold_expenses = 0

    total_interest = construction_interest + hold_interest

    # Use REAL market median if available, otherwise use user's exit assumption
    median_psf = result.market_stats.get("median_psf", 0)
    market_exit = median_psf if median_psf > 0 else exit_psf

    # Adjusted exit with market trend
    price_change_rate = price_decline / 100
    adjusted_exit = market_exit * ((1 + price_change_rate) ** timeline_years)
    adjusted_revenue = adjusted_exit * build_sf
    user_revenue = exit_psf * build_sf

    # Exit costs (realtor, title, closing)
    exit_costs_user = user_revenue * (exit_cost_pct / 100)
    exit_costs_market = adjusted_revenue * (exit_cost_pct / 100)

    total_cost = total_project_cost + total_interest + exit_costs_user
    market_total_cost = total_project_cost + total_interest + exit_costs_market

    market_profit = adjusted_revenue - market_total_cost + net_rental_income
    user_profit = user_revenue - total_cost + net_rental_income

    annual_rent = rent_per_unit * 12 * units
    cash_yield = (annual_rent / equity * 100) if equity > 0 else 0
    annualized_return = ((user_revenue / total_cost) ** (1 / max(timeline_years, 0.5)) - 1) if total_cost > 0 else 0
    breakeven_psf = (total_cost - net_rental_income) / build_sf if build_sf > 0 else 0

    # ══════════════════════════════════════════════
    # STEP 3: Risk scoring (0-100, higher = more risk)
    # ══════════════════════════════════════════════
    risk_score = 0
    risk_flags = []

    active_permits = [p for p in result.street_permits if p.status == 'Active']

    # Market data risks
    if median_psf > 0:
        exit_gap = ((exit_psf - median_psf) / median_psf) * 100
        if exit_gap > 20:
            risk_score += 30
            risk_flags.append(("🔴", f"Exit ${exit_psf}/sf is **{exit_gap:.0f}% above** market median ${median_psf}/sf — UNREALISTIC"))
        elif exit_gap > 10:
            risk_score += 15
            risk_flags.append(("🟡", f"Exit ${exit_psf}/sf is **{exit_gap:.0f}% above** market median ${median_psf}/sf — AGGRESSIVE"))
        elif exit_gap > 0:
            risk_score += 5
            risk_flags.append(("🟢", f"Exit ${exit_psf}/sf is **{exit_gap:.0f}% above** market median ${median_psf}/sf — Reasonable"))
        else:
            risk_flags.append(("🟢", f"Exit ${exit_psf}/sf is **at or below** market median ${median_psf}/sf — Conservative"))
    else:
        risk_score += 20
        risk_flags.append(("🟡", "No market comp data — cannot validate exit assumptions"))

    # Competition risks
    if len(active_permits) >= 5:
        risk_score += 20
        risk_flags.append(("🔴", f"**{len(active_permits)} competing units** under active construction on {street_name} St"))
    elif len(active_permits) >= 3:
        risk_score += 10
        risk_flags.append(("🟡", f"{len(active_permits)} competing units under construction on {street_name} St"))
    elif len(active_permits) > 0:
        risk_flags.append(("🟢", f"{len(active_permits)} unit(s) under construction — manageable competition"))

    # Profitability risks
    if market_profit < 0:
        risk_score += 25
        risk_flags.append(("🔴", f"**Negative profit** at market exit (${adjusted_exit:.0f}/sf) — LOSS of ${abs(market_profit):,.0f}"))
    elif market_profit < 100000:
        risk_score += 15
        risk_flags.append(("🟡", f"Thin profit margin (${market_profit:,.0f}) — vulnerable to overruns"))

    if delay_months > 3:
        risk_score += 10
        risk_flags.append(("🟡", f"Delays adding ${delay_cost:,.0f} in holding costs"))

    if breakeven_psf > median_psf and median_psf > 0:
        risk_score += 20
        risk_flags.append(("🔴", f"Break-even (${breakeven_psf:.0f}/sf) is **above** market median (${median_psf}/sf)"))

    # ══════════════════════════════════════════════
    # STEP 4: THE VERDICT
    # ══════════════════════════════════════════════
    st.markdown("---")

    if risk_score >= 50 or market_profit < 0:
        verdict = "DON'T BUY"
        verdict_color = "red"
        verdict_emoji = "❌"
        verdict_detail = "Too many risk factors. This deal doesn't pencil at current market rates."
    elif risk_score >= 25 or market_profit < 100000:
        verdict = "CAUTION"
        verdict_color = "orange"
        verdict_emoji = "⚠️"
        verdict_detail = "Deal is marginal. Only proceed if you can negotiate better terms."
    else:
        verdict = "BUY"
        verdict_color = "green"
        verdict_emoji = "✅"
        verdict_detail = "Deal looks solid based on market data and financials."

    # Big verdict banner
    st.markdown(f"""
    <div style="background-color: {'#ff4b4b' if verdict == "DON'T BUY" else '#ffa726' if verdict == 'CAUTION' else '#4caf50'};
                padding: 30px; border-radius: 15px; text-align: center; margin: 10px 0 20px 0;">
        <h1 style="color: white; margin: 0; font-size: 48px;">{verdict_emoji} {verdict}</h1>
        <p style="color: white; margin: 10px 0 0 0; font-size: 18px;">{verdict_detail}</p>
    </div>
    """, unsafe_allow_html=True)

    # Key numbers
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("All-In Cost", f"${total_cost:,.0f}")
    c2.metric("Market Exit Revenue", f"${adjusted_revenue:,.0f}")
    c3.metric("Profit (Market)", f"${market_profit:,.0f}")
    c4.metric("Break-Even", f"${breakeven_psf:.0f}/sf")
    c5.metric("Risk Score", f"{risk_score}/100")

    if median_psf > 0:
        st.info(f"📊 **Real Market Data:** Redfin median for new construction in {zip_code} is **${median_psf}/sf** "
                f"({result.market_stats.get('count', 0)} sold comps). Your exit assumption is ${exit_psf}/sf.")

    st.markdown("---")

    # ══════════════════════════════════════════════
    # TABS
    # ══════════════════════════════════════════════
    tab_verdict, tab_scenarios, tab_comps, tab_permits, tab_download = st.tabs([
        "🚦 Risk Analysis", "📈 Scenarios & Sensitivity", "📊 Sold Comps", "🏗️ Permits", "📄 Download"
    ])

    # ── Risk Analysis Tab ──
    with tab_verdict:
        st.subheader("Risk Factors")
        for emoji, msg in risk_flags:
            st.markdown(f"{emoji} {msg}")

        st.markdown("---")
        st.subheader("Deal Structure")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Development Costs**")
            st.markdown(f"""
            | Item | Amount |
            |------|--------|
            | Land / Purchase | ${purchase_price:,.0f} |
            | Hard Cost ({build_sf:,} sf × ${build_cost_psf}/sf) | ${hard_cost:,.0f} |
            | Hard Contingency ({hard_contingency_pct}%) | ${hard_contingency:,.0f} |
            | Soft Costs ({soft_cost_pct}%) | ${soft_costs:,.0f} |
            | Soft Contingency | ${soft_contingency:,.0f} |
            | Construction Interest | ${construction_interest:,.0f} |
            | Hold Interest ({hold_months} mo) | ${hold_interest:,.0f} |
            | Exit Costs ({exit_cost_pct}%) | ${exit_costs_user:,.0f} |
            | **Total All-In** | **${total_cost:,.0f}** |
            """)

        with c2:
            st.markdown("**Returns**")
            st.markdown(f"""
            | Scenario | Revenue | Profit |
            |----------|---------|--------|
            | Your Exit (${exit_psf}/sf) | ${user_revenue:,.0f} | ${user_profit:,.0f} |
            | Market Exit (${adjusted_exit:.0f}/sf) | ${adjusted_revenue:,.0f} | ${market_profit:,.0f} |
            | Break-Even | ${total_cost:,.0f} | $0 |
            """)

        st.markdown("---")
        st.subheader("Hold Strategy (Rental)")
        if hold_months > 0:
            rc1, rc2, rc3, rc4 = st.columns(4)
            rc1.metric("Gross Rent", f"${gross_rent:,.0f}", delta=f"{hold_months} months")
            rc2.metric("Net Rental Income", f"${net_rental_income:,.0f}")
            rc3.metric("Hold Expenses", f"${total_hold_expenses:,.0f}")
            rc4.metric("Cash Yield (annual)", f"{cash_yield:.1f}%")

            st.markdown(f"""
            **Rental NOI Detail ({hold_months} months):**
            | Item | Amount |
            |------|--------|
            | Gross Rent ({units} × ${rent_per_unit:,}/mo × {hold_months} mo) | ${gross_rent:,.0f} |
            | Less Vacancy ({vacancy_pct}%) | -${gross_rent * vacancy_pct / 100:,.0f} |
            | Effective Rent | ${effective_rent:,.0f} |
            | Less Mgmt Fee ({mgmt_fee_pct}%) | -${effective_rent * mgmt_fee_pct / 100:,.0f} |
            | Less Property Tax | -${(purchase_price + hard_cost * 0.5) * 0.02 * hold_months / 12:,.0f} |
            | Less Insurance/Repairs/Misc | -${(375 + 150 * units + 250) * hold_months:,.0f} |
            | Less Loan Interest | -${hold_interest:,.0f} |
            | **Net Rental Income** | **${net_rental_income:,.0f}** |
            """)
        else:
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("Annual Rent (if held)", f"${annual_rent:,.0f}")
            rc2.metric("Cash-on-Cash Yield", f"{cash_yield:.1f}%")
            rc3.metric("Equity Invested", f"${equity:,.0f}")
            st.info("Hold period is 0 — this is a flip strategy. Set hold months > 0 to see rental analysis.")

        st.caption("⚠ TCAD data (appraisals, deeds, foreclosure checks) requires running the CLI tool locally for complete risk assessment.")

    # ── Scenarios & Sensitivity Tab ──
    with tab_scenarios:
        st.subheader("Exit Scenario Matrix")
        # Build scenario table
        test_psfs = sorted(set([
            int(breakeven_psf) if breakeven_psf > 0 else 300,
            median_psf - 25 if median_psf > 0 else 325,
            median_psf if median_psf > 0 else 350,
            median_psf + 25 if median_psf > 0 else 375,
            median_psf + 50 if median_psf > 0 else 400,
            exit_psf,
        ]))
        test_psfs = [p for p in test_psfs if p > 0]

        scenario_data = []
        for psf in test_psfs:
            revenue = psf * build_sf
            exit_c = revenue * (exit_cost_pct / 100)
            sc_cost = total_project_cost + total_interest + exit_c
            profit = revenue - sc_cost + net_rental_income
            margin = (profit / sc_cost) * 100 if sc_cost > 0 else 0
            label = ""
            if median_psf > 0 and psf == median_psf:
                label = "← MARKET MEDIAN"
            elif psf == exit_psf:
                label = "← YOUR EXIT"
            elif psf == int(breakeven_psf):
                label = "← BREAK-EVEN"
            scenario_data.append({
                "Exit $/sf": f"${psf}",
                "Revenue": f"${revenue:,.0f}",
                "Profit": f"${profit:,.0f}",
                "Margin": f"{margin:.1f}%",
                "Signal": "✅" if margin > 10 else ("⚠" if margin > 0 else "❌"),
                "Note": label,
            })
        st.dataframe(scenario_data, use_container_width=True, hide_index=True)

        # Sensitivity charts
        st.subheader("📈 Sensitivity — Purchase Price vs Profit")
        price_range = np.arange(max(200000, purchase_price - 200000),
                                purchase_price + 200000, 25000)
        profits_by_price = []
        for p in price_range:
            cost = p + total_dev_cost + total_interest + (exit_psf * build_sf * exit_cost_pct / 100)
            profits_by_price.append(exit_psf * build_sf - cost + net_rental_income)
        st.line_chart({"Purchase Price": price_range, "Profit": profits_by_price},
                      x="Purchase Price", y="Profit")

        st.subheader("📊 Sensitivity — Exit $/sf vs Profit")
        exit_range = np.arange(max(200, int(breakeven_psf) - 100), int(breakeven_psf) + 200, 10)
        profits_by_exit = []
        for e in exit_range:
            rev = e * build_sf
            exit_c = rev * (exit_cost_pct / 100)
            profits_by_exit.append(rev - (total_project_cost + total_interest + exit_c) + net_rental_income)
        st.line_chart({"Exit $/sf": exit_range, "Profit": profits_by_exit},
                      x="Exit $/sf", y="Profit")

        if median_psf > 0:
            st.info(f"📍 Market median is **${median_psf}/sf** — your break-even is **${breakeven_psf:.0f}/sf**. "
                    f"You need the market to be **${breakeven_psf - median_psf:+.0f}/sf above median** to break even.")

    # ── Comps Tab ──
    with tab_comps:
        if result.redfin_comps:
            stats = result.market_stats
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Median $/sf", f"${stats.get('median_psf', 0)}")
            c2.metric("Average $/sf", f"${stats.get('avg_psf', 0)}")
            c3.metric("Min $/sf", f"${stats.get('min_psf', 0)}")
            c4.metric("Max $/sf", f"${stats.get('max_psf', 0)}")

            st.subheader(f"Recently Sold New Construction — {zip_code}")
            comp_data = []
            for c in sorted(result.redfin_comps, key=lambda x: x.get("psf", 0), reverse=True):
                if c.get("psf", 0) > 0:
                    comp_data.append({
                        "Address": c["address"],
                        "Price": f"${c['price']:,}",
                        "Size": f"{c['sqft']:,} sf",
                        "$/sf": c["psf"],
                        "Built": c.get("year_built", ""),
                        "Sold": c.get("sold_date", ""),
                        "Beds": c.get("beds", ""),
                        "Baths": c.get("baths", ""),
                    })
            st.dataframe(comp_data, use_container_width=True, hide_index=True)
        else:
            st.warning("No Redfin comps available. Redfin may be blocking requests from this server.")

    # ── Permits Tab ──
    with tab_permits:
        st.subheader(f"New Construction Permits — {street_name} St")
        if result.street_permits:
            active = [p for p in result.street_permits if p.status == 'Active']
            final = [p for p in result.street_permits if p.status == 'Final']

            if active:
                st.markdown(f"### 🟡 Under Construction ({len(active)})")
                st.dataframe([{"Address": p.address, "Size": f"{p.sqft:,.0f} sf",
                              "Builder": p.builder, "Date": p.issue_date,
                              "Type": p.permit_class} for p in active],
                             use_container_width=True, hide_index=True)
            if final:
                st.markdown(f"### ✅ Completed ({len(final)})")
                st.dataframe([{"Address": p.address, "Size": f"{p.sqft:,.0f} sf",
                              "Builder": p.builder, "Date": p.issue_date,
                              "Type": p.permit_class} for p in final],
                             use_container_width=True, hide_index=True)

            # Zip summary
            st.markdown(f"### 📊 Zip {zip_code} — Permit Trend")
            by_year = {}
            for p in result.zip_permits:
                yr = p.issue_date[:4] if p.issue_date else 'Unknown'
                by_year.setdefault(yr, []).append(p)
            year_data = []
            for yr in sorted(by_year.keys(), reverse=True):
                permits = by_year[yr]
                total_sf = sum(p.sqft for p in permits)
                year_data.append({"Year": yr, "Permits": len(permits),
                                  "Total SF": f"{total_sf:,.0f}",
                                  "Avg SF": f"{total_sf / len(permits):,.0f}" if permits else "0"})
            st.dataframe(year_data, use_container_width=True, hide_index=True)
        else:
            st.info("No new construction permits found.")

    # ── Download Tab ──
    with tab_download:
        st.subheader("Download Report")
        if result.redfin_comps or result.street_permits:
            report_bytes = generate_report_bytes(
                result, address, zip_code, street_name,
                purchase_price, build_sf, exit_psf, build_cost_psf
            )
            st.download_button(
                label="📥 Download Word Report (.docx)",
                data=report_bytes,
                file_name=f"{street_name.title()}_St_Analysis.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                type="primary",
            )
        else:
            st.warning("No data to generate report.")

        st.markdown("---")
        st.subheader("📊 Key Insights")
        st.markdown(f"""
        - **Break-even exit:** ${breakeven_psf:.0f}/sf
        - **Market median:** ${median_psf}/sf (Redfin, {result.market_stats.get('count', 0)} comps)
        - **Your exit:** ${exit_psf}/sf {'✅' if exit_psf <= median_psf else '⚠️'}
        - **This deal works IF:**
          - Purchase price ≤ ${max(0, purchase_price - (exit_psf - median_psf) * build_sf):,.0f} (or lower)
          - Exit ≥ ${breakeven_psf:.0f}/sf
          - No major delays beyond {delay_months} months
        """)

elif submitted:
    st.error("Please enter both an address and ZIP code.")
else:
    # Landing page
    st.markdown("""
    ### 🏡 How It Works

    1. **Enter property details** in the sidebar (address, ZIP, deal numbers)
    2. **Click "Analyze"** — the app pulls real market data automatically
    3. **Get a clear BUY / CAUTION / DON'T BUY verdict**

    ### What Makes This Different

    | Feature | Generic Calculator | This App |
    |---------|-------------------|----------|
    | Market comps | ❌ You guess | ✅ Pulls from Redfin |
    | Permit data | ❌ None | ✅ Austin permits API |
    | Competition check | ❌ None | ✅ Same-street construction |
    | Risk scoring | ❌ None | ✅ Automated 0-100 score |
    | BUY/DON'T BUY | ❌ None | ✅ Clear recommendation |
    | Sensitivity analysis | ✅ Manual | ✅ Auto with real median |

    > **Pro tip:** For complete analysis including TCAD records, deed history,
    > and foreclosure detection, run the CLI tool locally:
    > ```
    > python analyze_deal.py "ADDRESS" --zip XXXXX --purchase-price N
    > ```
    """)
