"""
make_portfolio_images.py
Builds 4 portfolio images (4:3, 2000x1500 PNG) plus 16:9 copies (1600x900) for the PDF operations
demo. Every number, table row, text line and page image comes from a real run of run_demo.py
(stored in sample_output/). Nothing is typed in by hand.

Run:     python make_portfolio_images.py
Needs:   pillow, pymupdf   (fonts: DejaVu or any TrueType font, see CONFIG)

Every image carries a "Synthetic documents | local demo" tag. Keep it: the documents are
generated test data, not client files.
"""
import json
import os

import pymupdf
from PIL import Image, ImageDraw, ImageFont

# ============================ CONFIG ============================
BRAND = "Alif"
TAGLINE = "Python Automation Specialist"
DEMO_TAG = "Synthetic documents  |  local demo"
OUT_DIR = "portfolio_images"
FONT_REGULAR = None   # optional full path to a .ttf
FONT_BOLD = None
FONT_MONO = None
# ================================================================

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "sample_output")
W, H, SS = 2000, 1500, 2
BG, PANEL, PANEL_2, LINE = (11, 16, 32), (20, 28, 52), (30, 41, 72), (48, 61, 100)
TEXT, MUTED, ACCENT, AMBER, DARK = (240, 244, 255), (150, 163, 196), (34, 211, 166), (251, 191, 36), (8, 12, 24)
MX = 120
CW = W - 2 * MX


# ------------------------------------------------------------------ data
def load():
    def j(name):
        with open(os.path.join(SAMPLE, name), encoding="utf-8") as f:
            return json.load(f)
    return {"rep": j("run_report.json"), "boxes": j("demo_invoice_boxes.json"), "rec": j("demo_invoice_record.json"),
            "st": j("demo_statement_record.json"), "ocr": j("demo_ocr.json"), "fm": j("demo_formats.json")}


def usd(cents):
    return f"${cents / 100:,.2f}"


def duration(seconds):
    s = int(round(seconds))
    return f"{s // 60}m {s % 60:02d}s" if s >= 60 else f"{s}s"


def kb(n):
    return f"{n / 1024:.1f} KB" if n < 1024 * 1024 else f"{n / 1048576:.1f} MB"


def page_image(name, crop_pt):
    """Real rendered page, cropped to the top `crop_pt` points (page is 792 pt tall)."""
    img = Image.open(os.path.join(SAMPLE, name)).convert("RGB")
    return img.crop((0, 0, img.width, int(img.height * crop_pt / 792.0)))


# ------------------------------------------------------------------ fonts
def _first(paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


FONT_PATHS = {
    "regular": _first([FONT_REGULAR, r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
                       "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
                       "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                       "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"]),
    "bold": _first([FONT_BOLD, r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"]),
    "mono": _first([FONT_MONO, r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\cour.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
                    "/usr/share/fonts/liberation/LiberationMono-Regular.ttf"]),
}
_cache = {}


def font(size, bold=False, mono=False):
    key = "mono" if mono else ("bold" if bold else "regular")
    path = FONT_PATHS[key] or FONT_PATHS["regular"]
    px = int(round(size * SS))
    if (path, px) not in _cache:
        _cache[(path, px)] = ImageFont.truetype(path, px) if path else ImageFont.load_default(size=px)
    return _cache[(path, px)]


# ------------------------------------------------------------------ canvas
class Canvas:
    def __init__(self):
        self.img = Image.new("RGB", (W * SS, H * SS), BG)
        self.d = ImageDraw.Draw(self.img)

    def rect(self, box, fill=None, outline=None, r=0, width=2):
        x0, y0, x1, y1 = [v * SS for v in box]
        self.d.rounded_rectangle([x0, y0, x1, y1], radius=r * SS, fill=fill, outline=outline, width=int(width * SS))

    def ellipse(self, center, r, fill):
        x, y = center
        self.d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=fill)

    def line(self, p0, p1, fill, width):
        self.d.line([p0[0] * SS, p0[1] * SS, p1[0] * SS, p1[1] * SS], fill=fill, width=int(width * SS))

    def poly(self, pts, fill):
        self.d.polygon([(x * SS, y * SS) for x, y in pts], fill=fill)

    def text(self, xy, s, size, fill=TEXT, bold=False, mono=False, anchor="la"):
        self.d.text((xy[0] * SS, xy[1] * SS), s, font=font(size, bold, mono), fill=fill, anchor=anchor)

    def tw(self, s, size, bold=False, mono=False):
        return self.d.textlength(s, font=font(size, bold, mono)) / SS

    def fit(self, s, start, max_w, bold=True, mono=False):
        size = start
        while size > 16 and self.tw(s, size, bold, mono) > max_w:
            size -= 2
        return size

    def paste(self, img, box, radius=16):
        x0, y0, x1, y1 = box
        w, h = int((x1 - x0) * SS), int((y1 - y0) * SS)
        im = img.convert("RGB").resize((w, h), Image.LANCZOS)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius * SS, fill=255)
        self.img.paste(im, (int(x0 * SS), int(y0 * SS)), mask)

    def save(self, name):
        os.makedirs(os.path.join(HERE, OUT_DIR), exist_ok=True)
        full = self.img.resize((W, H), Image.LANCZOS)
        p43 = os.path.join(HERE, OUT_DIR, name + ".png")
        full.save(p43, optimize=True)
        wide = Image.new("RGB", (1600, 900), BG)
        wide.paste(full.resize((1200, 900), Image.LANCZOS), (200, 0))
        p169 = os.path.join(HERE, OUT_DIR, name + "_16x9.png")
        wide.save(p169, optimize=True)
        return p43, p169


# ------------------------------------------------------------------ shared pieces
def header(c, label):
    c.rect((MX, 88, MX + 200, 96), fill=ACCENT, r=4)
    c.text((MX, 124), label, 34, fill=ACCENT, bold=True)


def footer(c):
    c.rect((MX, 1384, W - MX, 1386), fill=LINE)
    c.rect((MX, 1416, MX + 28, 1444), fill=ACCENT, r=6)
    c.text((MX + 46, 1430), BRAND, 40, bold=True, anchor="lm")
    c.text((MX + 46 + c.tw(BRAND, 40, True) + 28, 1430), TAGLINE, 32, fill=MUTED, anchor="lm")
    c.text((W - MX, 1430), DEMO_TAG, 32, fill=AMBER, anchor="rm")


def title(c, line1, line2, start=130):
    size = min(c.fit(line1, start, CW), c.fit(line2, start, CW))
    c.text((MX, 186), line1, size, bold=True)
    y2 = 186 + int(size * 1.07)
    c.text((MX, y2), line2, size, fill=ACCENT, bold=True)
    return y2 + int(size * 1.0) + 30


def chips(c, items, x, y, size=36, pad=28, h=68, gap=22):
    cx = x
    for s in items:
        w = c.tw(s, size, True) + 2 * pad
        c.rect((cx, y, cx + w, y + h), fill=PANEL_2, outline=LINE, r=h / 2)
        c.text((cx + w / 2, y + h / 2), s, size, bold=True, anchor="mm")
        cx += w + gap
    return y + h


def window(c, box, label, mono_title=True):
    x0, y0, x1, y1 = box
    c.rect(box, fill=PANEL, r=24)
    c.rect((x0, y0, x1, y0 + 60), fill=PANEL_2, r=24)
    c.rect((x0, y0 + 30, x1, y0 + 60), fill=PANEL_2)
    c.rect(box, outline=LINE, r=24)
    for i, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        c.ellipse((x0 + 34 + i * 32, y0 + 30), 9, col)
    c.text(((x0 + x1) / 2, y0 + 30), label, 26, fill=MUTED, mono=mono_title, anchor="mm")


def arrow(c, x0, x1, y, head=54, thick=14):
    c.line((x0, y), (x1 - head * 0.55, y), ACCENT, thick)
    c.poly([(x1 - head, y - head * 0.75), (x1, y), (x1 - head, y + head * 0.75)], ACCENT)


def tick(c, cx, cy, r, fill=ACCENT, ink=DARK):
    c.ellipse((cx, cy), r, fill)
    pts = [(cx - 0.45 * r, cy + 0.02 * r), (cx - 0.12 * r, cy + 0.38 * r), (cx + 0.5 * r, cy - 0.36 * r)]
    c.line(pts[0], pts[1], ink, r * 0.27)
    c.line(pts[1], pts[2], ink, r * 0.27)


def pill(c, text, x, y, fill=ACCENT, ink=DARK, size=22, h=34):
    w = c.tw(text, size, True) + 24
    c.rect((x, y, x + w, y + h), fill=fill, r=h / 2)
    c.text((x + w / 2, y + h / 2), text, size, fill=ink, bold=True, anchor="mm")
    return (x, y, x + w, y + h)


def metric_cards(c, y0, y1, metrics):
    gap, n = 30, len(metrics)
    cw = (CW - gap * (n - 1)) / n
    inner = cw - 56
    vsize = min(c.fit(v, 76, inner) for _, v in metrics)
    lsize = min(c.fit(k, 28, inner, bold=False) for k, _ in metrics)
    for i, (label, value) in enumerate(metrics):
        x0 = MX + i * (cw + gap)
        c.rect((x0, y0, x0 + cw, y1), fill=PANEL, outline=LINE, r=24)
        c.rect((x0 + 28, y0 + 24, x0 + 76, y0 + 32), fill=ACCENT, r=4)
        c.text((x0 + 28, y0 + 88), value, vsize, fill=ACCENT, bold=True, anchor="lm")
        c.text((x0 + 28, y1 - 28), label, lsize, fill=MUTED, anchor="lm")


# ------------------------------------------------------------------ image 1: cover
def place_label(c, text, box, scale, origin, taken, where="right"):
    x0, y0, x1, y1 = box
    X0, Y0, X1, Y1 = origin[0] + x0 * scale, origin[1] + y0 * scale, origin[0] + x1 * scale, origin[1] + y1 * scale
    c.rect((X0 - 4, Y0 - 4, X1 + 4, Y1 + 4), outline=ACCENT, r=6, width=3)
    w, h = c.tw(text, 22, True) + 24, 34
    if where == "above-right":
        px, py = X1 - w, Y0 - h - 18
    elif where == "below-right":
        px, py = X1 - w, Y1 + 8
    else:
        px, py = X1 + 14, (Y0 + Y1) / 2 - h / 2
    for t in taken:  # slide right until it no longer overlaps a pill already placed
        if px < t[2] + 8 and px + w > t[0] - 8 and py < t[3] + 6 and py + h > t[1] - 6:
            px = t[2] + 12
    taken.append(pill(c, text, px, py))


def image1(d):
    rep, rec = d["rep"], d["rec"]
    c = Canvas()
    header(c, "PDF DATA EXTRACTION  |  CONVERSION  |  OCR")
    y = title(c, "PDF Data Extraction", "& Conversion", 140)
    c.text((MX, y), "Invoices, statements and scans turned into clean, checked data.", 44, fill=MUTED)
    tot, inv = rep["totals"], rep["invoices"]
    c.text((MX, y + 62), f"{tot['pdfs_processed']} PDFs, {tot['pages_processed']} pages processed in "
                         f"{duration(tot['total_runtime_s'])}", 36, fill=TEXT)
    values_ok = inv["header_fields_ok"] + inv["line_item_cells_ok"]
    values_tot = inv["header_fields_total"] + inv["line_item_cells_total"]
    c.text((MX, y + 108), f"Digital invoices: {values_ok:,} of {values_tot:,} values exact   |   "
                          f"Scans: {rep['ocr']['line_item_accuracy_pct']:.0f}% of line-item cells", 32, fill=MUTED)

    top = y + 170
    page = page_image("demo_invoice_p1.png", 480)
    bw = 700
    bh = int(bw * page.height / page.width)
    c.paste(page, (MX, top, MX + bw, top + bh))
    c.rect((MX, top, MX + bw, top + bh), outline=LINE, r=16)
    scale, taken = bw / 612.0, []
    where = {"Line items": "above-right", "Total": "below-right"}
    for label, box in d["boxes"]["boxes"].items():
        place_label(c, label, box, scale, (MX, top), taken, where.get(label, "right"))

    wx0 = MX + bw + 40
    window(c, (wx0, top, W - MX, top + bh), f"{rec['invoice_no']}   extracted")
    x0, x1 = wx0, W - MX
    fields = [("invoice_no", rec["invoice_no"]), ("invoice_date", rec["invoice_date"]), ("vendor", rec["vendor"]),
              ("customer", rec["customer"]), ("subtotal", usd(rec["subtotal_c"])),
              ("tax", f"{usd(rec['tax_c'])}  ({rec['tax_rate_bp'] / 100:g}%)"), ("total", usd(rec["total_c"]))]
    for i, (k, v) in enumerate(fields):
        yy = top + 98 + i * 37
        c.text((x0 + 40, yy), k, 25, fill=MUTED, mono=True, anchor="lm")
        c.text((x0 + 300, yy), v, 25, fill=ACCENT if k == "total" else TEXT, mono=True, anchor="lm", bold=False)
    if rec["subtotal_c"] + rec["tax_c"] == rec["total_c"]:
        pw = c.tw("subtotal + tax = total", 22, True) + 24 + 40
        tick(c, x1 - 40 - pw + 18, top + 98 + 6 * 37, 15)
        c.text((x1 - 40 - pw + 42, top + 98 + 6 * 37), "subtotal + tax = total", 22, fill=ACCENT, bold=True, anchor="lm")
    hy = top + 98 + 7 * 37 + 14
    c.rect((x0 + 28, hy, x1 - 28, hy + 36), fill=ACCENT, r=8)
    cols = {"qty": x0 + 590, "unit_price": x0 + 760, "amount": x1 - 50}
    c.text((x0 + 44, hy + 18), "description", 22, fill=DARK, bold=True, mono=True, anchor="lm")
    for k, xr in cols.items():
        c.text((xr, hy + 18), k, 22, fill=DARK, bold=True, mono=True, anchor="rm")
    for i, it in enumerate(rec["items"][:3]):
        ry = hy + 36 + 22 + i * 36
        c.text((x0 + 44, ry), it["desc"], 23, mono=True, anchor="lm")
        c.text((cols["qty"], ry), str(it["qty"]), 23, mono=True, anchor="rm")
        c.text((cols["unit_price"], ry), usd(it["unit_c"]), 23, mono=True, anchor="rm")
        c.text((cols["amount"], ry), usd(it["amount_c"]), 23, mono=True, anchor="rm")

    chips(c, ["Excel", "CSV", "JSON", "Word", "Text", "Searchable PDF"], MX, top + bh + 36)
    footer(c)
    return c.save("1_cover")


# ------------------------------------------------------------------ image 2: tables to Excel
def excel_window(c, box, label, tabs, headers, widths, aligns, rows):
    x0, y0, x1, y1 = box
    window(c, box, label, mono_title=False)
    gutter = 60
    ly = y0 + 60
    c.rect((x0 + 2, ly, x1 - 2, ly + 34), fill=PANEL_2)
    x = x0 + gutter
    for i, w in enumerate(widths):
        c.text((x + w / 2, ly + 17), chr(65 + i), 20, fill=MUTED, anchor="mm")
        x += w
    hy = ly + 34
    c.rect((x0 + 2, hy, x1 - 2, hy + 38), fill=(15, 76, 92))
    c.text((x0 + gutter / 2, hy + 19), "1", 20, fill=MUTED, anchor="mm")
    x = x0 + gutter
    for h_, w, al in zip(headers, widths, aligns):
        c.text((x + w - 10, hy + 19) if al == "r" else (x + 12, hy + 19), h_, 20, fill=TEXT, bold=True,
               anchor="rm" if al == "r" else "lm")
        x += w
    for i, row in enumerate(rows):
        ry = hy + 38 + i * 38
        c.rect((x0 + 2, ry, x1 - 2, ry + 38), fill=PANEL if i % 2 == 0 else (24, 33, 60))
        c.text((x0 + gutter / 2, ry + 19), str(i + 2), 20, fill=MUTED, anchor="mm")
        x = x0 + gutter
        for cell, w, al in zip(row, widths, aligns):
            c.text((x + w - 10, ry + 19) if al == "r" else (x + 12, ry + 19), cell, 19, anchor="rm" if al == "r" else "lm")
            x += w
    x = x0 + gutter
    for w in widths:
        c.line((x, ly + 34), (x, hy + 38 + len(rows) * 38), LINE, 1)
        x += w
    ty = y1 - 38
    c.rect((x0 + 2, ty, x1 - 2, y1 - 2), fill=PANEL_2)
    tx = x0 + 24
    for i, t in enumerate(tabs):
        tw_ = c.tw(t, 21, True) + 32
        if i == 1:
            c.rect((tx, ty + 4, tx + tw_, y1 - 2), fill=PANEL)
            c.rect((tx, y1 - 6, tx + tw_, y1 - 2), fill=ACCENT)
        c.text((tx + tw_ / 2, ty + 20), t, 21, fill=TEXT if i == 1 else MUTED, bold=True, anchor="mm")
        tx += tw_ + 6


def image2(d):
    rep, st = d["rep"], d["st"]
    c = Canvas()
    header(c, "MULTI-PAGE TABLES TO EXCEL")
    y = title(c, "Multi-Page Tables", "to Clean Excel", 124)
    s = rep["statements"]
    c.text((MX, y), f"{s['count']} bank statements, {s['pages']} pages, merged into one tidy table per account.",
           42, fill=MUTED)
    top = y + 80
    page = page_image("demo_statement_p1.png", 520)
    bw = 600
    bh = int(bw * page.height / page.width)
    c.paste(page, (MX, top, MX + bw, top + bh))
    c.rect((MX, top, MX + bw, top + bh), outline=LINE, r=16)
    bb = st.get("table_bbox_pt")
    if bb:
        sc = bw / 612.0
        X0, Y0, X1, Y1 = MX + bb[0] * sc, top + bb[1] * sc, MX + bb[2] * sc, min(top + bb[3] * sc, top + bh - 4)
        c.rect((X0 - 3, Y0 - 3, X1 + 3, Y1), outline=ACCENT, r=6, width=3)
        pill(c, "Table detected", X1 - c.tw("Table detected", 22, True) - 36, Y0 + 52)

    rows = [[r["date"], r["desc"], r["ref"], usd(r["debit_c"]) if r["debit_c"] else "",
             usd(r["credit_c"]) if r["credit_c"] else "", usd(r["balance_c"])] for r in st["rows"][:9]]
    ex = (MX + bw + 60, top, W - MX, top + bh)
    stem = st["name"].replace(".pdf", "")
    excel_window(c, ex, "statements.xlsx", ["Summary", stem, "ST-002", "ST-003", f"+{rep['excel_statements']['sheets'] - 4} more"],
                 ["Date", "Description", "Reference", "Debit", "Credit", "Balance"],
                 [132, 420, 122, 118, 118, 130], ["l", "l", "l", "r", "r", "r"], rows)
    metric_cards(c, top + bh + 44, top + bh + 224, [
        ("Table rows extracted", f"{s['rows']:,}"), ("Cells correct", f"{s['cell_accuracy_pct']:.0f}%"),
        ("Balance errors caught", f"{s['errors_flagged']} of {s['injected_errors']}"),
        ("False alarms", str(s["false_alarms"]))])
    footer(c)
    return c.save("2_tables_to_excel")


# ------------------------------------------------------------------ image 3: scans / OCR
def ocr_excerpt(lines):
    keep, prev = [], ""
    for ln in lines:
        money = ln.count("$")
        if (ln.startswith("Invoice No") or ln.startswith("Date:") or prev == "Bill To:"
                or (money >= 2 and not ln.startswith(("Subtotal", "Tax", "Total"))) or ln.startswith(("Subtotal", "Total Due"))):
            keep.append(ln)
        prev = ln
    return keep


def image3(d):
    rep, ocr_d, rec = d["rep"], d["ocr"], d["rec"]
    o = rep["ocr"]
    c = Canvas()
    header(c, "OCR  |  SEARCHABLE PDFS  |  SCANS")
    y = title(c, "Scanned PDFs,", "Made Searchable", 124)
    c.text((MX, y), f"Measured on {o['scans']} degraded scans: skew, blur, noise and uneven light.", 42, fill=MUTED)
    top = y + 80
    page = page_image("demo_scan_p1.png", 480)
    bw = 640
    bh = int(bw * page.height / page.width)
    c.paste(page, (MX, top, MX + bw, top + bh))
    c.rect((MX, top, MX + bw, top + bh), outline=LINE, r=16)
    pill(c, "Scanned image: no text layer", MX + 18, top + bh - 52, fill=AMBER)
    arrow(c, MX + bw + 14, MX + bw + 78, top + bh / 2, head=34, thick=10)

    wx0 = MX + bw + 92
    box = (wx0, top, W - MX, top + bh)
    window(c, box, "searchable layer (OCR)")
    with pymupdf.open(os.path.join(SAMPLE, "demo_scan_searchable.pdf")) as doc:
        hits = sum(len(p.search_for(rec["invoice_no"])) for p in doc)
    sy = top + 78
    c.rect((wx0 + 28, sy, W - MX - 28, sy + 46), fill=BG, outline=LINE, r=12)
    c.text((wx0 + 48, sy + 23), "Find:", 24, fill=MUTED, bold=True, anchor="lm")
    c.text((wx0 + 140, sy + 23), rec["invoice_no"], 24, mono=True, anchor="lm")
    c.text((W - MX - 48, sy + 23), f"{hits} match" + ("" if hits == 1 else "es"), 24, fill=ACCENT, bold=True, anchor="rm")
    ly = sy + 46 + 30
    size = 22
    for i, ln in enumerate(ocr_excerpt(ocr_d["lines"])[:11]):
        yy = ly + i * 29
        x = wx0 + 44
        if rec["invoice_no"] in ln:
            pre = ln[:ln.index(rec["invoice_no"])]
            px = x + c.tw(pre, size, mono=True)
            c.rect((px - 4, yy - 14, px + c.tw(rec["invoice_no"], size, mono=True) + 4, yy + 14), fill=(15, 96, 82), r=5)
        c.text((x, yy), ln, size, mono=True, anchor="lm")

    hf = o["header_fields_ok"] / o["header_fields_total"] * 100
    cp = rep["compress"]
    metric_cards(c, top + bh + 44, top + bh + 224, [
        ("Character error rate", f"{o['mean_cer_pct']:.1f}%"), ("Line-item cells correct", f"{o['line_item_accuracy_pct']:.1f}%"),
        ("Header fields correct", f"{hf:.1f}%"), ("File size, text kept", f"-{cp['saved_pct']:.0f}%")])
    footer(c)
    return c.save("3_scans_ocr")


# ------------------------------------------------------------------ image 4: formats and operations
def image4(d):
    rep, fm = d["rep"], d["fm"]
    c = Canvas()
    header(c, "EVERY FORMAT  |  EVERY OPERATION")
    y = title(c, "One PDF,", "Every Format", 124)
    c.text((MX, y), "Real outputs from a single invoice, plus the everyday PDF tools.", 42, fill=MUTED)
    top = y + 76
    # source thumbnail
    page = page_image("demo_invoice_p1.png", 792)
    tw_, th_ = 300, int(300 * page.height / page.width)
    c.paste(page, (MX, top, MX + tw_, top + th_), radius=12)
    c.rect((MX, top, MX + tw_, top + th_), outline=LINE, r=12)
    pill(c, f"{fm['stem']}.pdf", MX + 12, top + th_ - 44, fill=AMBER, size=20, h=30)

    sb = fm["bytes"]
    searchable = os.path.getsize(os.path.join(SAMPLE, "demo_scan_searchable.pdf"))
    cards = [(".xlsx", "Excel workbook", f"{kb(sb['xlsx'])}, 3 sheets"), (".csv", "Spreadsheet data", kb(sb["csv"])),
             (".json", "Structured data", kb(sb["json"])), (".docx", "Word document", kb(sb["docx"])),
             (".txt", "Plain text", kb(sb["txt"])), (".html", "Web page", kb(sb["html"])),
             (".png", "Page image", kb(sb["png"])), (".pdf", "Searchable PDF from a scan", kb(searchable))]
    gx0, cw_, ch_, gap = MX + tw_ + 50, 335, 185, 23
    for i, (ext, desc, size_) in enumerate(cards):
        x0 = gx0 + (i % 4) * (cw_ + gap)
        y0 = top + (i // 4) * (ch_ + 20)
        c.rect((x0, y0, x0 + cw_, y0 + ch_), fill=PANEL, outline=LINE, r=22)
        c.text((x0 + 26, y0 + 56), ext, 50, fill=ACCENT, bold=True, mono=True, anchor="lm")
        tick(c, x0 + cw_ - 38, y0 + 38, 16)
        c.text((x0 + 26, y0 + 114), desc, c.fit(desc, 29, cw_ - 52, bold=True), bold=True, anchor="lm")
        c.text((x0 + 26, y0 + 152), size_, 28, fill=MUTED, anchor="lm")
    conv = rep["conversions"]
    checks = ", ".join(f"{k.upper()} {v['ok']}/{conv['documents']}" for k, v in conv["formats"].items())
    cy = top + 2 * ch_ + 20 + 18
    c.text((MX, cy), f"Content verified on {conv['documents']} PDFs:  {checks}", 28, fill=MUTED)

    oy = cy + 56
    c.text((MX, oy), "EVERYDAY PDF OPERATIONS, ALL CHECKED", 30, fill=MUTED, bold=True)
    ms, cp, wm, rd, pr = rep["merge_split"], rep["compress"], rep["watermark"], rep["redact"], rep["protect"]
    ops_ = [("Merge", f"{ms['inputs']} PDFs into 1 ({ms['merged_pages']} pages)"),
            ("Split", f"1 PDF into {ms['split_files']} single pages"),
            ("Compress", f"{cp['before_bytes'] / 1e6:.1f} MB to {cp['after_bytes'] / 1e6:.1f} MB, text kept"),
            ("Watermark", f"{wm['pages_stamped']} of {wm['pages']} pages stamped"),
            ("Redact", f"{rd['redactions']} items removed, {rd['matches_remaining']} left"),
            ("Password protect", "AES-256, wrong password rejected")]
    ow, oh, ogap = (CW - 2 * 24) / 3, 100, 20
    for i, (t, dsc) in enumerate(ops_):
        x0 = MX + (i % 3) * (ow + 24)
        y0 = oy + 48 + (i // 3) * (oh + ogap)
        c.rect((x0, y0, x0 + ow, y0 + oh), fill=PANEL, outline=LINE, r=20)
        tick(c, x0 + 46, y0 + oh / 2, 22)
        c.text((x0 + 88, y0 + 33), t, 34, bold=True, anchor="lm")
        c.text((x0 + 88, y0 + 71), dsc, c.fit(dsc, 26, ow - 110, bold=False), fill=MUTED, anchor="lm")
    footer(c)
    return c.save("4_formats_operations")


if __name__ == "__main__":
    if not FONT_PATHS["regular"]:
        print("WARNING: no TrueType font found. Set FONT_REGULAR / FONT_BOLD / FONT_MONO.")
    data = load()
    for fn in (image1, image2, image3, image4):
        a, b = fn(data)
        print("saved:", os.path.relpath(a, HERE), "and", os.path.relpath(b, HERE))
