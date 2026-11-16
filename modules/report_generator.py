"""Report exports: PDF (reportlab) and Excel (openpyxl). Every report states its data sources and generation date."""
from __future__ import annotations

import io
from datetime import datetime
from xml.sax.saxutils import escape

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DISCLAIMER = ("Internal AI audit score - not an official Fiverr ranking score or Fiverr-issued metric. "
              "Recommendations do not guarantee rankings, impressions or orders.")
_MAP = {"→": "->", "≥": ">=", "≤": "<=", "×": "x", "↔": "<->", "…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "•": "-", "✓": "yes", "✗": "no"}


def _s(t) -> str:
    t = "" if t is None else str(t)
    for k, v in _MAP.items():
        t = t.replace(k, v)
    return escape(t.encode("latin-1", "ignore").decode("latin-1"))


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8, leading=10, textColor=colors.HexColor("#555555")))
    ss.add(ParagraphStyle("Cell", parent=ss["Normal"], fontSize=8, leading=10))
    ss.add(ParagraphStyle("H1x", parent=ss["Heading1"], textColor=colors.HexColor("#0B6E4F")))
    ss.add(ParagraphStyle("H2x", parent=ss["Heading2"], textColor=colors.HexColor("#1C2B39")))
    return ss


def _table(rows: list[list], widths: list[float], header: bool = True) -> Table:
    ss = _styles()
    data = [[Paragraph(_s(c), ss["Cell"]) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6F2EE"))]
    t.setStyle(TableStyle(style))
    return t


def _doc(title: str, subtitle: str, sources: str, build) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                            title=title, author="GigGrowth AI")
    ss = _styles()
    story = [Paragraph(_s(title), ss["H1x"]), Paragraph(_s(subtitle), ss["Normal"]),
             Paragraph(_s(f"Generated {datetime.now():%Y-%m-%d %H:%M} | Data sources: {sources}"), ss["Small"]),
             Paragraph(_s(DISCLAIMER), ss["Small"]), Spacer(1, 10)]
    build(story, ss)

    def footer(c, d):
        c.saveState()
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.grey)
        c.drawString(0.7 * inch, 0.45 * inch, "GigGrowth AI - Fiverr SEO & Intelligence")
        c.drawRightString(letter[0] - 0.7 * inch, 0.45 * inch, f"Page {d.page}")
        c.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def source_line(account: dict) -> str:
    return f"Fiverr MCP ({account['source']}, as of {account['fetched_at'][:16]}); internal rule-based audit; manual metadata where entered"


def audit_pdf(account: dict, audits: list[dict]) -> bytes:
    def build(story, ss):
        rows = [["Gig", "Score /100", "Band", "Confidence", "Projected*"]]
        from modules.seo_engine import score_band
        for a in audits:
            rows.append([a["slug"], a["total"], score_band(a["total"]), f"{a['confidence']:.0%}", a["projected"]])
        story += [Paragraph("Portfolio summary", ss["H2x"]), _table(rows, [3.0 * inch, 0.8 * inch, 1.1 * inch, 0.9 * inch, 0.9 * inch]),
                  Paragraph("*Projected score assumes the fixable recommendations are implemented (75% realisation). It is an internal estimate.", ss["Small"])]
        for a in audits:
            story += [PageBreak(), Paragraph(_s(a["slug"]), ss["H2x"]),
                      Paragraph(_s(f"Title used: {a['title']} ({'entered by you' if a['title_verified'] else 'derived from URL slug - not verified'}) | Primary keyword: {a['primary_keyword']} | "
                                   f"Score {a['total']}/100 -> projected {a['projected']}"), ss["Normal"]), Spacer(1, 6)]
            rows = [["Category", "Score", "Max", "Verified checks"]] + [[c.name, f"{c.score:.1f}", c.weight, f"{c.confidence:.0%}"] for c in a["categories"]]
            story.append(_table(rows, [3.0 * inch, 0.8 * inch, 0.8 * inch, 1.2 * inch]))
            story += [Spacer(1, 6), Paragraph("Strengths", ss["Heading3"])]
            st = [f"{k.name}: {k.note}" for c in a["categories"] for k in c.checks if k.status == "pass"][:6]
            story += [Paragraph(_s("- " + t), ss["Cell"]) for t in st] or [Paragraph("None detected.", ss["Cell"])]
            story += [Spacer(1, 6), Paragraph("Recommendations (priority order)", ss["Heading3"])]
            rows = [["Priority", "Area", "Finding", "Recommended change", "Benefit"]] + [[r["priority"], r["area"], r["finding"], r["change"], r["benefit"]] for r in a["recommendations"][:12]]
            story.append(_table(rows, [0.6 * inch, 1.1 * inch, 1.9 * inch, 2.0 * inch, 1.3 * inch]))
    return _doc("Fiverr Gig SEO Audit", f"Seller: {account['profile'].get('display_name')} (@{account['username']})", source_line(account), build)


def strategy_pdf(account: dict, audits: list[dict], findings: list[dict], plans: dict[int, list[dict]]) -> bytes:
    def build(story, ss):
        story.append(Paragraph("Key findings", ss["H2x"]))
        for f in findings:
            story.append(Paragraph(_s(f"[{f['type']}] {f['text']}"), ss["Cell"]))
        for days, label in [(7, "7-day action plan"), (30, "30-day growth plan"), (60, "60-day optimization plan"), (90, "90-day business development plan")]:
            story += [Spacer(1, 8), Paragraph(label, ss["H2x"])]
            rows = [["Action", "Why (evidence)", "Impact", "Effort", "Evidence", "Gig"]] + [[r["Action"], r["Why (evidence)"], r["Impact"], r["Effort"], r["Evidence"], r["Gig"]] for r in plans[days]]
            story.append(_table(rows, [2.2 * inch, 2.3 * inch, 0.55 * inch, 0.55 * inch, 0.65 * inch, 0.7 * inch]))
        story.append(Paragraph(_s("Evidence key: Verified = found in loaded data; Estimate = inferred; Hypothesis = to be tested. " + DISCLAIMER), ss["Small"]))
    return _doc("Fiverr Gig Growth Strategy", f"Seller: {account['profile'].get('display_name')} (@{account['username']})", source_line(account), build)


def plan_pdf(account: dict, plans: dict[int, list[dict]]) -> bytes:
    def build(story, ss):
        for days, label in [(7, "Days 1-7"), (30, "Days 8-30"), (60, "Days 31-60"), (90, "Days 61-90")]:
            story += [Paragraph(label, ss["H2x"])]
            for i, r in enumerate(plans[days], 1):
                story.append(Paragraph(_s(f"{i}. {r['Action']} ({r['Gig']}) - impact {r['Impact']}, effort {r['Effort']}, evidence: {r['Evidence']}"), ss["Cell"]))
            story.append(Spacer(1, 8))
    return _doc("30/60/90-Day Action Plan", f"Seller: {account['profile'].get('display_name')} (@{account['username']})", source_line(account), build)


# ---- Excel -----------------------------------------------------------------------------------------------------
HEAD = PatternFill("solid", fgColor="0B6E4F")


def _sheet(ws, df: pd.DataFrame, start_row: int = 1) -> None:
    for j, c in enumerate(df.columns, 1):
        cell = ws.cell(row=start_row, column=j, value=str(c))
        cell.font, cell.fill = Font(name="Arial", bold=True, color="FFFFFF"), HEAD
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for i, row in enumerate(df.itertuples(index=False), start_row + 1):
        for j, v in enumerate(row, 1):
            v = None if (isinstance(v, float) and pd.isna(v)) else (v.item() if hasattr(v, "item") else v)
            cell = ws.cell(row=i, column=j, value=v)
            cell.font = Font(name="Arial", size=10)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for j, c in enumerate(df.columns, 1):
        w = max([len(str(c))] + [len(str(x)) for x in df.iloc[:, j - 1].head(50)])
        ws.column_dimensions[get_column_letter(j)].width = min(48, max(10, w + 2))
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)


def _notes(wb: Workbook, lines: list[str]) -> None:
    ws = wb.create_sheet("About this report")
    ws.column_dimensions["A"].width = 120
    for i, l in enumerate([f"Generated: {datetime.now():%Y-%m-%d %H:%M}"] + lines + [DISCLAIMER], 1):
        ws.cell(row=i, column=1, value=l).font = Font(name="Arial", size=10, bold=(i == 1))
        ws.cell(row=i, column=1).alignment = Alignment(wrap_text=True)


def _xlsx(build) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    build(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def keywords_xlsx(df: pd.DataFrame, source: str) -> bytes:
    def b(wb):
        _sheet(wb.create_sheet("Keywords"), df)
        _notes(wb, [f"Source: {source}", "Keywords are template-generated candidates. Fiverr does not publish search volume; 'Opportunity' is a qualitative judgement, not measured data.",
                    "Competition evidence counts competitor profiles loaded via the Fiverr MCP; 'Not measured' means no competitor data was loaded."])
    return _xlsx(b)


def competitors_xlsx(sellers: pd.DataFrame, gigs: pd.DataFrame, insights: list[dict], source: str) -> bytes:
    def b(wb):
        _sheet(wb.create_sheet("Competitor sellers"), sellers)
        if gigs is not None and not gigs.empty:
            _sheet(wb.create_sheet("Competitor gigs"), gigs)
        _sheet(wb.create_sheet("Insights"), pd.DataFrame(insights or [{"type": "-", "text": "No insights"}]))
        _notes(wb, [f"Source: {source}", "Only public data returned by Fiverr's MCP server. Tags, private analytics and exact search positions are not available.",
                    "Gig titles are derived from URL slugs and may differ from the live title."])
    return _xlsx(b)


def performance_xlsx(df: pd.DataFrame) -> bytes:
    """Daily data with live formulas for CTR, conversion and AOV so the sheet recalculates when inputs change."""
    def b(wb):
        ws = wb.create_sheet("Daily data")
        cols = ["Date", "Gig", "Impressions", "Clicks", "Orders", "Revenue", "CTR %", "Click-to-order %", "AOV"]
        for j, c in enumerate(cols, 1):
            cell = ws.cell(row=1, column=j, value=c)
            cell.font, cell.fill = Font(name="Arial", bold=True, color="FFFFFF"), HEAD
        d = df.sort_values(["gig", "date"]).reset_index(drop=True)
        for i, r in enumerate(d.itertuples(index=False), 2):
            ws.cell(row=i, column=1, value=r.date.to_pydatetime()).number_format = "yyyy-mm-dd"
            ws.cell(row=i, column=2, value=r.gig)
            for j, v in zip((3, 4, 5, 6), (r.impressions, r.clicks, r.orders, r.revenue)):
                ws.cell(row=i, column=j, value=None if pd.isna(v) else float(v))
            ws.cell(row=i, column=7, value=f'=IF(C{i}>0,D{i}/C{i}*100,"")').number_format = "0.00"
            ws.cell(row=i, column=8, value=f'=IF(AND(D{i}>0,ISNUMBER(E{i})),E{i}/D{i}*100,"")').number_format = "0.00"
            ws.cell(row=i, column=9, value=f'=IF(AND(ISNUMBER(E{i}),E{i}>0,ISNUMBER(F{i})),F{i}/E{i},"")').number_format = "#,##0.00"
            for j in range(1, 10):
                ws.cell(row=i, column=j).font = Font(name="Arial", size=10)
        n = len(d) + 1
        ws.cell(row=n + 2, column=2, value="Totals").font = Font(name="Arial", bold=True)
        for j in (3, 4, 5, 6):
            L = get_column_letter(j)
            ws.cell(row=n + 2, column=j, value=f"=SUM({L}2:{L}{n})").font = Font(name="Arial", bold=True)
        ws.cell(row=n + 2, column=7, value=f'=IF(C{n + 2}>0,D{n + 2}/C{n + 2}*100,"")').number_format = "0.00"
        ws.cell(row=n + 2, column=8, value=f'=IF(D{n + 2}>0,E{n + 2}/D{n + 2}*100,"")').number_format = "0.00"
        ws.cell(row=n + 2, column=9, value=f'=IF(E{n + 2}>0,F{n + 2}/E{n + 2},"")').number_format = "#,##0.00"
        for j, w in enumerate([12, 36, 12, 10, 10, 12, 10, 16, 10], 1):
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.freeze_panes = "A2"
        _notes(wb, ["Source: data you imported from your Fiverr analytics export.",
                    "CTR % = Clicks / Impressions x 100.  Click-to-order % = Orders / Clicks x 100.  AOV = Revenue / Orders.",
                    "Blank = denominator is zero or the column was not in your export (never shown as a real zero)."])
    return _xlsx(b)
