"""F7 combinational-loop checker"""

import glob
from pathlib import Path

from dlc.parser.dig_parser import parse_dig_file
from dlc.analyzer.combinational_loops import check_combinational_loops
from dlc.analyzer.wire_completeness import IssueSeverity

SAMPLES = Path(__file__).parent.parent / "data" / "sample_circuits"


def test_combinational_loop_bug_sample_surfaces_issue():
    c = parse_dig_file(str(SAMPLES / "tier1_bug" / "combinational_loop.dig"))
    issues = check_combinational_loops(c)
    loops = issues.by_kind("combinational_loop")
    assert len(loops) >= 1
    assert all(i.severity == IssueSeverity.ERROR for i in loops)
    assert loops[0].location is not None


def test_clean_tier_samples_produce_no_loop_issues():
    """tier1_minimal + tier2_structured + tier3_realistic all clean."""
    for tier in ("tier1_minimal", "tier2_structured", "tier3_realistic"):
        for f in glob.glob(f"data/sample_circuits/{tier}/*.dig"):
            c = parse_dig_file(f)
            issues = check_combinational_loops(c)
            assert len(issues.issues) == 0, f"{f}: unexpected loop issues"


def test_run_all_l1_aggregator_includes_combinational_loop_kind():
    from dlc.analyzer import check_all_l1
    c = parse_dig_file(str(SAMPLES / "tier1_bug" / "combinational_loop.dig"))
    issues = check_all_l1(c)
    assert len(issues.by_kind("combinational_loop")) >= 1