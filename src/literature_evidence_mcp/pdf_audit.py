"""Local PDF page, table and image bounding-box provenance.

Never accepts a URL or filesystem path. PDF content is user-supplied and untrusted;
page-text matches do NOT authenticate the PDF, prove its claims or decode figures.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from io import BytesIO

import pdfplumber

from literature_evidence_mcp.methodology import _locate


def audit_pdf_page(pdf_base64: str, page_number: int, quote: str) -> dict:
    if not isinstance(pdf_base64, str) or len(pdf_base64) > 7_000_000:
        raise ValueError("PDF base64 must be a string smaller than 7 MB")
    if isinstance(page_number, bool) or type(page_number) is not int or not 1 <= page_number <= 1000:
        raise ValueError("Valid page_number 1-1000 required")
    if not isinstance(quote, str) or not 1 <= len(quote.strip()) <= 2000:
        raise ValueError("quote length must be 1-2000")
    try:
        contents = base64.b64decode(pdf_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid base64 PDF") from exc
    if not contents.startswith(b"%PDF-") or len(contents) > 5_000_000:
        raise ValueError("PDF header or size invalid")
    digest = hashlib.sha256(contents).hexdigest()
    try:
        with pdfplumber.open(BytesIO(contents)) as pdf:
            if page_number > len(pdf.pages):
                raise ValueError("Page not present in PDF")
            page = pdf.pages[page_number - 1]
            text = page.extract_text() or ""
            if len(text) > 250_000:
                raise ValueError("Page text limit exceeded")
            match = _locate(text, quote)
            # Anchor full excerpt to page-local coordinates, not inferred pixel
            # precision: PDF layout and hyphenation affect word positions.
            matches = page.search(quote, regex=False, case=False, return_chars=False)
            rectangles = [{"x0": m["x0"], "top": m["top"], "x1": m["x1"], "bottom": m["bottom"]}
                          for m in matches[:10]]
            tables = page.find_tables()
            table_bounds = [
                {"bbox": list(t.bbox), "row_count": len(t.rows)}
                for t in tables[:30]
            ]
            image_bounds = [
                {"x0": i.get("x0"), "top": i.get("top"),
                 "x1": i.get("x1"), "bottom": i.get("bottom")}
                for i in page.images[:50]
            ]
            return {
                "status": "PDF_PAGE_TEXT_FOUND_NOT_SCIENTIFICALLY_VERIFIED"
                          if match is not None else "PDF_PAGE_TEXT_NOT_VERIFIED",
                "pdf_sha256": digest, "page_number": page_number,
                "page_count": len(pdf.pages),
                "page_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "quote_offset_start": match[0] if match is not None else None,
                "quote_offset_end": match[1] if match is not None else None,
                "matching_text_bounding_boxes": rectangles,
                "detected_table_bounding_boxes": table_bounds,
                "detected_image_bounding_boxes": image_bounds,
                "tables_truncated": len(tables) > 30,
                "images_truncated": len(page.images) > 50,
                "figure_and_table_content_verified": False,
                "notice": "Only structural/textual PDF coordinates; embedded image content, "
                          "table semantics, source authenticity and scientific claims are not verified.",
            }
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("PDF could not be safely parsed") from exc
