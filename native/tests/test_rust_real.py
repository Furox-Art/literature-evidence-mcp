from literature_evidence_mcp import server
from literature_evidence_mcp.methodology import _locate


def test_real_rust_unicode_and_negative_prefix_parity():
    pairs = [
        ("αβ significant Δ", "significant"),
        ("The result was insignificant.", "significant"),
        ("The outcome is ineffective.", "effective"),
        ("The trial was randomized.", "randomized"),
        ("Measured (N = 20) participants", "(N = 20)"),
    ]
    for text, quote in pairs:
        result = server.rust_locate_quote(text, quote)
        assert result["status"] != "NATIVE_NOT_INSTALLED"
        expected = _locate(text, quote)
        got = ((result["offset_start"], result["offset_end"])
               if result["offset_start"] is not None else None)
        assert got == expected
        assert result["semantic_support_verified"] is False
