"""Excel and PDF output for reports, plus the GST tax invoice PDF."""
import io
import os
from datetime import date, datetime
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.money import amount_in_words, inr
from app.models import Company, SalesInvoice
from app.services.reports import Report

# Brand palette
SIDEBAR = "34443F"
ACCENT = "84968A"
SOFT = "DCE4DF"
TEXT = "26332D"
BG = "F8FAF9"

_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
_fonts_ready = False


def _fonts():
    global _fonts_ready
    if not _fonts_ready:
        pdfmetrics.registerFont(TTFont("Body", os.path.join(_FONT_DIR, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("Body-Bold", os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold")
        _fonts_ready = True


def _fmt(value, kind: str) -> str:
    if value is None or value == "":
        return ""
    if kind == "money":
        return inr(value)
    if kind == "date" and isinstance(value, (date, datetime)):
        return value.strftime("%d-%m-%Y")
    if kind == "pct":
        return f"{Decimal(value).normalize():f}"
    if kind == "number":
        return f"{Decimal(value).normalize():f}"
    return str(value)


# ---------------- Excel ----------------
def report_xlsx(report: Report, company: Company) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = report.title[:31].replace("/", "-")
    n = len(report.columns)
    title_font = Font(name="Calibri", size=14, bold=True, color=TEXT)
    head_fill = PatternFill("solid", fgColor=SIDEBAR)
    head_font = Font(name="Calibri", bold=True, color="FFFFFF")
    total_fill = PatternFill("solid", fgColor=SOFT)
    thin = Side(style="thin", color=SOFT)

    ws.cell(row=1, column=1, value=company.legal_name).font = title_font
    ws.cell(row=2, column=1, value=f"{report.title} — {report.subtitle}").font = Font(size=11, color=TEXT)
    if company.gstin:
        ws.cell(row=3, column=1, value=f"GSTIN: {company.gstin}").font = Font(size=9, color="6B7A72")
    ws.cell(row=3, column=max(n, 2), value=f"Generated {datetime.now():%d-%m-%Y %H:%M}").font = Font(size=9, color="6B7A72")

    hr = 5
    for ci, col in enumerate(report.columns, start=1):
        c = ws.cell(row=hr, column=ci, value=col.label)
        c.fill, c.font = head_fill, head_font
        c.alignment = Alignment(horizontal="right" if col.kind in ("money", "number", "pct") else "left",
                                vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(ci)].width = max(col.width, len(col.label) + 2)
    ws.row_dimensions[hr].height = 22

    r = hr + 1
    for row in report.rows:
        for ci, col in enumerate(report.columns, start=1):
            v = row.get(col.key)
            c = ws.cell(row=r, column=ci)
            if col.kind == "money" and v is not None:
                c.value = float(v)
                c.number_format = '#,##,##0.00;[Red]-#,##,##0.00'
            elif col.kind in ("number", "pct") and v is not None:
                c.value = float(v)
                c.number_format = "0.##"
            elif col.kind == "date" and isinstance(v, date):
                c.value = v
                c.number_format = "DD-MM-YYYY"
            else:
                c.value = "" if v is None else str(v)
            c.border = Border(bottom=thin)
            if row.get("bold"):
                c.font = Font(bold=True)
        r += 1
    if report.totals:
        for ci, col in enumerate(report.columns, start=1):
            c = ws.cell(row=r, column=ci)
            c.fill = total_fill
            c.font = Font(bold=True, color=TEXT)
            if ci == 1:
                c.value = "Total"
            if col.key in report.totals:
                c.value = float(report.totals[col.key])
                c.number_format = '#,##,##0.00;[Red]-#,##,##0.00'
        r += 1
    r += 1
    for note in report.notes:
        ws.cell(row=r, column=1, value=note).font = Font(italic=True, size=9, color="6B7A72")
        r += 1
    ws.freeze_panes = ws.cell(row=hr + 1, column=1)
    ws.auto_filter.ref = f"A{hr}:{get_column_letter(n)}{hr + len(report.rows)}"
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape" if report.landscape else "portrait"
    ws.page_setup.fitToWidth = 1
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------- PDF (reports) ----------------
def _styles():
    _fonts()
    base = ParagraphStyle("base", fontName="Body", fontSize=8, leading=10, textColor=colors.HexColor("#" + TEXT))
    return {
        "base": base,
        "small": ParagraphStyle("small", parent=base, fontSize=7, textColor=colors.HexColor("#6B7A72")),
        "title": ParagraphStyle("title", parent=base, fontName="Body-Bold", fontSize=14, leading=18),
        "h2": ParagraphStyle("h2", parent=base, fontName="Body-Bold", fontSize=10, leading=13),
        "right": ParagraphStyle("right", parent=base, alignment=TA_RIGHT),
        "cell": ParagraphStyle("cell", parent=base, fontSize=7.5, leading=9),
    }


def _footer(company_name: str):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Body", 7)
        canvas.setFillColor(colors.HexColor("#6B7A72"))
        canvas.drawString(doc.leftMargin, 8 * mm, f"{company_name} — generated {datetime.now():%d-%m-%Y %H:%M}")
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def report_pdf(report: Report, company: Company) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    size = landscape(A4) if report.landscape else A4
    doc = SimpleDocTemplate(buf, pagesize=size, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm,
                            bottomMargin=14 * mm, title=report.title, author=company.legal_name)
    story = [Paragraph(company.legal_name, st["title"]),
             Paragraph(f"{report.title} &nbsp;·&nbsp; {report.subtitle}", st["h2"])]
    if company.gstin:
        story.append(Paragraph(f"GSTIN {company.gstin}", st["small"]))
    story.append(Spacer(1, 5 * mm))

    usable = size[0] - 24 * mm
    total_w = sum(c.width for c in report.columns)
    widths = [usable * c.width / total_w for c in report.columns]
    header = [Paragraph(f"<b>{c.label}</b>", ParagraphStyle("h", parent=st["cell"],
                                                            textColor=colors.white,
                                                            alignment=TA_RIGHT if c.kind in ("money", "number", "pct") else 0))
              for c in report.columns]
    data = [header]
    bold_rows = []
    for i, row in enumerate(report.rows, start=1):
        cells = []
        for c in report.columns:
            txt = _fmt(row.get(c.key), c.kind)
            style = st["cell"] if c.kind not in ("money", "number", "pct") else ParagraphStyle(
                "r", parent=st["cell"], alignment=TA_RIGHT)
            cells.append(Paragraph(txt.replace("&", "&amp;").replace("<", "&lt;"), style))
        data.append(cells)
        if row.get("bold") or row.get("type") in ("Opening", "Closing") or \
                str(row.get("section", "")).startswith(("Total", "Net")):
            bold_rows.append(i)
    if report.totals:
        tr = []
        for j, c in enumerate(report.columns):
            v = report.totals.get(c.key)
            tr.append(Paragraph(f"<b>{'Total' if j == 0 else _fmt(v, c.kind)}</b>",
                                ParagraphStyle("t", parent=st["cell"], alignment=TA_RIGHT if j else 0)))
        data.append(tr)
        bold_rows.append(len(data) - 1)

    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + SIDEBAR)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor("#" + SOFT)),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i in bold_rows:
        style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#" + SOFT)))
    t.setStyle(TableStyle(style))
    story.append(t)
    if not report.rows:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("No entries for this period.", st["base"]))
    if report.notes:
        story.append(Spacer(1, 4 * mm))
        for n in report.notes:
            story.append(Paragraph(n, st["small"]))
    doc.build(story, onFirstPage=_footer(company.legal_name), onLaterPages=_footer(company.legal_name))
    return buf.getvalue()


# ---------------- PDF (GST tax invoice) ----------------
def invoice_pdf(inv: SalesInvoice, company: Company, *, copy_label: str = "Original for Recipient") -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm,
                            bottomMargin=14 * mm, title=f"Invoice {inv.number}", author=company.legal_name)
    W = A4[0] - 24 * mm
    soft = colors.HexColor("#" + SOFT)
    dark = colors.HexColor("#" + SIDEBAR)

    def P(text, s="base"):
        return Paragraph(text, st[s])

    # Header: logo + company | title
    logo = None
    if company.logo_path and os.path.exists(company.logo_path):
        try:
            logo = Image(company.logo_path, width=22 * mm, height=22 * mm, kind="proportional")
        except Exception:
            logo = None
    comp_lines = [f"<b>{company.legal_name}</b>"]
    if company.address:
        comp_lines.append(company.address.replace("\n", ", "))
    comp_lines.append(", ".join(x for x in [company.city, company.state_name, company.pincode] if x))
    if company.gstin:
        comp_lines.append(f"GSTIN: <b>{company.gstin}</b> &nbsp; State: {company.state_name} ({company.state_code})")
    contact = " · ".join(x for x in [company.phone, company.email] if x)
    if contact:
        comp_lines.append(contact)
    left = [logo, P("<br/>".join(comp_lines))] if logo else [P("<br/>".join(comp_lines))]
    head = Table([[Table([left], colWidths=[24 * mm, W * 0.62 - 24 * mm]) if logo else left[0],
                   P(f"<b><font size=13>TAX INVOICE</font></b><br/><font size=7>{copy_label}</font>", "right")]],
                 colWidths=[W * 0.62, W * 0.38])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, dark),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))

    p = inv.party
    bill_to = (f"<b>Bill to</b><br/><b>{p.name}</b><br/>{(p.address or '').replace(chr(10), ', ')}<br/>"
               f"{', '.join(x for x in [p.city, p.district, p.state_name, p.pincode] if x)}<br/>"
               f"GSTIN: {p.gstin or 'Unregistered'}")
    meta = (f"<b>Invoice No:</b> {inv.number or 'DRAFT'}<br/><b>Date:</b> {inv.date:%d-%m-%Y}<br/>"
            f"<b>Due date:</b> {inv.due_date:%d-%m-%Y}<br/>"
            f"<b>Place of supply:</b> {p.state_name} ({inv.place_of_supply})<br/>"
            + (f"<b>Order ref:</b> {inv.reference}<br/>" if inv.reference else "")
            + f"<b>Tax type:</b> {'CGST + SGST' if inv.supply_type == 'intra' else 'IGST'}")
    parties = Table([[P(bill_to), P(meta)]], colWidths=[W * 0.6, W * 0.4])
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, soft),
                                 ("LINEAFTER", (0, 0), (0, 0), 0.5, soft), ("TOPPADDING", (0, 0), (-1, -1), 5),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))

    intra = inv.supply_type == "intra"
    r = ParagraphStyle("r", parent=st["cell"], alignment=TA_RIGHT)
    hdr = ["#", "Description", "HSN", "Qty", "Rate", "Disc%", "Taxable", "GST%"]
    hdr += ["CGST", "SGST"] if intra else ["IGST"]
    hdr += ["Amount"]
    rows = [[Paragraph(f"<b>{h}</b>", ParagraphStyle("hh", parent=st["cell"], textColor=colors.white,
                                                      alignment=TA_RIGHT if i >= 3 else 0)) for i, h in enumerate(hdr)]]
    for ln in inv.lines:
        row = [Paragraph(str(ln.line_no), st["cell"]), Paragraph(ln.description, st["cell"]),
               Paragraph(ln.hsn_code or "", st["cell"]),
               Paragraph(f"{ln.qty.normalize():f} {ln.unit}", r), Paragraph(inr(ln.rate), r),
               Paragraph(f"{ln.discount_pct.normalize():f}" if ln.discount_pct else "", r),
               Paragraph(inr(ln.taxable), r), Paragraph(f"{ln.gst_rate.normalize():f}", r)]
        row += [Paragraph(inr(ln.cgst), r), Paragraph(inr(ln.sgst), r)] if intra else [Paragraph(inr(ln.igst), r)]
        row += [Paragraph(inr(ln.total), r)]
        rows.append(row)
    if intra:
        cw = [6, 46, 13, 17, 16, 12, 20, 11, 15, 15, 22]
    else:
        cw = [6, 54, 13, 18, 17, 12, 22, 12, 18, 26]
    cw = [W * c / sum(cw) for c in cw]
    items = Table(rows, colWidths=cw, repeatRows=1)
    items.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), dark), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LINEBELOW", (0, 1), (-1, -1), 0.4, soft), ("TOPPADDING", (0, 0), (-1, -1), 3),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

    tot_rows = [["Taxable value", inr(inv.taxable_total)]]
    if inv.discount_total:
        tot_rows.insert(0, ["Discount", inr(inv.discount_total)])
    if intra:
        tot_rows += [["CGST", inr(inv.cgst_total)], ["SGST", inr(inv.sgst_total)]]
    else:
        tot_rows += [["IGST", inr(inv.igst_total)]]
    if inv.round_off:
        tot_rows.append(["Round off", inr(inv.round_off)])
    tot_rows.append(["Invoice total (₹)", inr(inv.grand_total)])
    totals = Table([[P(a), Paragraph(b, r)] for a, b in tot_rows], colWidths=[W * 0.22, W * 0.18])
    totals.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 1, dark), ("BACKGROUND", (0, -1), (-1, -1), soft),
                                ("FONTNAME", (0, -1), (-1, -1), "Body-Bold")]))
    words = P(f"<b>Amount in words</b><br/>{amount_in_words(inv.grand_total)}")
    bank = P(f"<b>Bank details</b><br/>{(company.bank_details_for_invoice or '—').replace(chr(10), '<br/>')}")
    summary = Table([[[words, Spacer(1, 4 * mm), bank], totals]], colWidths=[W * 0.6, W * 0.4])
    summary.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    terms = (company.invoice_terms or "").replace("\n", "<br/>")
    sign = P(f"For <b>{company.legal_name}</b><br/><br/><br/>{company.signatory_name or ''}<br/>"
             f"{company.signatory_designation or 'Authorised Signatory'}", "right")
    foot = Table([[P(f"<b>Terms</b><br/>{terms}" if terms else ""), sign]], colWidths=[W * 0.6, W * 0.4])
    foot.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEABOVE", (0, 0), (-1, 0), 0.5, soft),
                              ("TOPPADDING", (0, 0), (-1, -1), 6)]))

    story = [head, Spacer(1, 4 * mm), parties, Spacer(1, 4 * mm), items, Spacer(1, 4 * mm),
             KeepTogether([summary, Spacer(1, 6 * mm), foot])]
    if company.is_sample_data:
        story.insert(0, P("<font color='#B45309'>SAMPLE — company details are placeholders until confirmed.</font>",
                          "small"))
    if inv.status == "cancelled":
        story.insert(0, P("<font color='#B91C1C'><b>CANCELLED</b></font>", "h2"))
    doc.build(story, onFirstPage=_footer(company.legal_name), onLaterPages=_footer(company.legal_name))
    return buf.getvalue()
