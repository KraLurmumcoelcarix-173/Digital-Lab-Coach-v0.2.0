"""
F4 : TestSpec extractor.

Given a parsed Circuit, walk its Testcase elements, parse the
`<dataString>` text into a structured `TestSpec` per testcase, and
match each header column to a top-level circuit port.
"""

from dataclasses import dataclass, field

from dlc.parser.models import Circuit


@dataclass(frozen=True)
class Token:

    raw: str
    kind: str            # "int" | "clock" | "highZ" | "dontcare" | "loop_expr" | "unknown"
    value: int | None    


@dataclass
class TestRow:
    __test__ = False

    raw: str
    values: list[Token] = field(default_factory=list)
    line_index: int = 0
    is_malformed: bool = False


@dataclass(frozen=True)
class VariableBinding:
    name: str
    role: str                       # "input" | "output" | "clock" | "unbound"
    component_index: int | None
    bit_width: int | None


@dataclass
class TestSpec:
    """One Testcase from a circuit, parsed into rows."""
    __test__ = False

    name: str                       
    component_index: int          
    headers: list[str]
    rows: list[TestRow]
    raw_data_string: str
    has_unexpanded_loops: bool

    def row_count(self) -> int:
        return len(self.rows)

    def well_formed_row_count(self) -> int:
        return sum(1 for r in self.rows if not r.is_malformed)


