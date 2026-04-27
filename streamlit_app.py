"""
RE Investment Analyzer — Streamlit Web App
==========================================
Web interface for Austin TX real estate investment analysis.
Uses Austin Permits API + Redfin CSV API (TCAD requires local Playwright).
"""

import streamlit as st
import requests
import re
import io
import csv
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

# ── Page Config ──
st.set_page_config(
    page_title="Austin RE Investment Analyzer",
    page_icon="🏠",
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
#  STREAMLIT UI
# ══════════════════════════════════════════════════════════════

st.title("🏠 Austin RE Investment Analyzer")
st.caption("Automated due diligence using TCAD, Austin permits & Redfin comps")

# ── Sidebar: Input Form ──
with st.sidebar:
    st.header("📋 Deal Parameters")

    with st.form("deal_form"):
        address = st.text_input("Property Address", placeholder="e.g., 1309 Perez St")
        zip_code = st.text_input("ZIP Code", placeholder="e.g., 78721")

        st.divider()
        st.subheader("Deal Numbers (optional)")
        purchase_price = st.number_input("Purchase Price ($)", min_value=0, value=0, step=50000)
        build_sf = st.number_input("Build Size (sf)", min_value=0, value=0, step=500)
        exit_psf = st.number_input("Exit Price ($/sf)", min_value=0, value=0, step=25)
        build_cost_psf = st.number_input("Build Cost ($/sf)", min_value=0, value=250, step=25)

        submitted = st.form_submit_button("🔍 Analyze Deal", use_container_width=True, type="primary")

    st.divider()
    st.caption("**Data Sources**")
    st.caption("✅ Austin Permits API")
    st.caption("✅ Redfin CSV API")
    st.caption("⚠ TCAD — run CLI locally")

# ── Main Content ──
if submitted and address and zip_code:
    street_name = extract_street_name(address)

    with st.spinner(f"Analyzing {address}, {zip_code}..."):
        result = run_analysis(address, zip_code, street_name)

    # ── Source Status Badges ──
    cols = st.columns(3)
    with cols[0]:
        permit_count = len(result.street_permits)
        st.metric("Street Permits", permit_count, delta=f"{len([p for p in result.street_permits if p.status == 'Active'])} active")
    with cols[1]:
        st.metric("Zip Permits", len(result.zip_permits))
    with cols[2]:
        comp_count = len(result.redfin_comps)
        median = result.market_stats.get("median_psf", 0)
        st.metric("Redfin Comps", comp_count, delta=f"${median}/sf median" if median else None)

    st.divider()

    # ── Tabs ──
    tab_comps, tab_permits, tab_analysis, tab_download = st.tabs([
        "📊 Sold Comps", "🏗️ Permits", "💰 Deal Analysis", "📄 Download Report"
    ])

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
                        "Size (sf)": f"{c['sqft']:,}",
                        "$/sf": c["psf"],
                        "Built": c.get("year_built", ""),
                        "Sold": c.get("sold_date", ""),
                        "Beds": c.get("beds", ""),
                        "Baths": c.get("baths", ""),
                    })
            st.dataframe(comp_data, use_container_width=True, hide_index=True)

            if exit_psf and median:
                gap = ((exit_psf - median) / median) * 100
                if gap > 15:
                    st.error(f"🔴 Exit ${exit_psf}/sf is **{gap:.0f}% above** market median (${median}/sf) — AGGRESSIVE")
                elif gap > 5:
                    st.warning(f"🟡 Exit ${exit_psf}/sf is **{gap:.0f}% above** market median (${median}/sf) — Caution")
                else:
                    st.success(f"🟢 Exit ${exit_psf}/sf is within **{gap:.0f}%** of market median (${median}/sf) — Reasonable")
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
                active_data = [{"Address": p.address, "Size": f"{p.sqft:,.0f} sf",
                               "Builder": p.builder, "Permit Date": p.issue_date,
                               "Type": p.permit_class} for p in active]
                st.dataframe(active_data, use_container_width=True, hide_index=True)

            if final:
                st.markdown(f"### ✅ Completed ({len(final)})")
                final_data = [{"Address": p.address, "Size": f"{p.sqft:,.0f} sf",
                              "Builder": p.builder, "Permit Date": p.issue_date,
                              "Type": p.permit_class} for p in final]
                st.dataframe(final_data, use_container_width=True, hide_index=True)

            # Summary by year
            st.markdown(f"### 📊 Zip Code {zip_code} — Permit Trend")
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
            st.info("No new construction permits found for this street.")

    # ── Analysis Tab ──
    with tab_analysis:
        if purchase_price > 0 and build_sf > 0:
            total_build_cost = build_cost_psf * build_sf
            total_cost = purchase_price + total_build_cost + (total_build_cost * 0.10)
            median = result.market_stats.get("median_psf", 0)

            st.subheader("Deal Parameters")
            c1, c2, c3 = st.columns(3)
            c1.metric("Purchase", f"${purchase_price:,.0f}")
            c2.metric("Build Cost", f"${total_build_cost:,.0f}", delta=f"${build_cost_psf}/sf")
            c3.metric("All-In Cost", f"${total_cost:,.0f}", delta="incl. 10% contingency")

            st.subheader("Exit Scenarios")
            test_psfs = set()
            if median:
                test_psfs.update([median, median + 25, median + 50])
            if exit_psf:
                test_psfs.add(exit_psf)

            scenario_data = []
            for psf in sorted(test_psfs):
                if psf > 0:
                    revenue = psf * build_sf
                    profit = revenue - total_cost
                    margin = (profit / total_cost) * 100
                    scenario_data.append({
                        "Exit $/sf": f"${psf}",
                        "Revenue": f"${revenue:,.0f}",
                        "Profit": f"${profit:,.0f}",
                        "Margin": f"{margin:.1f}%",
                        "Signal": "✅ GO" if margin > 10 else ("⚠ CAUTION" if margin > 0 else "❌ NO-GO"),
                    })
            st.dataframe(scenario_data, use_container_width=True, hide_index=True)

            # Risk factors
            st.subheader("Risk Assessment")
            risks = []
            active_permits = [p for p in result.street_permits if p.status == 'Active']
            if active_permits:
                risks.append(f"🟡 {len(active_permits)} competing units under construction on {street_name} St")
            if exit_psf and median and ((exit_psf - median) / median) > 0.15:
                risks.append(f"🔴 Exit $/sf ({exit_psf}) is >15% above market median (${median})")
            if not result.redfin_comps:
                risks.append("🟡 No Redfin comp data available — cannot validate exit assumptions")

            st.info("⚠ TCAD data (appraisals, deeds, foreclosure checks) requires running the CLI tool locally. "
                    "Risk assessment below is **partial** without TCAD.")

            if risks:
                for risk in risks:
                    st.markdown(f"- {risk}")
            else:
                st.success("No red flags detected from available data sources.")
        else:
            st.info("Enter purchase price and build size in the sidebar to see deal analysis.")

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
            st.caption("Report includes permits, comps, and deal analysis.")
            st.caption("For full report with TCAD data, run: `python analyze_deal.py`")
        else:
            st.warning("No data to generate report. Run the analysis first.")

elif submitted:
    st.error("Please enter both an address and ZIP code.")
else:
    # Landing page
    st.markdown("""
    ### How to Use
    1. Enter a **property address** and **ZIP code** in the sidebar
    2. Optionally add deal numbers (purchase price, build size, exit $/sf)
    3. Click **🔍 Analyze Deal**
    4. Review tabs: Comps → Permits → Analysis → Download

    ### Data Sources
    | Source | Data | Status |
    |--------|------|--------|
    | **Austin Open Data** | Construction permits (builder, size, status) | ✅ Available |
    | **Redfin** | Recently sold new construction comps | ✅ Available |
    | **TCAD** | Property appraisals, ownership, deeds | ⚠ CLI only |

    > **Note:** For full analysis including TCAD property records, foreclosure checks,
    > and deed history, run the CLI tool locally:
    > ```
    > python analyze_deal.py "ADDRESS" --zip XXXXX --purchase-price N
    > ```
    """)
