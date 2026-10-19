//! Unicode-aware, punctuation-preserving literal phrase matching. Text offsets
//! are Python Unicode character indices, not UTF-8 byte positions.
use pyo3::prelude::*;
use regex::RegexBuilder;

fn quote_location(text: &str, quote: &str) -> Option<(usize, usize)> {
    let parts: Vec<&str> = quote.split_whitespace().collect();
    if parts.is_empty() {
        return None;
    }
    let pattern = parts.iter().map(|part| regex::escape(part)).collect::<Vec<_>>().join(r"\s+");
    let first = parts[0].chars().next()?;
    let last = parts.last()?.chars().last()?;
    let starts_word = first.is_alphanumeric() || first == '_';
    let ends_word = last.is_alphanumeric() || last == '_';
    let expr = format!("{}{}{}", if starts_word { r"\b" } else { "" }, pattern,
        if ends_word { r"\b" } else { "" });
    let rx = RegexBuilder::new(&expr).case_insensitive(true).unicode(true).build().ok()?;
    let match_ = rx.find(text)?;
    Some((text[..match_.start()].chars().count(), text[..match_.end()].chars().count()))
}

#[pyfunction]
fn find_quote(text: &str, quote: &str) -> Option<(usize, usize)> {
    quote_location(text, quote)
}

#[pymodule]
fn literature_evidence_rust(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(find_quote, module)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn tests_literal() {
        assert_eq!(quote_location("A RANDOMIZED\n  clinical trial", "randomized clinical"), Some((2, 23)));
        assert_eq!(quote_location("insignificant", "significant"), None);
        assert_eq!(quote_location("ineffective", "effective"), None);
        assert_eq!(quote_location("αβ significant Δ", "significant"), Some((3, 14)));
        assert_eq!(quote_location("one (N = 20) trial", "(N = 20)"), Some((4, 12)));
        assert_eq!(quote_location("citation", "    "), None);
        assert_eq!(quote_location("short text", "missing"), None);
        assert_eq!(find_quote("scientific method", "scientific"), Some((0, 10)));
    }
    #[test]
    fn python_module_registers_callable() {
        Python::initialize();
        Python::attach(|py| {
            let module = PyModule::new(py, "literature_evidence_rust").unwrap();
            literature_evidence_rust(&module).unwrap();
            let outcome: Option<(usize,usize)> = module.getattr("find_quote").unwrap()
                .call1(("unblinded", "blinded")).unwrap().extract().unwrap();
            assert_eq!(outcome, None);
        });
    }
}
