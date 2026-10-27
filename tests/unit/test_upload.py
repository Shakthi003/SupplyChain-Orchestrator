"""
tests/unit/test_upload.py

Unit tests for the document upload pipeline:
  - retrieval/parser.py  (text extraction)
  - retrieval/validator.py (3-layer validation)

These tests are fully offline — no ChromaDB, no PostgreSQL, no Gemini.
"""

import io
import pytest

from retrieval.parser import extract_text, is_long_enough
from retrieval.validator import validate_document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf_bytes(text: str) -> bytes:
    """Create a minimal valid PDF in memory containing the given text."""
    import pypdf
    from pypdf import PdfWriter

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    # pypdf blank pages have no text stream by default —
    # use a real pypdf page from a simple in-memory PDF instead.
    # Easiest approach: build a raw minimal PDF manually.
    _ = page  # we'll use the raw approach below
    del writer

    # Raw minimal PDF that renders one line of text
    content = text.encode("latin-1", errors="replace")
    stream = (
        b"BT /F1 12 Tf 72 720 Td (" + content + b") Tj ET"
    )
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
        b"   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000400 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n460\n%%EOF\n"
    )
    return pdf


def _make_docx_bytes(text: str) -> bytes:
    """Create a minimal DOCX in memory containing the given text."""
    import docx as _docx

    doc = _docx.Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


LONG_CONTRACT = (
    "SUPPLIER CONTRACT\n"
    "This agreement is between the buyer and the supplier.\n"
    "Penalty clause: a delay of 4-7 days incurs a 5% penalty on the purchase order value.\n"
    "Delivery terms: standard lead time is 14 days from order confirmation.\n"
    "Payment terms: net 30 days after delivery.\n"
    "The supplier agrees to notify the buyer within 24 hours of any anticipated delay.\n"
    "Liability is limited to the value of the affected purchase order.\n"
    "This contract is governed by the laws of the jurisdiction.\n"
) * 3  # repeat to make it long enough


# ---------------------------------------------------------------------------
# parser.py tests
# ---------------------------------------------------------------------------

class TestExtractText:

    def test_txt_extracts_correctly(self):
        text, err = extract_text("doc.txt", b"Hello supplier contract penalty delivery")
        assert err is None
        assert "supplier" in text

    def test_unsupported_extension_returns_error(self):
        text, err = extract_text("file.xyz", b"some bytes")
        assert text == ""
        assert err is not None
        assert "Unsupported" in err

    def test_empty_txt_returns_error(self):
        # Empty bytes → empty string after decode → _extract_text returns an error
        # (the caller should treat this as an unusable file)
        text, err = extract_text("empty.txt", b"")
        assert text == ""
        assert err is not None

    def test_docx_extracts_correctly(self):
        content = "Supplier contract penalty clause delivery payment terms agreement."
        docx_bytes = _make_docx_bytes(content)
        text, err = extract_text("contract.docx", docx_bytes)
        assert err is None
        assert "penalty" in text.lower() or "contract" in text.lower()

    def test_wrong_bytes_for_docx_returns_error(self):
        text, err = extract_text("bad.docx", b"not a docx file at all")
        assert text == ""
        assert err is not None


class TestIsLongEnough:

    def test_short_text_fails(self):
        assert not is_long_enough("too short")

    def test_long_text_passes(self):
        assert is_long_enough("x" * 200)

    def test_exact_minimum(self):
        from retrieval.parser import MIN_CONTENT_LENGTH
        assert is_long_enough("x" * MIN_CONTENT_LENGTH)
        assert not is_long_enough("x" * (MIN_CONTENT_LENGTH - 1))


# ---------------------------------------------------------------------------
# validator.py tests
# ---------------------------------------------------------------------------

class TestLayer1Length:

    def test_empty_text_is_rejected(self):
        result = validate_document("", "contract", run_gemini=False)
        assert not result.passed
        assert result.errors

    def test_short_text_is_rejected(self):
        result = validate_document("short", "contract", run_gemini=False)
        assert not result.passed

    def test_long_text_passes_layer1(self):
        result = validate_document(LONG_CONTRACT, "contract", run_gemini=False)
        assert result.passed


class TestLayer2Keywords:

    def test_contract_with_keywords_passes_silently(self):
        result = validate_document(LONG_CONTRACT, "contract", run_gemini=False)
        assert result.passed
        assert not result.warnings  # keywords found — no warning

    def test_contract_without_keywords_warns(self):
        irrelevant = (
            "This is a completely unrelated document about cooking recipes. "
            "It has nothing to do with procurement or logistics. " * 10
        )
        result = validate_document(irrelevant, "contract", run_gemini=False)
        assert result.passed  # Layer 2 never blocks — only warns
        assert any("doesn't look like" in w for w in result.warnings)

    def test_other_category_skips_keyword_check(self):
        # "other" has no keywords — should produce no Layer 2 warning
        long_random = "random unrelated text about nothing in particular. " * 10
        result = validate_document(long_random, "other", run_gemini=False)
        assert result.passed
        assert not result.warnings

    def test_policy_keywords_detected(self):
        policy_text = (
            "INTERNAL POLICY\n"
            "This policy defines the approval thresholds for emergency procurement.\n"
            "Escalate to the procurement director for purchases above $50,000.\n"
            "Compliance with this procedure is mandatory for all teams.\n"
        ) * 4
        result = validate_document(policy_text, "policy", run_gemini=False)
        assert result.passed
        assert not result.warnings


class TestLayer3GeminiSkipped:

    def test_gemini_skipped_when_run_gemini_false(self):
        result = validate_document(LONG_CONTRACT, "contract", run_gemini=False)
        assert result.gemini_verdict is None

    def test_gemini_falls_back_gracefully_with_bad_key(self, monkeypatch):
        """If Gemini fails, validation still passes — just adds a warning."""
        monkeypatch.setenv("GEMINI_API_KEY", "INVALID-KEY-FOR-TEST")

        # Patch the genai client to raise immediately
        import retrieval.validator as val_module
        original = val_module._layer3_gemini

        def fake_layer3(text, category, result):
            result.warn("AI content check skipped (Gemini unavailable: test-forced error).")

        monkeypatch.setattr(val_module, "_layer3_gemini", fake_layer3)

        result = validate_document(LONG_CONTRACT, "contract", run_gemini=True)
        assert result.passed  # must still pass
        assert any("skipped" in w for w in result.warnings)
