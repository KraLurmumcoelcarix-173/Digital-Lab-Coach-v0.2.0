"""
F4: Digital CLI test output parser.

Two parse layers:

1. `parse_cli_output` — result lines only. Digital prints one line per
   Testcase element: `<name>: passed` or `<name>: failed (N%)`. Stray
   log noise (java.util.prefs INFO lines, etc.) is ignored.

2. `parse_cli_output_verbose` — result lines PLUS the value table that
   `CLI test -verbose` prints under each FAILED testcase. Grammar
   (verified empirically against Digital v0.31):

       <name>: failed (N%)
       <header line: the testcase's column names, space-separated>
       <one line per executed row, in execution order>
       <blank line>
       ...next testcase's result line...
       Tests have failed.

   - Loops (`loop(N,30) ... end loop`) are expanded by Digital itself,
     one table line per expanded row — same expansion DLC's TestSpec
     performs, so table line i corresponds to spec.rows[i].
   - A row with a `C` clock token still produces exactly ONE table
     line (the clock column echoes the post-pulse value, e.g. `0`).
   - A passing row echoes its values (formats vary: `1E`, `0x19`...).
   - A failing row renders each mismatched OUTPUT cell as
     `E: <expected> / F: <found>` — so "row failed" == "any E:/F: cell".
   - A testcase that could not run at all prints
     `<name>: <error text>` (e.g. "Test signal Qx not found in the
     circuit!") and no table.
   - Exit codes: 0 = all passed, 1 = some testcase failed or errored,
     200 = execution error (e.g. file not found).
"""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TestcaseResult:
    __test__ = False

    name: str
    status: str         
    fail_pct: int | None
    raw_line: str


@dataclass
class TestRunResults:
    __test__ = False

    testcases: list[TestcaseResult]
    raw_output: str

    def passed(self) -> bool:
        if not self.testcases:
            return False
        return all(t.status == "passed" for t in self.testcases)

    def by_name(self) -> dict[str, TestcaseResult]:
        return {t.name: t for t in self.testcases}

    def failed(self) -> list[TestcaseResult]:
        return [t for t in self.testcases if t.status == "failed"]

    def passed_testcases(self) -> list[TestcaseResult]:
        return [t for t in self.testcases if t.status == "passed"]

_PASS_RE = re.compile(r'(\S+):\s+passed\s*$')
_FAIL_RE = re.compile(r'(\S+):\s+failed(?:\s*\((\d+)%\))?\s*$')


def parse_cli_output(text: str) -> TestRunResults:
    by_name: dict[str, TestcaseResult] = {}
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        m = _FAIL_RE.search(line)
        if m:
            name = m.group(1)
            pct_str = m.group(2)
            pct = int(pct_str) if pct_str else None
            by_name[name] = TestcaseResult(
                name=name, status="failed", fail_pct=pct, raw_line=line,
            )
            continue
        m = _PASS_RE.search(line)
        if m:
            name = m.group(1)
            by_name[name] = TestcaseResult(
                name=name, status="passed", fail_pct=None, raw_line=line,
            )
    return TestRunResults(
        testcases=list(by_name.values()),
        raw_output=text,
    )


# Verbose value-table parsing (fast per-row path)

_MISMATCH_CELL_RE = re.compile(r'E:\s*(\S+)\s*/\s*F:\s*(\S+)')
_FINAL_LINE_RE = re.compile(r'^(Tests have failed\.|All tests passed\.?)\s*$')

# Like _PASS_RE/_FAIL_RE but anchored to the whole line so testcase
# names containing spaces ("Register File Test") parse fully. Noise
# lines are still excluded because they don't end in passed/failed.
_V_PASS_RE = re.compile(r'^(.*\S):\s+passed\s*$')
_V_FAIL_RE = re.compile(r'^(.*\S):\s+failed(?:\s*\((\d+)%\))?\s*$')


def _is_result_line(line: str) -> bool:
    return bool(_V_PASS_RE.match(line) or _V_FAIL_RE.match(line))


@dataclass
class VerboseSection:
    """One testcase's slice of `CLI test -verbose` output."""
    __test__ = False

    name: str
    status: str                  # "passed" | "failed" | "error"
    fail_pct: int | None
    error_message: str | None
    headers: list[str] = field(default_factory=list)
    # Parallel lists, one entry per executed (loop-expanded) row:
    row_lines: list[str] = field(default_factory=list)
    row_failed: list[bool] = field(default_factory=list)
    # Per row: [{"column": str|None, "expected": str, "found": str}, ...]
    row_mismatches: list[list[dict]] = field(default_factory=list)
    table_ok: bool = False       # True when every table line mapped cleanly


def _split_table_line(line: str, n_columns: int) -> tuple[list[str], list[dict]] | None:
    """Split one echoed table row into exactly `n_columns` cells.

    Mismatch cells (`E: x / F: y`) contain spaces, so they are lifted
    out first and re-inserted as single cells. Returns (cells,
    mismatches) or None if the line doesn't split into n_columns.
    """
    mismatches_raw: list[tuple[str, str]] = []

    def _stash(m: re.Match) -> str:
        mismatches_raw.append((m.group(1), m.group(2)))
        return f"\x00{len(mismatches_raw) - 1}\x00"

    cooked = _MISMATCH_CELL_RE.sub(_stash, line)
    cells = cooked.split()
    if len(cells) != n_columns:
        return None
    mismatches: list[dict] = []
    out_cells: list[str] = []
    for i, cell in enumerate(cells):
        m = re.fullmatch(r'\x00(\d+)\x00', cell)
        if m:
            exp, found = mismatches_raw[int(m.group(1))]
            mismatches.append({"column": i, "expected": exp, "found": found})
            out_cells.append(f"E:{exp}/F:{found}")
        else:
            out_cells.append(cell)
    return out_cells, mismatches


def parse_cli_output_verbose(
    text: str,
    known_names: set[str] | None = None,
) -> dict[str, VerboseSection]:
    """Parse `CLI test -verbose` output into per-testcase sections.

    `known_names`: testcase names the caller expects (from TestSpecs).
    Lines shaped `<name>: <message>` where the message is neither
    "passed" nor "failed (N%)" are treated as that testcase's error
    ONLY if name is in known_names — this keeps java log noise
    (`INFO: ...`) from being misread as a result.
    """
    sections: dict[str, VerboseSection] = {}
    lines = text.splitlines()
    i = 0
    current: VerboseSection | None = None
    while i < len(lines):
        line = lines[i].rstrip()
        i += 1
        if not line or _FINAL_LINE_RE.match(line):
            current = None
            continue

        m = _V_FAIL_RE.match(line)
        if m:
            pct = int(m.group(2)) if m.group(2) else None
            current = VerboseSection(
                name=m.group(1), status="failed", fail_pct=pct,
                error_message=None,
            )
            sections[current.name] = current
            # The value table (if -verbose) starts on the next line.
            if i < len(lines):
                nxt = lines[i].rstrip()
                header_cells = nxt.split()
                if (header_cells and not _FINAL_LINE_RE.match(nxt)
                        and not _is_result_line(nxt)):
                    current.headers = header_cells
                    i += 1
                    clean = True
                    while i < len(lines):
                        row_line = lines[i].rstrip()
                        if not row_line or _FINAL_LINE_RE.match(row_line):
                            break
                        if _is_result_line(row_line):
                            break
                        split = _split_table_line(row_line, len(header_cells))
                        if split is None:
                            clean = False
                            i += 1
                            continue
                        _cells, mismatches = split
                        for mm in mismatches:
                            mm["column"] = (
                                header_cells[mm["column"]]
                                if mm["column"] < len(header_cells) else None
                            )
                        current.row_lines.append(row_line)
                        current.row_failed.append(bool(mismatches))
                        current.row_mismatches.append(mismatches)
                        i += 1
                    current.table_ok = clean and bool(current.row_lines)
            continue

        m = _V_PASS_RE.match(line)
        if m:
            sections[m.group(1)] = VerboseSection(
                name=m.group(1), status="passed", fail_pct=None,
                error_message=None, table_ok=True,
            )
            current = None
            continue

        # `<name>: <error message>` for an expected testcase name only
        # (keeps java log noise from being misread as a result).
        if known_names:
            for nm in known_names:
                if line.startswith(nm + ":"):
                    msg = line[len(nm) + 1:].strip()
                    if msg:
                        sections[nm] = VerboseSection(
                            name=nm, status="error", fail_pct=None,
                            error_message=msg,
                        )
                        current = None
                    break
    return sections