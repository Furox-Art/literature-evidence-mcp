"""Real PDF text, image and table structural evidence plus hostile-input checks."""
import base64
from io import BytesIO

import pytest
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from literature_evidence_mcp import server
from literature_evidence_mcp.pdf_audit import audit_pdf_page


def pdf_fixture():
    stream = BytesIO()
    c = canvas.Canvas(stream, pagesize=(380, 470), pageCompression=0)
    c.drawString(30, 435, "Randomized trial participants enrolled")
    c.line(30, 370, 250, 370)
    c.line(30, 350, 250, 350)
    c.line(30, 330, 250, 330)
    c.line(30, 330, 30, 370)
    c.line(140, 330, 140, 370)
    c.line(250, 330, 250, 370)
    c.drawString(37, 353, "Treatment")
    c.drawString(145, 353, "Control")
    image = Image.new("RGB", (8, 8), (40, 90, 130))
    c.drawImage(ImageReader(image), 30, 250, width=42, height=42)
    c.showPage()
    c.drawString(30, 420, "Second page: no source claim")
    c.save()
    return base64.b64encode(stream.getvalue()).decode("ascii")


def test_real_pdf_page_table_and_image_boundaries():
    raw = pdf_fixture()
    out = server.pdf_page_provenance(raw, 1, "Randomized trial")
    assert out["status"] == "PDF_PAGE_TEXT_FOUND_NOT_SCIENTIFICALLY_VERIFIED"
    assert out["page_number"] == 1
    assert out["page_count"] == 2
    assert len(out["pdf_sha256"]) == 64
    assert len(out["page_text_sha256"]) == 64
    assert out["quote_offset_start"] is not None
    assert out["quote_offset_end"] > out["quote_offset_start"]
    assert out["matching_text_bounding_boxes"]
    assert out["detected_table_bounding_boxes"]
    assert out["detected_image_bounding_boxes"]
    assert out["figure_and_table_content_verified"] is False
    other = audit_pdf_page(raw, 2, "Randomized trial")
    assert other["status"] == "PDF_PAGE_TEXT_NOT_VERIFIED"
    assert other["quote_offset_start"] is None
    assert other["matching_text_bounding_boxes"] == []


@pytest.mark.parametrize("data,page,quote", [
    ("not base64?", 1, "trial"), ("", 1, "trial"),
    (base64.b64encode(b"not a pdf").decode(), 1, "trial"),
    (None, 1, "trial"), ("X" * 7_000_001, 1, "trial"),
    (pdf_fixture(), 0, "trial"), (pdf_fixture(), True, "trial"),
    (pdf_fixture(), 1001, "trial"), (pdf_fixture(), 3, "trial"),
    (pdf_fixture(), 1, ""), (pdf_fixture(), 1, " " * 30),
    (pdf_fixture(), 1, "x" * 2001),
])
def test_reject_hostile_or_incomplete_pdf_inputs(data, page, quote):
    with pytest.raises(ValueError):
        audit_pdf_page(data, page, quote)


def test_invalid_pdf_parse_does_not_infer_evidence():
    corrupt = base64.b64encode(b"%PDF-1.4\n000 garbage").decode()
    with pytest.raises(ValueError, match="parsed"):
        audit_pdf_page(corrupt, 1, "test")


def test_pdf_oversize_decoding_is_rejected():
    oversize = base64.b64encode(b"%PDF-" + b"A" * 5_000_000).decode()
    with pytest.raises(ValueError, match="size"):
        audit_pdf_page(oversize, 1, "study")


def test_untrusted_pdf_page_extraction_overlimit(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "a" * 250001
    class FakePDF:
        def __init__(self):
            self.pages = [FakePage()]
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
    monkeypatch.setattr("literature_evidence_mcp.pdf_audit.pdfplumber.open",
                        lambda contents: FakePDF())
    fake = base64.b64encode(b"%PDF-1.4\nopaque bytes").decode()
    with pytest.raises(ValueError, match="Page text limit"):
        audit_pdf_page(fake, 1, "source")
