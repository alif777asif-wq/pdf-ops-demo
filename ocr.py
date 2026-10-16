"""
Scanned PDFs: simulate a scan (skew, blur, noise, uneven light, JPEG), then OCR it into a
searchable PDF by adding an invisible text layer on top of the ORIGINAL scanned image
(so the file keeps its look and its size). Character error rate is measured against the text
of the digital original, which is known because the scan was rendered from it.
"""
import io
import re

import numpy as np
import pymupdf
import pytesseract
from PIL import Image, ImageFilter
from pytesseract import Output
from rapidfuzz.distance import Levenshtein

DPI = 300


def render_page(pdf_path, page_no=0, dpi=DPI):
    with pymupdf.open(pdf_path) as doc:
        pix = doc[page_no].get_pixmap(dpi=dpi)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def degrade(img, rng):
    """Make a clean render look like a mediocre office scan."""
    img = img.rotate(rng.uniform(-1.4, 1.4), resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.7, 1.1)))
    arr = np.asarray(img).astype(np.float32)
    gen = np.random.default_rng(rng.randint(0, 10 ** 9))
    arr += gen.normal(0, 7, arr.shape)
    arr *= np.linspace(0.92, 1.0, arr.shape[0])[:, None, None]  # uneven lighting
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("L")
    return img


def make_scan(src_pdf, dst_pdf, rng, dpi=DPI):
    """Render page 1 of src_pdf as a degraded, image-only PDF (no text layer)."""
    degrade(render_page(src_pdf, 0, dpi), rng).save(dst_pdf, "PDF", resolution=dpi, quality=60)


def deskew(gray):
    """Straighten the page: pick the rotation that makes text rows line up best."""
    small = gray.resize((gray.width // 4, gray.height // 4))
    ink = Image.fromarray(((np.asarray(small) < 160) * 255).astype(np.uint8))
    best, best_score = 0.0, -1.0
    for angle in np.arange(-3.0, 3.01, 0.1):
        score = float(np.var(np.asarray(ink.rotate(angle, resample=Image.BILINEAR)).sum(axis=1)))
        if score > best_score:
            best, best_score = float(angle), score
    return gray.rotate(best, resample=Image.BICUBIC, fillcolor=255), best


def remove_lines(gray, dpi=DPI):
    """Erase long table rules so OCR sees only text (the original image is kept untouched)."""
    import cv2
    arr = np.asarray(gray)
    ink = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    span = int(dpi * 0.35)
    horiz = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (span, 1)))
    vert = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, span)))
    mask = cv2.dilate(cv2.bitwise_or(horiz, vert), np.ones((3, 3), np.uint8))
    cleaned = cv2.bitwise_and(ink, cv2.bitwise_not(mask))
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))  # drop specks
    return Image.fromarray(255 - cleaned)


def ocr_to_searchable(scan_pdf, dst_pdf, psm=6, dpi=DPI):
    """Deskew, OCR, and write a searchable PDF: the straightened scan image with an invisible
    text layer on top. Returns (word_count, pages_lines, skew_degrees) where pages_lines is the
    OCR text line by line, one list per page, for downstream data extraction."""
    words, pages_lines, skews = 0, [], []
    out = pymupdf.open()
    with pymupdf.open(scan_pdf) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            gray = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            gray, angle = deskew(gray)
            skews.append(angle)
            d = pytesseract.image_to_data(remove_lines(gray, dpi), config=f"--psm {psm}",
                                          output_type=Output.DICT)
            buf = io.BytesIO()
            gray.save(buf, "JPEG", quality=60)
            new = out.new_page(width=pix.width * 72.0 / dpi, height=pix.height * 72.0 / dpi)
            new.insert_image(new.rect, stream=buf.getvalue())
            k = 72.0 / dpi
            lines, order = {}, []
            for i, txt in enumerate(d["text"]):
                txt = txt.strip().encode("latin-1", "replace").decode("latin-1")
                if not txt or float(d["conf"][i]) < 0:
                    continue
                key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
                if key not in lines:
                    lines[key] = []
                    order.append(key)
                lines[key].append(txt)
                x, y, w, h = d["left"][i] * k, d["top"][i] * k, d["width"][i] * k, d["height"][i] * k
                fs = max(4.0, h * 0.8)
                base = pymupdf.Point(x, y + h * 0.82)
                tl = pymupdf.get_text_length(txt, fontname="helv", fontsize=fs) or 1.0
                new.insert_text(base, txt, fontname="helv", fontsize=fs, render_mode=3,
                                morph=(base, pymupdf.Matrix(w / tl, 1)))
                words += 1
            pages_lines.append([" ".join(lines[k_]) for k_ in order])
    out.save(dst_pdf, garbage=3, deflate=True)
    out.close()
    return words, pages_lines, skews


def search_hits(pdf_path, needle):
    """Number of times `needle` is findable with PDF text search (proves the PDF is searchable)."""
    with pymupdf.open(pdf_path) as doc:
        return sum(len(page.search_for(needle)) for page in doc)


def text_of(pdf_path):
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def has_text_layer(pdf_path):
    with pymupdf.open(pdf_path) as doc:
        return any(page.get_text().strip() for page in doc)


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def cer(truth, hyp):
    """Character error rate of hyp against truth (lower is better)."""
    truth, hyp = norm(truth), norm(hyp)
    return Levenshtein.distance(truth, hyp) / max(1, len(truth))
