# PDF operations toolkit: extraction, conversion, OCR (demo project)

A Python toolkit for the most common PDF jobs, built and **measured against ground truth** on
synthetic documents: invoices in three layouts, multi-page bank statements, and degraded scans.
All companies, people and account numbers are fictional. This is a personal demo project, not
client work, and no real documents were used.

## What it does
| Task | How |
|---|---|
| Invoice data extraction (header fields + line items) | pdfplumber, label and pattern based, three layouts |
| Multi-page tables to Excel | ruled-table detection, repeated headers dropped, rows merged, one sheet per statement |
| Arithmetic and balance checks | subtotal + tax = total, running balance recomputed row by row |
| Scanned PDFs to searchable PDFs | deskew, table-line removal, Tesseract OCR, invisible text layer over the original image |
| PDF to Word / text / HTML / PNG | pdf2docx, pdfplumber, PyMuPDF |
| Merge, split, compress, watermark | pypdf, PyMuPDF, reportlab |
| True redaction, password protect / unlock | PyMuPDF redactions (text removed from the file), AES-256 |
| Exports | Excel (typed cells, formats, frozen header, filters), CSV, JSON |

## Results (one measured run, `sample_output/run_report.json`)
| Measure | Result |
|---|---|
| Documents | 152 PDFs, 197 pages in 2m 23s |
| Invoices, header fields | 1,080 / 1,080 exact |
| Invoices, line-item cells | 4,220 / 4,220 exact (1,055 line items) |
| Invoice arithmetic check | 3 / 3 injected errors caught, 0 false alarms |
| Statement table cells | 10,026 / 10,026 exact (1,671 rows, 51 pages) |
| Statement balance check | 2 / 2 injected errors caught, 0 false alarms |
| Scans, character error rate | 4.2% (mean of 20 scans) |
| Scans, header fields | 170 / 180 correct |
| Scans, line-item cells | 556 / 596 correct (93.29%) |
| Scans, invoice number findable by text search | 17 / 20 |
| Compression of the searchable scans | 8.9 MB to 1.6 MB (82.6% smaller), text search unchanged |
| Merge and split | 120 invoices merged into 1 PDF (126 pages), split into 126 single-page files,     page count matches |
| Watermark | 21 of 21 pages stamped, text intact |
| Password protection | AES-256, wrong password rejected, correct password unlocks |
| Format conversion content checks (14 PDFs) | DOCX 14/14, TXT 14/14, HTML 14/14, PNG 14/14 |
| Redaction | 63 items removed from 12 statements, 0 matches remain |

## How to read these numbers
- Every document is generated with known contents, so accuracy is **measured**, not estimated.
- The digital-PDF results cover **three invoice layouts and one table style**. Perfect scores on
  layouts the extractor was written for do not promise the same on a stranger's documents: a new
  layout normally needs a short setup pass.
- Scans are simulated (skew, blur, noise, uneven light, JPEG). Real scans vary more.
- Character error rate is strict: it also counts reading-order differences, so true recognition
  quality is slightly better than the figure shows. The remaining scan errors are real OCR typos
  (for example a word read with a wrong letter).
- Timings come from one machine (single CPU core).

## Run it
Arch Linux:
```
sudo pacman -S --needed tesseract tesseract-data-eng
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run_demo.py                       # generate, extract, OCR, convert, operate (about 2.5 minutes)
python make_portfolio_images.py          # images built from sample_output/
python -m unittest discover -s tests -v  # 14 tests
```
Other systems: install Tesseract 5 with English data, then the same Python steps.

## Files
- `samples.py`: synthetic document generator with ground truth
- `extract.py`: invoice and statement extraction, reconciliation, scoring
- `ocr.py`: scan simulation, deskew, line removal, OCR, searchable PDF, error rate
- `convert.py`, `ops.py`, `export.py`: conversions, PDF operations, Excel / CSV / JSON output
- `run_demo.py`: end-to-end run, writes `output/`, `run_report.json`, `run.log`
- `sample_output/`: real artefacts from a run (report, log, workbooks, sample PDFs and conversions)
- `tests/`: 14 tests on real fixture PDFs
