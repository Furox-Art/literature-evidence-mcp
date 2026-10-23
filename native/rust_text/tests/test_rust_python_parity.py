import literature_evidence_rust as rust
import pytest

from literature_evidence_mcp.methodology import _locate


@pytest.mark.parametrize("source,quote", [
 ("The treatment was insignificant.","significant"),
 ("The intervention was ineffective.","effective"),
 ("A RANDOMIZED\n trial was reported.","randomized trial"),
 ("αβ significant Δ","significant"),
 ("one (N = 20) trial","(N = 20)"),
 ("A short paragraph","missed"),
 ("Résumé on neural data","résumé"),
 ("good data"," "), ("Part 42","42")
])
def test_exact_unicode_quote_parity(source, quote):
 assert rust.find_quote(source,quote)==_locate(source,quote)
