"""PDF -> other formats (Word, plain text, PNG, HTML), each with a content check."""
import logging
import os

import pdfplumber
import pymupdf


def to_docx(pdf, out):
    from pdf2docx import Converter
    logging.disable(logging.CRITICAL)  # pdf2docx logs every page at INFO level
    try:
        cv = Converter(pdf)
        try:
            cv.convert(out)
        finally:
            cv.close()
    finally:
        logging.disable(logging.NOTSET)


def to_txt(pdf, out):
    """Layout-preserving text (columns stay aligned)."""
    with pdfplumber.open(pdf) as doc, open(out, "w", encoding="utf-8") as f:
        for i, page in enumerate(doc.pages):
            f.write((page.extract_text(layout=True) or "").rstrip() + "\n")
            if i < len(doc.pages) - 1:
                f.write("\f\n")


def to_pngs(pdf, outdir, dpi=150):
    os.makedirs(outdir, exist_ok=True)
    paths = []
    with pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc, 1):
            p = os.path.join(outdir, f"page_{i:02d}.png")
            page.get_pixmap(dpi=dpi).save(p)
            paths.append(p)
    return paths


def to_html(pdf, out):
    with pymupdf.open(pdf) as doc, open(out, "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset='utf-8'>\n")
        for page in doc:
            f.write(page.get_text("html"))


def docx_text(path):
    import docx
    d = docx.Document(path)
    parts = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            parts += [c.text for c in row.cells]
    return "\n".join(parts)
