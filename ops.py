"""Everyday PDF operations: merge, split, compress, watermark, redact, password protect / unlock."""
import io
import os

import pymupdf
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.pdfgen import canvas


def merge(paths, out):
    w = PdfWriter()
    for p in paths:
        w.append(p)
    with open(out, "wb") as f:
        w.write(f)
    return len(w.pages)


def split(src, outdir):
    os.makedirs(outdir, exist_ok=True)
    reader = PdfReader(src)
    for i, page in enumerate(reader.pages, 1):
        w = PdfWriter()
        w.add_page(page)
        with open(os.path.join(outdir, f"page_{i:03d}.pdf"), "wb") as f:
            w.write(f)
    return len(reader.pages)


def compress(src, out, dpi_threshold=160, dpi_target=130, quality=45):
    """Down-sample and re-encode embedded images; text layer is untouched."""
    with pymupdf.open(src) as doc:
        doc.rewrite_images(dpi_threshold=dpi_threshold, dpi_target=dpi_target, quality=quality)
        doc.save(out, garbage=4, deflate=True, clean=True)


def watermark(src, out, text="CONFIDENTIAL"):
    reader = PdfReader(src)
    w = PdfWriter()
    for page in reader.pages:
        pw, ph = float(page.mediabox.width), float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(pw, ph))
        c.saveState()
        c.translate(pw / 2, ph / 2)
        c.rotate(45)
        c.setFillColor(colors.Color(0.8, 0.1, 0.1, alpha=0.18))
        c.setFont("Helvetica-Bold", 78)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        c.save()
        buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
        w.add_page(page)
    with open(out, "wb") as f:
        w.write(f)


def redact(src, out, needles):
    """True redaction: the text is removed from the file, not just covered by a black box."""
    count = 0
    with pymupdf.open(src) as doc:
        for page in doc:
            for needle in needles:
                for rect in page.search_for(needle):
                    page.add_redact_annot(rect, fill=(0, 0, 0))
                    count += 1
            page.apply_redactions()
        doc.save(out, garbage=4, deflate=True)
    return count


def protect(src, out, user_pw, owner_pw):
    w = PdfWriter(clone_from=src)
    w.encrypt(user_password=user_pw, owner_password=owner_pw, algorithm="AES-256")
    with open(out, "wb") as f:
        w.write(f)


def unprotect(src, out, password):
    r = PdfReader(src)
    if r.is_encrypted:
        r.decrypt(password)
    w = PdfWriter(clone_from=r)
    with open(out, "wb") as f:
        w.write(f)
