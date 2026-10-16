#!/usr/bin/env python3
"""
End-to-end PDF operations demo on synthetic documents, measured against ground truth.

Stages: generate -> extract invoices -> extract statements -> OCR scans -> convert formats ->
utility operations (merge, split, compress, watermark, redact, protect). Writes output/ with
every file produced, plus run_report.json and run.log. Then copies a small set of real artefacts
to sample_output/ (used by make_portfolio_images.py).

Run:  python run_demo.py        (needs tesseract installed; see README)
"""
import json
import os
import random
import shutil
import sys
import time
from datetime import datetime

import pymupdf
from pypdf import PdfReader

import convert
import export
import extract
import ocr
import ops
import samples

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "output")
SAMPLES = os.path.join(ROOT, "samples")
SAMPLE_OUT = os.path.join(ROOT, "sample_output")
N_INVOICES, N_STATEMENTS, N_SCANS, OCR_PSM = 120, 12, 20, 4


def log(level, msg):
    line = f"{datetime.now():%H:%M:%S} [{level}] {msg}"
    print(line, flush=True)
    with open(os.path.join(OUT, "run.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def pct(a, b):
    return round(100.0 * a / b, 2) if b else 0.0


def size(path):
    return os.path.getsize(path)


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    for d in ("scans", "searchable", "converted", "ops"):
        os.makedirs(os.path.join(OUT, d))
    shutil.rmtree(SAMPLES, ignore_errors=True)
    t_all = time.time()
    rep = {"environment": "synthetic PDFs generated locally (fictional companies and people), no real data",
           "generated_at": datetime.now().isoformat(timespec="seconds")}

    # ---------------------------------------------------------------- 1. generate
    truth, pages_generated = samples.generate(SAMPLES, N_INVOICES, N_STATEMENTS)
    inv_paths = {n: os.path.join(SAMPLES, "invoices", n) for n in truth["invoices"]}
    st_paths = {n: os.path.join(SAMPLES, "statements", n) for n in truth["statements"]}
    log("INFO", f"Generated {N_INVOICES} invoices (3 layouts) and {N_STATEMENTS} statements: "
                f"{pages_generated} pages")

    # ---------------------------------------------------------------- 2. invoices
    t0 = time.time()
    inv_records, agg = [], dict(f_ok=0, f_tot=0, c_ok=0, c_tot=0, all_ok=0, pages=0)
    flagged_names = set()
    for name, path in inv_paths.items():
        rec = extract.extract_invoice(path)
        s = extract.score_invoice(rec, truth["invoices"][name])
        problems = extract.reconcile_invoice(rec)
        if problems:
            flagged_names.add(name)
        inv_records.append((name, rec, problems))
        agg["f_ok"] += s["fields_ok"]; agg["f_tot"] += s["fields_total"]
        agg["c_ok"] += s["cells_ok"]; agg["c_tot"] += s["cells_total"]
        agg["all_ok"] += s["all_ok"]; agg["pages"] += rec["pages"]
    inv_s = time.time() - t0
    injected = {n for n, t in truth["invoices"].items() if t["injected_error"]}
    rep["invoices"] = {
        "count": N_INVOICES, "pages": agg["pages"], "layouts": 3,
        "header_fields_ok": agg["f_ok"], "header_fields_total": agg["f_tot"],
        "header_accuracy_pct": pct(agg["f_ok"], agg["f_tot"]),
        "line_item_cells_ok": agg["c_ok"], "line_item_cells_total": agg["c_tot"],
        "line_item_accuracy_pct": pct(agg["c_ok"], agg["c_tot"]),
        "line_items": sum(len(r["items"]) for _, r, _ in inv_records),
        "documents_fully_correct": agg["all_ok"],
        "injected_errors": len(injected), "errors_flagged": len(injected & flagged_names),
        "false_alarms": len(flagged_names - injected), "seconds": round(inv_s, 1),
        "pages_per_second": round(agg["pages"] / inv_s, 1)}
    log("INFO", f"Invoices: {N_INVOICES} PDFs, {agg['pages']} pages, "
                f"{rep['invoices']['line_items']:,} line items in {inv_s:.1f}s")
    log("INFO", f"Invoice accuracy: header fields {agg['f_ok']:,}/{agg['f_tot']:,}, "
                f"line-item cells {agg['c_ok']:,}/{agg['c_tot']:,}")
    log("WARN" if injected else "INFO",
        f"Arithmetic check flagged {len(flagged_names)} invoices; "
        f"{len(injected & flagged_names)}/{len(injected)} injected errors caught, "
        f"{len(flagged_names - injected)} false alarms")
    rep["excel_invoices"] = export.write_invoices(
        inv_records, os.path.join(OUT, "invoices.xlsx"), os.path.join(OUT, "invoices.csv"),
        os.path.join(OUT, "invoices.json"))

    # ---------------------------------------------------------------- 3. statements
    t0 = time.time()
    st_records, cells_ok, cells_tot, rows_found, pages_st = [], 0, 0, 0, 0
    st_injected = {n for n, t in truth["statements"].items() if t["injected_error_row"] is not None}
    st_caught, st_false, st_reconciled = 0, 0, 0
    for name, path in st_paths.items():
        rec = extract.extract_statement(path)
        s = extract.score_statement(rec, truth["statements"][name])
        flagged, problems = extract.reconcile_statement(rec)
        st_records.append((name, rec, flagged, problems))
        cells_ok += s["cells_ok"]; cells_tot += s["cells_total"]; rows_found += len(rec["rows"])
        pages_st += rec["pages"]
        inj_row = truth["statements"][name]["injected_error_row"]
        if inj_row is not None:
            st_caught += flagged == [inj_row]
        elif flagged or problems:
            st_false += 1
        st_reconciled += (not flagged and not problems)
    st_s = time.time() - t0
    rep["statements"] = {
        "count": N_STATEMENTS, "pages": pages_st, "rows": rows_found, "cells_ok": cells_ok,
        "cells_total": cells_tot, "cell_accuracy_pct": pct(cells_ok, cells_tot),
        "injected_errors": len(st_injected), "errors_flagged": st_caught, "false_alarms": st_false,
        "reconciled_clean": st_reconciled, "seconds": round(st_s, 1)}
    log("INFO", f"Statements: {N_STATEMENTS} PDFs, {pages_st} pages, {rows_found:,} table rows "
                f"in {st_s:.1f}s, cell accuracy {cells_ok:,}/{cells_tot:,}")
    log("WARN" if st_injected else "INFO",
        f"Balance check: {st_caught}/{len(st_injected)} injected balance errors flagged, "
        f"{st_false} false alarms, {st_reconciled}/{N_STATEMENTS} statements fully reconciled")
    rep["excel_statements"] = export.write_statements(st_records, os.path.join(OUT, "statements.xlsx"))

    # ---------------------------------------------------------------- 4. scans + OCR
    demo = next(n for n, t in truth["invoices"].items()
                if t["template"] == "A" and 6 <= len(t["items"]) <= 9 and not t["injected_error"]
                and dict((nm, r["pages"]) for nm, r, _ in inv_records)[n] == 1)
    page_count = {nm: r["pages"] for nm, r, _ in inv_records}
    scan_names = [demo] + [n for n in truth["invoices"] if page_count[n] == 1 and n != demo][:N_SCANS - 1]
    t0 = time.time()
    scan_paths, search_paths, ocr_cer, o = [], [], [], dict(f_ok=0, f_tot=0, c_ok=0, c_tot=0, found=0,
                                                              words=0, no_text=0, skew=[])
    ocr_lines_demo = None
    for i, name in enumerate(scan_names):
        tr = truth["invoices"][name]
        scan = os.path.join(OUT, "scans", name)
        ocr.make_scan(inv_paths[name], scan, random.Random(1000 + i))
        o["no_text"] += not ocr.has_text_layer(scan)
        searchable = os.path.join(OUT, "searchable", name)
        words, pl, skews = ocr.ocr_to_searchable(scan, searchable, psm=OCR_PSM)
        o["words"] += words
        o["skew"] += [abs(x) for x in skews]
        ocr_cer.append(ocr.cer(ocr.text_of(inv_paths[name]), "\n".join("\n".join(p) for p in pl)))
        rec = extract.extract_invoice_from_lines(pl, ocr=True)
        s = extract.score_invoice(rec, tr)
        o["f_ok"] += s["fields_ok"]; o["f_tot"] += s["fields_total"]
        o["c_ok"] += s["cells_ok"]; o["c_tot"] += s["cells_total"]
        o["found"] += ocr.search_hits(searchable, tr["invoice_no"]) > 0
        scan_paths.append(scan)
        search_paths.append(searchable)
        if name == demo:
            ocr_lines_demo = {"lines": pl[0], "truth_lines": ocr.text_of(inv_paths[name]).split("\n"),
                              "cer_pct": round(100 * ocr_cer[-1], 2)}
    ocr_s = time.time() - t0
    rep["ocr"] = {
        "scans": len(scan_names), "engine": "Tesseract 5 (psm 4) + deskew + table-line removal",
        "scans_without_text_layer": o["no_text"], "words_recognised": o["words"],
        "mean_cer_pct": round(100 * sum(ocr_cer) / len(ocr_cer), 2),
        "header_fields_ok": o["f_ok"], "header_fields_total": o["f_tot"],
        "line_item_cells_ok": o["c_ok"], "line_item_cells_total": o["c_tot"],
        "line_item_accuracy_pct": pct(o["c_ok"], o["c_tot"]),
        "searchable_found": o["found"], "mean_abs_skew_deg": round(sum(o["skew"]) / len(o["skew"]), 2),
        "seconds": round(ocr_s, 1)}
    log("INFO", f"OCR: {len(scan_names)} scanned pages (no text layer) -> searchable PDFs in {ocr_s:.0f}s, "
                f"mean character error {rep['ocr']['mean_cer_pct']}%")
    log("INFO", f"OCR extraction: header fields {o['f_ok']}/{o['f_tot']}, "
                f"line-item cells {o['c_ok']}/{o['c_tot']}; invoice number searchable in "
                f"{o['found']}/{len(scan_names)} PDFs")

    merged_scans = os.path.join(OUT, "ops", "scans_searchable_merged.pdf")
    ops.merge(search_paths, merged_scans)
    compressed = os.path.join(OUT, "ops", "scans_compressed.pdf")
    t0 = time.time()
    ops.compress(merged_scans, compressed)
    still = sum(ocr.search_hits(compressed, truth["invoices"][n]["invoice_no"]) > 0 for n in scan_names)
    rep["compress"] = {"before_bytes": size(merged_scans), "after_bytes": size(compressed),
                       "saved_pct": round(100 * (1 - size(compressed) / size(merged_scans)), 1),
                       "searchable_before": o["found"], "searchable_after": still,
                       "seconds": round(time.time() - t0, 1)}
    log("INFO", f"Compress: {size(merged_scans) / 1e6:.1f} MB -> {size(compressed) / 1e6:.1f} MB "
                f"({rep['compress']['saved_pct']}% smaller), text search still works in {still}/{o['found']}")

    # ---------------------------------------------------------------- 5. conversions
    conv_dir = os.path.join(OUT, "converted")
    picks = [n for t in ("A", "B", "C") for n in
             [x for x, v in truth["invoices"].items() if v["template"] == t][:4]]
    docs = [(n, inv_paths[n], truth["invoices"][n]["invoice_no"], truth["invoices"][n]["total_c"])
            for n in picks]
    docs += [(n, st_paths[n], truth["statements"][n]["account_no"], truth["statements"][n]["closing_c"])
             for n in list(st_paths)[:2]]
    conv = {k: {"files": 0, "bytes": 0, "ok": 0, "seconds": 0.0} for k in ("docx", "txt", "html", "png")}
    for name, path, key_text, amount_c in docs:
        stem = name.replace(".pdf", "")
        money_txt = samples.money(amount_c)
        npages = len(PdfReader(path).pages)
        runs = (("docx", lambda: convert.to_docx(path, os.path.join(conv_dir, stem + ".docx")),
                 lambda: key_text in convert.docx_text(os.path.join(conv_dir, stem + ".docx")),
                 [stem + ".docx"]),
                ("txt", lambda: convert.to_txt(path, os.path.join(conv_dir, stem + ".txt")),
                 lambda: key_text in open(os.path.join(conv_dir, stem + ".txt"), encoding="utf-8").read(),
                 [stem + ".txt"]),
                ("html", lambda: convert.to_html(path, os.path.join(conv_dir, stem + ".html")),
                 lambda: key_text in open(os.path.join(conv_dir, stem + ".html"), encoding="utf-8").read(),
                 [stem + ".html"]),
                ("png", lambda: convert.to_pngs(path, os.path.join(conv_dir, stem + "_png")),
                 lambda: len(os.listdir(os.path.join(conv_dir, stem + "_png"))) == npages,
                 [os.path.join(stem + "_png", f"page_{i:02d}.png") for i in range(1, npages + 1)]))
        for fmt, do, check, files in runs:
            t1 = time.time()
            do()
            conv[fmt]["seconds"] += time.time() - t1
            conv[fmt]["files"] += len(files)
            conv[fmt]["bytes"] += sum(size(os.path.join(conv_dir, f)) for f in files)
            conv[fmt]["ok"] += bool(check())
    for fmt in conv:
        conv[fmt]["seconds"] = round(conv[fmt]["seconds"], 1)
    rep["conversions"] = {"documents": len(docs), "formats": conv}
    log("INFO", f"Converted {len(docs)} PDFs to DOCX / TXT / HTML / PNG; content check passed "
                + ", ".join(f"{f.upper()} {v['ok']}/{len(docs)}" for f, v in conv.items()))

    # ---------------------------------------------------------------- 6. utility operations
    opsd = os.path.join(OUT, "ops")
    all_inv = list(inv_paths.values())
    merged = os.path.join(opsd, "invoices_merged.pdf")
    n_pages = ops.merge(all_inv, merged)
    split_n = ops.split(merged, os.path.join(opsd, "split"))
    rep["merge_split"] = {"inputs": len(all_inv), "merged_pages": n_pages,
                          "expected_pages": agg["pages"], "split_files": split_n,
                          "ok": n_pages == agg["pages"] == split_n}
    log("INFO", f"Merge: {len(all_inv)} PDFs -> 1 PDF of {n_pages} pages; split back into {split_n} single-page files")

    wm_src = os.path.join(opsd, "invoices_first20.pdf")
    ops.merge(all_inv[:20], wm_src)
    wm_out = os.path.join(opsd, "invoices_first20_watermarked.pdf")
    ops.watermark(wm_src, wm_out)
    with pymupdf.open(wm_out) as d:
        wm_pages = len(d)
        wm_hits = sum(bool(p.search_for("CONFIDENTIAL")) for p in d)
    still_text = ocr.search_hits(wm_out, truth["invoices"][os.path.basename(all_inv[0])]["invoice_no"]) > 0
    rep["watermark"] = {"pages": wm_pages, "pages_stamped": wm_hits, "text_intact": still_text,
                        "ok": wm_hits == wm_pages and still_text}
    log("INFO", f"Watermark: stamped {wm_hits}/{wm_pages} pages, original text still selectable")

    redactions, remaining, intact = 0, 0, 0
    for name, path in st_paths.items():
        tr = truth["statements"][name]
        out_pdf = os.path.join(opsd, "redacted_" + name)
        redactions += ops.redact(path, out_pdf, [tr["account_no"], tr["holder"]])
        remaining += sum(ocr.search_hits(out_pdf, x) for x in (tr["account_no"], tr["holder"]))
        txt = ocr.text_of(out_pdf)
        intact += (samples.money(tr["rows"][0]["balance_c"]) in txt) and (tr["bank"] in txt)
    rep["redact"] = {"statements": len(st_paths), "redactions": redactions, "matches_remaining": remaining,
                     "content_intact": intact, "ok": remaining == 0 and intact == len(st_paths)}
    log("INFO", f"Redaction: {redactions} account numbers and names removed from {len(st_paths)} statements; "
                f"{remaining} matches remain, other content intact in {intact}/{len(st_paths)}")

    prot = os.path.join(opsd, "demo_invoice_protected.pdf")
    ops.protect(inv_paths[demo], prot, "user-pass", "owner-pass")
    r = PdfReader(prot)
    encrypted = r.is_encrypted
    wrong_rejected = PdfReader(prot).decrypt("wrong-pass") == 0
    unlocked = os.path.join(opsd, "demo_invoice_unlocked.pdf")
    ops.unprotect(prot, unlocked, "user-pass")
    unlocked_ok = truth["invoices"][demo]["invoice_no"] in ocr.text_of(unlocked) and not PdfReader(unlocked).is_encrypted
    rep["protect"] = {"encrypted": encrypted, "algorithm": "AES-256", "wrong_password_rejected": wrong_rejected,
                      "unlock_ok": unlocked_ok, "ok": encrypted and wrong_rejected and unlocked_ok}
    log("INFO", f"Password protect: AES-256 encrypted={encrypted}, wrong password rejected={wrong_rejected}, "
                f"unlock with correct password works={unlocked_ok}")

    # ---------------------------------------------------------------- 7. report + sample artefacts
    rep["totals"] = {
        "pdfs_processed": N_INVOICES + N_STATEMENTS + len(scan_names),
        "pages_processed": agg["pages"] + pages_st + len(scan_names),
        "total_runtime_s": round(time.time() - t_all, 1)}
    log("INFO", f"Done: {rep['totals']['pdfs_processed']} PDFs, {rep['totals']['pages_processed']} pages "
                f"in {rep['totals']['total_runtime_s']:.0f}s")
    build_sample_output(rep, truth, demo, inv_paths, st_paths, inv_records, st_records, ocr_lines_demo, conv_dir)
    with open(os.path.join(OUT, "run_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    shutil.copy(os.path.join(OUT, "run_report.json"), os.path.join(SAMPLE_OUT, "run_report.json"))
    shutil.copy(os.path.join(OUT, "run.log"), os.path.join(SAMPLE_OUT, "run.log"))
    return 0


def build_sample_output(rep, truth, demo, inv_paths, st_paths, inv_records, st_records, ocr_lines_demo, conv_dir):
    """Copy a small, real set of artefacts that make_portfolio_images.py draws from."""
    shutil.rmtree(SAMPLE_OUT, ignore_errors=True)
    os.makedirs(os.path.join(SAMPLE_OUT, "formats"))
    S = lambda *p: os.path.join(SAMPLE_OUT, *p)  # noqa: E731
    shutil.copy(inv_paths[demo], S("demo_invoice.pdf"))
    shutil.copy(os.path.join(OUT, "scans", demo), S("demo_scan.pdf"))
    shutil.copy(os.path.join(OUT, "searchable", demo), S("demo_scan_searchable.pdf"))
    st_name = list(st_paths)[0]
    shutil.copy(st_paths[st_name], S("demo_statement.pdf"))
    for f in ("invoices.xlsx", "invoices.csv", "invoices.json", "statements.xlsx"):
        shutil.copy(os.path.join(OUT, f), S(f))
    for src, dst in ((S("demo_invoice.pdf"), "demo_invoice_p1.png"), (S("demo_scan.pdf"), "demo_scan_p1.png"),
                     (S("demo_statement.pdf"), "demo_statement_p1.png")):
        with pymupdf.open(src) as d:
            d[0].get_pixmap(dpi=150).save(S(dst))
    rec = next(r for n, r, _ in inv_records if n == demo)
    with open(S("demo_invoice_boxes.json"), "w", encoding="utf-8") as f:
        json.dump({"page_pt": [612, 792], "boxes": extract.field_boxes(inv_paths[demo], rec)}, f, indent=1)
    keep = {k: v for k, v in rec.items() if k not in ("raw",)}
    keep["items"] = [{k: v for k, v in i.items() if k != "raw_amount"} for i in rec["items"]]
    with open(S("demo_invoice_record.json"), "w", encoding="utf-8") as f:
        json.dump(keep, f, indent=1)
    srec = next(r for n, r, _, _ in st_records if n == st_name)
    import pdfplumber
    with pdfplumber.open(st_paths[st_name]) as pdf:
        tables = [t for t in pdf.pages[0].find_tables() if len(t.rows) > 5]
        table_bbox = [round(v, 1) for v in tables[0].bbox] if tables else None
    with open(S("demo_statement_record.json"), "w", encoding="utf-8") as f:
        json.dump({"name": st_name, "account_no": srec.get("account_no"), "summary": srec["summary"],
                   "pages": srec["pages"], "row_count": len(srec["rows"]), "table_bbox_pt": table_bbox,
                   "rows": srec["rows"][:12]}, f, indent=1)
    with open(S("demo_ocr.json"), "w", encoding="utf-8") as f:
        json.dump(ocr_lines_demo, f, indent=1)
    # the same demo invoice in every output format, single-file versions
    stem = demo.replace(".pdf", "")
    fm = {}
    one = [(demo, rec, [])]
    export.write_invoices(one, S("formats", stem + ".xlsx"), S("formats", stem + ".csv"), S("formats", stem + ".json"))
    for ext in ("docx", "txt", "html"):
        shutil.copy(os.path.join(conv_dir, stem + "." + ext), S("formats", stem + "." + ext))
    shutil.copy(os.path.join(conv_dir, stem + "_png", "page_01.png"), S("formats", stem + ".png"))
    shutil.copy(inv_paths[demo], S("formats", stem + ".pdf"))
    for f in os.listdir(S("formats")):
        fm[os.path.splitext(f)[1][1:]] = size(S("formats", f))
    with open(S("demo_formats.json"), "w", encoding="utf-8") as f:
        json.dump({"stem": stem, "bytes": fm}, f, indent=1)
    shutil.copy(os.path.join(OUT, "ops", "redacted_" + st_name), S("demo_statement_redacted.pdf"))


if __name__ == "__main__":
    sys.exit(main())
