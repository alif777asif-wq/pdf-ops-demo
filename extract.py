"""
PDF data extraction: invoices (label / pattern based, three layouts), bank statements (ruled
multi-page tables), reconciliation checks, and scoring against ground truth.

Works on digital PDFs and on OCR'd scans (see ocr.py), because both end up with a text layer.
"""
import re
from datetime import datetime

import pdfplumber

_M = r"\$[\d,]+\.\d{2}"
ROW = re.compile(rf"^(?P<desc>.+?)\s+(?P<qty>\d+)\s+(?P<unit>{_M})\s+(?P<amt>{_M})$")
ROW_OCR = re.compile(rf"^(?P<desc>.+?)\s+(?P<qty>[\dIl|]+)\s+(?P<unit>{_M})\s+(?P<amt>{_M})$")
_OCR_DIGITS = str.maketrans("Il|", "111")  # OCR often reads the digit 1 as I, l or |


def repair_qty(token, unit_c, amount_c):
    """OCR mode: normalise look-alike characters, then let quantity x price = amount confirm it."""
    qty = int(token.translate(_OCR_DIGITS))
    if unit_c and qty * unit_c != amount_c and amount_c % unit_c == 0:
        qty = amount_c // unit_c
    return qty


SUBTOTAL = re.compile(rf"^(?:Subtotal|Sub-total|Net)\s+({_M})$")
TAX = re.compile(rf"^(?:Tax|VAT|Sales Tax)\s*\((\d+(?:\.\d+)?)%\)\s+({_M})$")
TOTAL = re.compile(rf"^(?:Total Due|Amount Due|Grand Total)\s+({_M})$")
INVNO = re.compile(r"(?:Invoice\s*(?:No\.?|Number|#)|Inv\.\s*Number)\s*:?\s*([A-Z]{2,5}-[\w-]+)")
BILLTO = re.compile(r"^(?:Bill To|Billed to|Customer)\s*:?\s*(.*)$")
DATE_FORMS = [(r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"), (r"\d{1,2} [A-Z][a-z]{2} \d{4}", "%d %b %Y"),
              (r"\d{2}/\d{2}/\d{4}", "%m/%d/%Y")]  # slash dates are read as MM/DD/YYYY


def parse_money(s):
    s = s.strip()
    neg = s.startswith("-") or s.startswith("(")
    whole, _, frac = re.sub(r"[^\d.]", "", s).partition(".")
    cents = int(whole or 0) * 100 + int((frac + "00")[:2])
    return -cents if neg else cents


def find_date(line):
    for pattern, fmt in DATE_FORMS:
        m = re.search(pattern, line)
        if m:
            return m.start(), m.group(0), datetime.strptime(m.group(0), fmt).date().isoformat()
    return None


def page_lines(page):
    return [ln.strip() for ln in (page.extract_text() or "").split("\n") if ln.strip()]


# ------------------------------------------------------------------ invoices
def extract_invoice(path):
    with pdfplumber.open(path) as pdf:
        pages = [page_lines(p) for p in pdf.pages]
    return extract_invoice_from_lines(pages)


def extract_invoice_from_lines(pages, ocr=False):
    """pages: list of pages, each a list of text lines (from a PDF text layer or from OCR).
    ocr=True switches on OCR-tolerant parsing of numeric fields."""
    rec = {"items": [], "raw": {}, "pages": len(pages)}
    first = pages[0] if pages else []
    for line in first:  # vendor = first line left once the "INVOICE" title is removed
        vendor = re.sub(r"\bINVOICE\b", "", line).strip()
        if vendor:
            rec["vendor"] = rec["raw"]["vendor"] = vendor
            break
    for i, line in enumerate(first):
        m = INVNO.search(line)
        if m and "invoice_no" not in rec:
            rec["invoice_no"] = rec["raw"]["invoice_no"] = m.group(1)
        d = find_date(line)
        if d:
            label = line[:d[0]].lower()
            key = "due_date" if "due" in label else "invoice_date"
            if key not in rec:
                rec[key], rec["raw"][key] = d[2], d[1]
        b = BILLTO.match(line)
        if b and "customer" not in rec:
            name = b.group(1).strip() or (first[i + 1] if i + 1 < len(first) else "")
            rec["customer"] = rec["raw"]["customer"] = name
    for lines in pages:
        for line in lines:
            m = (ROW_OCR if ocr else ROW).match(line)
            if m:
                unit_c, amt_c = parse_money(m["unit"]), parse_money(m["amt"])
                qty = repair_qty(m["qty"], unit_c, amt_c) if ocr else int(m["qty"])
                rec["items"].append({"desc": m["desc"], "qty": qty, "unit_c": unit_c,
                                     "amount_c": amt_c, "raw_amount": m["amt"]})
                continue
            if m := SUBTOTAL.match(line):
                rec["subtotal_c"] = parse_money(m.group(1))
            elif m := TAX.match(line):
                rec["tax_rate_bp"] = int(round(float(m.group(1)) * 100))
                rec["tax_c"] = parse_money(m.group(2))
            elif m := TOTAL.match(line):
                rec["total_c"] = parse_money(m.group(1))
                rec["raw"]["total"] = m.group(1)
    return rec


def reconcile_invoice(rec):
    """Arithmetic checks on the extracted numbers. Returns a list of problem codes."""
    problems = []
    items = rec.get("items", [])
    if any(i["qty"] * i["unit_c"] != i["amount_c"] for i in items):
        problems.append("line_amount_mismatch")
    if "subtotal_c" in rec and sum(i["amount_c"] for i in items) != rec["subtotal_c"]:
        problems.append("subtotal_mismatch")
    if {"subtotal_c", "tax_rate_bp", "tax_c"} <= rec.keys():
        if (rec["subtotal_c"] * rec["tax_rate_bp"] + 5000) // 10000 != rec["tax_c"]:
            problems.append("tax_mismatch")
    if {"subtotal_c", "tax_c", "total_c"} <= rec.keys() and rec["subtotal_c"] + rec["tax_c"] != rec["total_c"]:
        problems.append("total_mismatch")
    for key in ("invoice_no", "invoice_date", "customer", "total_c"):
        if key not in rec:
            problems.append(f"missing_{key}")
    return problems


def score_invoice(rec, truth):
    fields = {k: truth[k] for k in ("invoice_no", "invoice_date", "due_date", "vendor", "customer",
                                    "subtotal_c", "tax_rate_bp", "tax_c", "total_c")}
    ok = sum(rec.get(k) == v for k, v in fields.items())
    cells_ok = 0
    for i, ti in enumerate(truth["items"]):
        ri = rec["items"][i] if i < len(rec["items"]) else {}
        cells_ok += sum(ri.get(k) == ti[k] for k in ("desc", "qty", "unit_c", "amount_c"))
    cells_total = 4 * len(truth["items"])
    return {"fields_total": len(fields), "fields_ok": ok, "cells_total": cells_total, "cells_ok": cells_ok,
            "all_ok": ok == len(fields) and cells_ok == cells_total and len(rec["items"]) == len(truth["items"])}


def field_boxes(path, rec):
    """Bounding boxes (PDF points) of extracted values on page 1, for visual highlighting."""
    with pdfplumber.open(path) as pdf:
        words = pdf.pages[0].extract_words()

    def find(text, last=False):
        toks = text.split()
        spans = [words[i:i + len(toks)] for i in range(len(words) - len(toks) + 1)
                 if [w["text"] for w in words[i:i + len(toks)]] == toks]
        if not spans:
            return None
        ws = spans[-1] if last else spans[0]
        return (min(w["x0"] for w in ws), min(w["top"] for w in ws), max(w["x1"] for w in ws),
                max(w["bottom"] for w in ws))

    boxes = {}
    for label, key in (("Invoice no", "invoice_no"), ("Date", "invoice_date"), ("Customer", "customer"),
                       ("Vendor", "vendor")):
        if key in rec["raw"] and (b := find(rec["raw"][key])):
            boxes[label] = b
    if rec["items"]:
        top = find(rec["items"][0]["desc"])
        bottom = find(rec["items"][-1]["raw_amount"], last=True)
        if top and bottom:
            boxes["Line items"] = (48, top[1] - 3, 564, bottom[3] + 3)
    if "total" in rec["raw"] and (b := find(rec["raw"]["total"], last=True)):
        boxes["Total"] = b
    return boxes


# ------------------------------------------------------------------ statements
def extract_statement(path):
    rec = {"rows": [], "summary": {}}
    with pdfplumber.open(path) as pdf:
        rec["pages"] = len(pdf.pages)
        lines = page_lines(pdf.pages[0])
        for line in lines:
            for key, pat in (("opening_c", r"Opening Balance\s+(\$[\d,]+\.\d{2})"),
                             ("total_debits_c", r"Total Debits\s+(\$[\d,]+\.\d{2})"),
                             ("total_credits_c", r"Total Credits\s+(\$[\d,]+\.\d{2})"),
                             ("closing_c", r"Closing Balance\s+(\$[\d,]+\.\d{2})")):
                m = re.search(pat, line)
                if m:
                    rec["summary"][key] = parse_money(m.group(1))
            m = re.search(r"Account No:\s*([\d ]+)$", line)
            if m:
                rec["account_no"] = m.group(1).strip()
        for page in pdf.pages:
            for table in page.extract_tables():
                for r in table:
                    if not r or len(r) != 6 or (r[0] or "").strip() in ("", "Date"):
                        continue
                    c = [(x or "").strip() for x in r]
                    rec["rows"].append({"date": c[0], "desc": c[1], "ref": c[2],
                                        "debit_c": parse_money(c[3]) if c[3] else 0,
                                        "credit_c": parse_money(c[4]) if c[4] else 0,
                                        "balance_c": parse_money(c[5])})
    return rec


def reconcile_statement(rec):
    """Recompute the running balance. Returns (flagged_row_indexes, summary_problems)."""
    running = rec["summary"].get("opening_c", 0)
    flagged = []
    for i, r in enumerate(rec["rows"]):
        running = running - r["debit_c"] + r["credit_c"]
        if running != r["balance_c"]:
            flagged.append(i)
    problems = []
    s = rec["summary"]
    if s.get("total_debits_c") != sum(r["debit_c"] for r in rec["rows"]):
        problems.append("total_debits_mismatch")
    if s.get("total_credits_c") != sum(r["credit_c"] for r in rec["rows"]):
        problems.append("total_credits_mismatch")
    if s.get("closing_c") != running:
        problems.append("closing_balance_mismatch")
    return flagged, problems


def score_statement(rec, truth):
    cells_ok = 0
    for i, tr in enumerate(truth["rows"]):
        rr = rec["rows"][i] if i < len(rec["rows"]) else {}
        cells_ok += sum(rr.get(k) == tr[k] for k in ("date", "desc", "ref", "debit_c", "credit_c", "balance_c"))
    return {"cells_total": 6 * len(truth["rows"]), "cells_ok": cells_ok,
            "rows_truth": len(truth["rows"]), "rows_found": len(rec["rows"])}
