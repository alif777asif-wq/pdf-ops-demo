"""Tests for extraction, reconciliation, OCR-tolerant parsing and PDF operations.

Run:  python -m unittest discover -s tests -v
Fixtures are real generated PDFs (three invoice layouts, one invoice with a wrong printed total,
two statements) plus the ground truth they were generated from.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import extract  # noqa: E402
import ocr  # noqa: E402
import ops  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
TRUTH = json.load(open(os.path.join(FX, "truth.json"), encoding="utf-8"))


class InvoiceTests(unittest.TestCase):
    def test_every_layout_is_extracted_exactly(self):
        for name, truth in TRUTH["invoices"].items():
            with self.subTest(name=name, layout=truth["template"]):
                rec = extract.extract_invoice(os.path.join(FX, name))
                score = extract.score_invoice(rec, truth)
                self.assertTrue(score["all_ok"], score)

    def test_wrong_printed_total_is_flagged(self):
        flagged = [n for n, t in TRUTH["invoices"].items() if t["injected_error"]]
        self.assertEqual(len(flagged), 1)
        rec = extract.extract_invoice(os.path.join(FX, flagged[0]))
        self.assertIn("total_mismatch", extract.reconcile_invoice(rec))

    def test_clean_invoices_are_not_flagged(self):
        for name, truth in TRUTH["invoices"].items():
            if not truth["injected_error"]:
                rec = extract.extract_invoice(os.path.join(FX, name))
                self.assertEqual(extract.reconcile_invoice(rec), [], name)


class StatementTests(unittest.TestCase):
    def test_multi_page_table_is_extracted_exactly(self):
        for name, truth in TRUTH["statements"].items():
            rec = extract.extract_statement(os.path.join(FX, name))
            score = extract.score_statement(rec, truth)
            self.assertEqual(score["cells_ok"], score["cells_total"], name)
            self.assertEqual(len(rec["rows"]), len(truth["rows"]), name)

    def test_only_the_wrong_balance_row_is_flagged(self):
        truth = TRUTH["statements"]["ST-003.pdf"]
        rec = extract.extract_statement(os.path.join(FX, "ST-003.pdf"))
        flagged, problems = extract.reconcile_statement(rec)
        self.assertEqual(flagged, [truth["injected_error_row"]])
        self.assertEqual(problems, [])

    def test_clean_statement_reconciles(self):
        rec = extract.extract_statement(os.path.join(FX, "ST-001.pdf"))
        self.assertEqual(extract.reconcile_statement(rec), ([], []))


class ParsingTests(unittest.TestCase):
    def test_parse_money(self):
        self.assertEqual(extract.parse_money("$1,273.68"), 127368)
        self.assertEqual(extract.parse_money("-$12.50"), -1250)

    def test_dates_in_three_formats(self):
        self.assertEqual(extract.find_date("Date: 2026-03-05")[2], "2026-03-05")
        self.assertEqual(extract.find_date("Issued 30 Jul 2026")[2], "2026-07-30")
        self.assertEqual(extract.find_date("Due 05/22/2026")[2], "2026-05-22")

    def test_ocr_mode_repairs_look_alike_digits(self):
        for bad in ("I", "l", "|"):
            line = f"Ergonomic office chair {bad} $222.74 $222.74"
            strict = extract.extract_invoice_from_lines([[line]])
            tolerant = extract.extract_invoice_from_lines([[line]], ocr=True)
            self.assertEqual(strict["items"], [])
            self.assertEqual(tolerant["items"][0]["qty"], 1)

    def test_ocr_mode_uses_arithmetic_to_confirm_quantity(self):
        self.assertEqual(extract.repair_qty("l", 5000, 15000), 3)  # 3 x $50.00 = $150.00

    def test_cer(self):
        self.assertEqual(ocr.cer("abcd", "abcd"), 0.0)
        self.assertEqual(ocr.cer("abcd", "abxd"), 0.25)


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_merge_then_split_keeps_every_page(self):
        names = [n for n in TRUTH["invoices"]]
        merged = os.path.join(self.tmp.name, "m.pdf")
        pages = ops.merge([os.path.join(FX, n) for n in names], merged)
        self.assertEqual(ops.split(merged, os.path.join(self.tmp.name, "s")), pages)

    def test_redaction_removes_text_from_the_file(self):
        truth = TRUTH["statements"]["ST-001.pdf"]
        out = os.path.join(self.tmp.name, "r.pdf")
        n = ops.redact(os.path.join(FX, "ST-001.pdf"), out, [truth["account_no"], truth["holder"]])
        self.assertGreater(n, 0)
        text = ocr.text_of(out)
        self.assertNotIn(truth["account_no"], text)
        self.assertNotIn(truth["holder"], text)
        self.assertIn(truth["bank"], text)

    def test_password_round_trip(self):
        from pypdf import PdfReader
        src = os.path.join(FX, "ST-001.pdf")
        prot, back = os.path.join(self.tmp.name, "p.pdf"), os.path.join(self.tmp.name, "u.pdf")
        ops.protect(src, prot, "u-pass", "o-pass")
        self.assertTrue(PdfReader(prot).is_encrypted)
        self.assertEqual(PdfReader(prot).decrypt("wrong"), 0)
        ops.unprotect(prot, back, "u-pass")
        self.assertFalse(PdfReader(back).is_encrypted)


if __name__ == "__main__":
    unittest.main()
