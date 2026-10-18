# Optional native scientific-tool components

These three native backend modules are opt-in, not replacements for the original
Python methods. The TypeScript front end dynamically discovers them.
If a module has not been installed its tool returns NATIVE_NOT_INSTALLED.
None supplies expert scientific judgment.

| MCP tool | Language | Role | Boundaries |
| --- | --- | --- | --- |
| rust_locate_quote | Rust PyO3 Maturin | Unicode-aware literal quote location, Python character offsets | Textual presence is not semantic support |
| go_parallel_provider_status | Go | Concurrent fixed-allowlist OpenAlex Crossref Europe PMC status | Availability is not relevance, no arbitrary endpoints |
| cpp_fixed_effect_meta | C++ pybind11 CMake | Inverse-variance fixed-effect meta-analysis on user-supplied effects/SEs | Assumes independence and common effect; heterogeneity/bias not assessed |

## Build on Linux / WSL

Requires Python 3.11+, Rust Cargo, Go 1.25+, C++17 and CMake.
All commands below are issued from the repository root:

    python -m pip install -e '.[dev]' maturin pybind11
    mkdir -p dist/native
    maturin build --release --manifest-path native/rust_text/Cargo.toml --out dist/native
    python -m pip install dist/native/literature_evidence_rust-*.whl

    go build -C native/go_sources -o ../../dist/literature-go-probe .
    export LITERATURE_EVIDENCE_GO_BIN="$(pwd)/dist/literature-go-probe"

    cmake -S native/cpp_meta -B dist/cpp_build \
      -Dpybind11_DIR="$(python -m pybind11 --cmakedir)" \
      -DPython_EXECUTABLE="$(command -v python)"
    cmake --build dist/cpp_build
    export PYTHONPATH="$(pwd)/dist/cpp_build:${PYTHONPATH:-}"

After installation, the three explicit native MCP tools become available
through the existing Python server. They do not replace its default algorithms.

## Scientific and QA limits

- Original Python 100% statement and branch CI gate must remain for Python
  3.11, 3.12, 3.13, and 100% TypeScript coverage must remain.
- Test Rust cargo and Python quote parity; Go unit tests and race detector and
  instrumented CLI coverage; C++ tests against independent known values.
- Measure native coverage honestly without excluding source or faking tests.
- The numeric result is a calculation, NOT a justified meta-analysis of
  eligible studies. No automatic bias or causal conclusions are asserted.
- npm publishing is not part of this change.
