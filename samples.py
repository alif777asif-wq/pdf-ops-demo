"""
Synthetic document generator for the PDF operations demo.

Creates realistic but entirely fictional PDFs, plus a ground-truth JSON for each one so
extraction accuracy can be measured instead of guessed:

  * invoices   : 3 different layouts, 1-3 pages each, some with an injected arithmetic error
  * statements : multi-page ruled tables, running balances, some with an injected balance error

All names, addresses and account numbers are made up. Nothing here is real data.
"""
import json
import os
import random
from datetime import date, timedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

W, H = letter  # 612 x 792 pt

VENDORS = [
    ("Harborline Supply Co.", "48 Quayside Road, Portbridge"),
    ("Brightwave Studio Ltd.", "9 Lantern Yard, Eastvale"),
    ("Kestrel Logistics", "Unit 7, Falcon Park, Northfield"),
    ("Maple & Finch Catering", "22 Orchard Lane, Millbrook"),
    ("Tandem Office Goods", "301 Union Street, Redhill"),
    ("Vertex Print Works", "15 Foundry Way, Ashgrove"),
    ("Lumen Cleaning Services", "6 Beacon Court, Southmere"),
    ("Orbit IT Support", "88 Circuit Avenue, Techford"),
    ("Cedar & Stone Builders", "40 Quarry Hill, Westbury"),
    ("Nimbus Cloud Hosting", "2 Skyline Plaza, Highpoint"),
]
CUSTOMERS = [
    ("Cobalt Retail Group", "100 Market Square, Cityford"),
    ("Aurora Dental Clinic", "17 Mill Road, Greenhithe"),
    ("Pinecrest Academy", "5 School Lane, Pinecrest"),
    ("Summit Fitness Club", "63 Ridge Street, Highmoor"),
    ("Willow Creek Dairy", "Willow Farm, Creekside"),
    ("Ember & Oak Restaurant", "31 Harbour Walk, Seaton"),
    ("Quartz Analytics LLC", "250 Data Drive, Bytown"),
    ("Riverton Community Council", "1 Civic Plaza, Riverton"),
    ("Blue Heron Hotels", "9 Lakeshore Parade, Heronsgate"),
    ("Granite Peak Outfitters", "74 Trailhead Road, Peakview"),
]
ITEMS = [
    ("Standard A4 paper, 500 sheets", 4.50, 40), ("Black toner cartridge", 62.00, 6),
    ("Colour toner cartridge", 78.50, 4), ("Ergonomic office chair", 189.00, 3),
    ("Standing desk, 140 cm", 329.00, 2), ("Whiteboard markers, box of 12", 9.75, 15),
    ("Wireless keyboard and mouse set", 34.90, 10), ("27-inch monitor", 214.00, 4),
    ("USB-C docking station", 119.00, 5), ("Cat6 network cable, 10 m", 8.20, 30),
    ("Consulting services, per hour", 95.00, 40), ("Website maintenance, monthly", 240.00, 3),
    ("Cloud hosting, standard plan", 49.00, 12), ("Software licence, annual", 135.00, 25),
    ("Technical support, per hour", 70.00, 30), ("Deep cleaning, per visit", 120.00, 8),
    ("Window cleaning, per visit", 65.00, 8), ("Catering, per head", 18.50, 90),
    ("Venue hire, half day", 450.00, 2), ("Print run, 500 flyers", 85.00, 6),
    ("Business cards, box of 250", 29.00, 12), ("Pallet delivery, regional", 140.00, 10),
    ("Courier parcel, next day", 12.75, 60), ("Packing materials, bundle", 22.40, 20),
    ("Safety gloves, pack of 10", 14.80, 25), ("Hi-vis jackets, size L", 11.60, 30),
    ("Concrete mix, 25 kg bag", 6.30, 120), ("Timber battens, 3 m", 4.10, 150),
    ("Paint, 10 L white", 38.00, 20), ("Training workshop, per day", 780.00, 3),
    ("Photography session, per hour", 110.00, 6), ("Graphic design, per hour", 80.00, 25),
    ("Hand sanitiser, 5 L", 24.90, 15), ("Coffee beans, 1 kg", 17.90, 25),
    ("Filter cartridges, pack of 4", 31.00, 10), ("Server rack rental, monthly", 210.00, 6),
]
DEBITS = ["Card purchase - Orchard Grocers", "Direct debit - Beacon Energy", "Direct debit - Skyline Broadband",
          "Transfer out - Rent", "ATM withdrawal - High Street", "Card purchase - Union Fuel Stop",
          "Standing order - Gym membership", "Card purchase - Corner Bakery",
          "Online payment - Insurance premium", "Card purchase - Lantern Books"]
CREDITS = ["Salary - Quartz Analytics", "Transfer in - Savings", "Refund - Orchard Grocers", "Interest paid",
           "Client payment - Invoice settlement", "Transfer in - Family"]
HOLDERS = ["Jordan A. Whitfield", "Priya N. Raman", "Mateo L. Duarte", "Hannah K. Brandt", "Omar S. Haddad",
           "Lena M. Fischer", "Samuel T. Okafor", "Chloe R. Bennett", "Arjun P. Mehta", "Isla D. Frost",
           "Tomas E. Novak", "Grace H. Lindqvist"]

# layout parameters for the three invoice templates
TEMPLATES = {
    "A": dict(font="Helvetica", fontb="Helvetica-Bold", band=False, rule="grid", date_fmt="%Y-%m-%d",
              labels=("Invoice No:", "Date:", "Due Date:"), billto="Bill To:", billto_inline=False,
              cols=("Description", "Qty", "Unit Price", "Amount"), totals=("Subtotal", "Tax ({r}%)", "Total Due"),
              x_desc=56, x_qty=372, x_unit=462, x_amt=556),
    "B": dict(font="Helvetica", fontb="Helvetica-Bold", band=True, rule="none", date_fmt="%d %b %Y",
              labels=("Invoice #", "Issued", "Payment due"), billto="Billed to", billto_inline=False,
              cols=("Item", "Quantity", "Rate", "Total"), totals=("Sub-total", "VAT ({r}%)", "Amount Due"),
              x_desc=50, x_qty=390, x_unit=468, x_amt=562),
    "C": dict(font="Times-Roman", fontb="Times-Bold", band=False, rule="hlines", date_fmt="%m/%d/%Y",
              labels=("Inv. Number", "Invoice Date", "Due"), billto="Customer:", billto_inline=True,
              cols=("Details", "Units", "Price", "Line Total"), totals=("Net", "Sales Tax ({r}%)", "Grand Total"),
              x_desc=52, x_qty=360, x_unit=450, x_amt=560),
}


def money(c):
    return f"${c / 100:,.2f}"


# ------------------------------------------------------------------ invoices
def make_invoice(rng, idx):
    vendor, vaddr = rng.choice(VENDORS)
    cust, caddr = rng.choice(CUSTOMERS)
    n_items = rng.choice([3, 4, 5, 6, 7, 8] * 3 + [9, 10, 12, 14] * 2 + [18, 22, 26])
    items = []
    for _ in range(n_items):
        desc, base, max_q = rng.choice(ITEMS)
        qty = rng.randint(1, max_q)
        unit_c = int(round(base * rng.uniform(0.85, 1.25) * 100))
        items.append({"desc": desc, "qty": qty, "unit_c": unit_c, "amount_c": qty * unit_c})
    subtotal_c = sum(i["amount_c"] for i in items)
    rate_bp = rng.choice([0, 500, 700, 850, 1000, 1500])
    tax_c = (subtotal_c * rate_bp + 5000) // 10000
    total_c = subtotal_c + tax_c
    error = rng.random() < 0.035          # printed total does not match the maths
    if error:
        total_c += rng.choice([-1, 1]) * rng.choice([50, 100, 900, 1000, 2500])
    inv_date = date(2026, 1, 5) + timedelta(days=rng.randint(0, 270))
    return {
        "invoice_no": f"INV-2026-{10000 + idx}", "invoice_date": inv_date.isoformat(),
        "due_date": (inv_date + timedelta(days=rng.choice([14, 30, 45]))).isoformat(),
        "vendor": vendor, "vendor_addr": vaddr, "customer": cust, "customer_addr": caddr,
        "items": items, "subtotal_c": subtotal_c, "tax_rate_bp": rate_bp, "tax_c": tax_c,
        "total_c": total_c, "injected_error": error, "template": rng.choice(["A", "B", "C"]),
    }


def plan_pages(n_items, y_first, y_next, row_h, bottom=80, totals_h=92):
    pages, remaining, y = [], n_items, y_first
    while True:
        take = min(remaining, int((y - bottom) // row_h))
        pages.append(take)
        remaining -= take
        if remaining == 0:
            if y - take * row_h - totals_h < bottom:
                pages.append(0)  # totals spill onto a page of their own
            return pages
        y = y_next


def draw_invoice(path, inv):
    t = TEMPLATES[inv["template"]]
    f, fb = t["font"], t["fontb"]
    row_h, y_first, y_next = 18, 536, 676
    pages = plan_pages(len(inv["items"]), y_first, y_next, row_h)
    cv = canvas.Canvas(path, pagesize=letter)
    cv.setTitle(f"Invoice {inv['invoice_no']}")
    cv.setAuthor(inv["vendor"])
    idx = 0
    for pno, take in enumerate(pages, 1):
        if pno == 1:
            if t["band"]:
                cv.setFillColor(colors.HexColor("#1f3a5f"))
                cv.rect(0, H - 95, W, 95, fill=1, stroke=0)
                cv.setFillColor(colors.white)
            cv.setFont(fb, 17)
            cv.drawString(50, H - 52, inv["vendor"])
            if t["font"] == "Times-Roman":  # template C: title sits on its own line
                cv.setFont(f, 9)
                cv.drawString(50, H - 66, inv["vendor_addr"])
                cv.setFont(fb, 22)
                cv.drawString(50, H - 98, "INVOICE")
            else:
                cv.setFont(fb, 26)
                cv.drawRightString(W - 50, H - 52, "INVOICE")
                cv.setFont(f, 9)
                cv.drawString(50, H - 68, inv["vendor_addr"])
            cv.setFillColor(colors.black)
            fmt = t["date_fmt"]
            vals = (inv["invoice_no"], date.fromisoformat(inv["invoice_date"]).strftime(fmt),
                    date.fromisoformat(inv["due_date"]).strftime(fmt))
            for k, (lab, val) in enumerate(zip(t["labels"], vals)):
                y = 660 - k * 16
                cv.setFont(fb, 10)
                cv.drawString(50, y, lab)
                cv.setFont(f, 10)
                cv.drawString(150, y, val)
            if t["billto_inline"]:
                cv.setFont(fb, 10)
                cv.drawString(50, 596, t["billto"])
                cv.setFont(f, 10)
                cv.drawString(150, 596, inv["customer"])
                cv.setFont(f, 9)
                cv.drawString(150, 582, inv["customer_addr"])
            else:
                cv.setFont(fb, 10)
                cv.drawString(50, 598, t["billto"])
                cv.setFont(f, 10)
                cv.drawString(50, 584, inv["customer"])
                cv.setFont(f, 9)
                cv.drawString(50, 571, inv["customer_addr"])
            top = y_first + row_h
        else:
            cv.setFont(f, 9)
            cv.drawString(50, H - 50, f"Invoice {inv['invoice_no']} (continued)")
            top = y_next + row_h
        # table header
        xs = (t["x_desc"], t["x_qty"], t["x_unit"], t["x_amt"])
        if t["rule"] == "grid":
            cv.setFillColor(colors.Color(.9, .9, .9))
            cv.rect(50, top - row_h, 512, row_h, fill=1, stroke=0)
        cv.setFillColor(colors.black)
        cv.setFont(fb, 9)
        cv.drawString(xs[0], top - 13, t["cols"][0])
        for x, lab in zip(xs[1:], t["cols"][1:]):
            cv.drawRightString(x, top - 13, lab)
        y = top - row_h
        cv.setLineWidth(.5)
        cv.line(50, top, 562, top) if t["rule"] != "none" else None
        cv.line(50, y, 562, y)
        for _ in range(take):
            it = inv["items"][idx]
            idx += 1
            cv.setFont(f, 9)
            cv.drawString(xs[0], y - 13, it["desc"])
            cv.drawRightString(xs[1], y - 13, str(it["qty"]))
            cv.drawRightString(xs[2], y - 13, money(it["unit_c"]))
            cv.drawRightString(xs[3], y - 13, money(it["amount_c"]))
            y -= row_h
            if t["rule"] in ("grid", "hlines"):
                cv.line(50, y, 562, y)
        if t["rule"] == "grid":
            bottom_y = y
            for x in (50, 332, 400, 480, 562):
                cv.line(x, top, x, bottom_y)
        if pno == len(pages):
            ty = y - 26
            for k, (lab, val, bold) in enumerate((
                    (t["totals"][0], inv["subtotal_c"], False),
                    (t["totals"][1].format(r=f"{inv['tax_rate_bp'] / 100:g}"), inv["tax_c"], False),
                    (t["totals"][2], inv["total_c"], True))):
                cv.setFont(fb if bold else f, 10 if not bold else 11)
                cv.drawString(380, ty - k * 17, lab)
                cv.drawRightString(t["x_amt"], ty - k * 17, money(val))
        cv.setFont(f, 8)
        cv.drawCentredString(W / 2, 40, f"Page {pno} of {len(pages)}")
        cv.showPage()
    cv.save()
    return len(pages)


# ------------------------------------------------------------------ statements
def make_statement(rng, idx):
    n_tx = rng.randint(60, 190)
    bal = rng.randint(80_000, 600_000)
    opening = bal
    rows, d = [], date(2026, 1, 2) + timedelta(days=rng.randint(0, 200))
    start = d
    for i in range(n_tx):
        d += timedelta(days=rng.choice([0, 0, 1, 1, 2]))
        if rng.random() < 0.72 and bal > 5_000:
            amt = min(bal - 100, rng.choice([rng.randint(300, 9000), rng.randint(1000, 60000)]))
            debit, credit, desc = amt, 0, rng.choice(DEBITS)
        else:
            amt = rng.choice([rng.randint(2000, 80000), rng.randint(150000, 420000)])
            debit, credit, desc = 0, amt, rng.choice(CREDITS)
        bal = bal - debit + credit
        rows.append({"date": d.isoformat(), "desc": desc, "ref": f"TX{rng.randint(1000000, 9999999)}",
                     "debit_c": debit, "credit_c": credit, "balance_c": bal})
    error_row = None
    if idx % 6 == 2:  # inject one wrong running balance
        error_row = rng.randint(10, n_tx - 10)
        rows[error_row]["balance_c"] += rng.choice([-1, 1]) * rng.choice([500, 1250, 10000])
    return {
        "statement_no": f"ST-{idx + 1:03d}", "holder": HOLDERS[idx % len(HOLDERS)],
        "account_no": f"{rng.randint(1000, 9999)} {rng.randint(1000, 9999)} {rng.randint(1000, 9999)}",
        "bank": "Riverton Savings Bank", "period_start": start.isoformat(), "period_end": d.isoformat(),
        "opening_c": opening, "closing_c": bal if error_row is None else rows[-1]["balance_c"],
        "total_debits_c": sum(r["debit_c"] for r in rows), "total_credits_c": sum(r["credit_c"] for r in rows),
        "rows": rows, "injected_error_row": error_row,
    }


STMT_COLS = [("Date", 40, 100, "l"), ("Description", 100, 290, "l"), ("Reference", 290, 362, "l"),
             ("Debit", 362, 432, "r"), ("Credit", 432, 502, "r"), ("Balance", 502, 572, "r")]


def draw_statement(path, st):
    row_h, first_cap, next_cap = 16, 26, 40
    rows = st["rows"]
    chunks, i = [], 0
    while i < len(rows):
        cap = first_cap if not chunks else next_cap
        chunks.append(rows[i:i + cap])
        i += cap
    cv = canvas.Canvas(path, pagesize=letter)
    cv.setTitle(f"Account statement {st['statement_no']}")
    cv.setAuthor(st["bank"])
    for pno, chunk in enumerate(chunks, 1):
        if pno == 1:
            cv.setFillColor(colors.HexColor("#0f4c5c"))
            cv.rect(0, H - 80, W, 80, fill=1, stroke=0)
            cv.setFillColor(colors.white)
            cv.setFont("Helvetica-Bold", 18)
            cv.drawString(40, H - 38, st["bank"])
            cv.setFont("Helvetica", 11)
            cv.drawString(40, H - 58, "Account Statement")
            cv.setFillColor(colors.black)
            cv.setFont("Helvetica-Bold", 10)
            cv.drawString(40, H - 108, st["holder"])
            cv.setFont("Helvetica", 10)
            cv.drawString(40, H - 123, f"Account No: {st['account_no']}")
            cv.drawString(40, H - 138, f"Period: {st['period_start']} to {st['period_end']}")
            cv.setFillColor(colors.Color(.94, .96, .97))
            cv.rect(340, H - 148, 232, 66, fill=1, stroke=0)
            cv.setFillColor(colors.black)
            for k, (lab, val) in enumerate((("Opening Balance", st["opening_c"]), ("Total Debits", st["total_debits_c"]),
                                            ("Total Credits", st["total_credits_c"]), ("Closing Balance", st["closing_c"]))):
                cv.setFont("Helvetica-Bold" if k == 3 else "Helvetica", 9)
                cv.drawString(350, H - 96 - k * 15, lab)
                cv.drawRightString(562, H - 96 - k * 15, money(val))
            top = H - 170
        else:
            cv.setFont("Helvetica", 9)
            cv.drawString(40, H - 40, f"{st['bank']}  |  {st['statement_no']}  |  Account {st['account_no']}")
            top = H - 60
        # header row (repeated on every page)
        cv.setFillColor(colors.HexColor("#0f4c5c"))
        cv.rect(40, top - row_h, 532, row_h, fill=1, stroke=0)
        cv.setFillColor(colors.white)
        cv.setFont("Helvetica-Bold", 8.5)
        for name, x0, x1, al in STMT_COLS:
            (cv.drawString(x0 + 4, top - 11, name) if al == "l" else cv.drawRightString(x1 - 4, top - 11, name))
        y = top - row_h
        cv.setFillColor(colors.black)
        for k, r in enumerate(chunk):
            if k % 2 == 1:
                cv.setFillColor(colors.Color(.95, .95, .95))
                cv.rect(40, y - row_h, 532, row_h, fill=1, stroke=0)
                cv.setFillColor(colors.black)
            cells = [r["date"], r["desc"], r["ref"],
                     money(r["debit_c"]) if r["debit_c"] else "", money(r["credit_c"]) if r["credit_c"] else "",
                     money(r["balance_c"])]
            cv.setFont("Helvetica", 8)
            for (name, x0, x1, al), txt in zip(STMT_COLS, cells):
                if txt:
                    (cv.drawString(x0 + 4, y - 11, txt) if al == "l" else cv.drawRightString(x1 - 4, y - 11, txt))
            y -= row_h
        # ruled grid so the table is machine-detectable
        cv.setLineWidth(.5)
        cv.setStrokeColor(colors.Color(.6, .6, .6))
        for k in range(len(chunk) + 2):
            cv.line(40, top - k * row_h, 572, top - k * row_h)
        for x in [40] + [c[2] for c in STMT_COLS]:
            cv.line(x, top, x, y)
        cv.setStrokeColor(colors.black)
        cv.setFont("Helvetica", 8)
        cv.drawCentredString(W / 2, 30, f"Page {pno} of {len(chunks)}")
        cv.showPage()
    cv.save()
    return len(chunks)


# ------------------------------------------------------------------ driver
def generate(out_dir, n_invoices=120, n_statements=12, seed=7):
    rng = random.Random(seed)
    inv_dir, st_dir = os.path.join(out_dir, "invoices"), os.path.join(out_dir, "statements")
    os.makedirs(inv_dir, exist_ok=True)
    os.makedirs(st_dir, exist_ok=True)
    truth = {"invoices": {}, "statements": {}}
    pages = 0
    for i in range(n_invoices):
        inv = make_invoice(rng, i)
        name = f"{inv['invoice_no']}.pdf"
        pages += draw_invoice(os.path.join(inv_dir, name), inv)
        truth["invoices"][name] = inv
    for i in range(n_statements):
        st = make_statement(rng, i)
        name = f"{st['statement_no']}.pdf"
        pages += draw_statement(os.path.join(st_dir, name), st)
        truth["statements"][name] = st
    with open(os.path.join(out_dir, "ground_truth.json"), "w", encoding="utf-8") as f:
        json.dump(truth, f)
    return truth, pages


if __name__ == "__main__":
    t, p = generate("samples")
    print(f"{len(t['invoices'])} invoices, {len(t['statements'])} statements, {p} pages -> ./samples")
