"""Tests for dlc.facts.net_width"""

from pathlib import Path

from dlc.parser.dig_parser import parse_dig_file
from dlc.parser.netlist import build_netlist
from dlc.facts.net_width import (
    infer_net_widths, width_of_net, NetWidthInfo, WidthConflict
)


SAMPLES_DIR = Path(__file__).parent.parent / "data" / "sample_circuits"


def _load_netlist(rel_path):
    c = parse_dig_file(str(SAMPLES_DIR / rel_path))
    nl = build_netlist(c)
    return c, nl


def test_full_adder_all_nets_one_bit():
    """All gates in full_adder are 1-bit; every net should be 1 bit."""
    c, nl = _load_netlist("tier1_minimal/full_adder.dig")
    per_net, conflicts = infer_net_widths(c, nl)
    assert conflicts == []
    for net in nl.nets:
        info = per_net[net.net_id]
        assert info.width == 1, f"net {net.net_id}: expected 1, got {info.width}"


def test_splitter_test_widths_4_and_ones():
    """splitter_test: In(Bus, Bits=4) -> Splitter -> 4 Outs of 1 bit each.
    One net is 4-bit (the bus), four nets are 1-bit (the splits)."""
    c, nl = _load_netlist("tier1_minimal/splitter_test.dig")
    per_net, conflicts = infer_net_widths(c, nl)
    assert conflicts == []
    widths = sorted(info.width for info in per_net.values() if info.width is not None)
    assert widths == [1, 1, 1, 1, 4]


def test_tier3_calculator_widths_include_1_2_4():
    """tier3_calculator has 4-bit data, 2-bit Op, 1-bit carry/flags."""
    c, nl = _load_netlist("tier3_realistic/tier3_calculator.dig")
    per_net, _ = infer_net_widths(c, nl)
    widths_present = {info.width for info in per_net.values() if info.width is not None}
    assert 1 in widths_present
    assert 2 in widths_present
    assert 4 in widths_present


def test_tier3_subcircuit_result_pin_width_resolved_from_child():
    """The net carrying bool_unit.Result must get its width from the
    child circuit's Out(Result) Bits, not None."""
    c, nl = _load_netlist("tier3_realistic/tier3_calculator.dig")
    per_net, _ = infer_net_widths(c, nl)
    found = False
    for net in nl.nets:
        for pin in net.pins:
            comp = c.components[pin.component_index]
            if comp.element_name.endswith(".dig") and pin.pin_name == "Result":
                assert per_net[net.net_id].width is not None, \
                    "bool_unit.Result net has no inferred width"
                found = True
    assert found, "bool_unit.Result pin not found in any net"


def test_bug_multi_driver_same_width_no_conflict():
    """multi_driver.dig: two 1-bit Ins on one net."""
    c, nl = _load_netlist("tier1_bug/multi_driver.dig")
    _, conflicts = infer_net_widths(c, nl)
    assert conflicts == []


def test_dangling_input_inherits_sink_width():
    """dangling_input.dig: AND.in1 is undriven. The dangling net should
    still report width=1 via the sink and tag source='sink'."""
    c, nl = _load_netlist("tier1_bug/dangling_input.dig")
    per_net, _ = infer_net_widths(c, nl)
    dangling = [net for net in nl.nets if net.pins and not net.drivers()]
    assert len(dangling) >= 1
    info = per_net[dangling[0].net_id]
    assert info.width == 1
    assert info.source == "sink"


def test_width_of_net_convenience_matches_full_pass():
    """width_of_net returns the same width as the full pass for each net."""
    c, nl = _load_netlist("tier1_minimal/splitter_test.dig")
    per_net, _ = infer_net_widths(c, nl)
    for net in nl.nets:
        expected = per_net[net.net_id].width
        assert width_of_net(c, nl, net.net_id) == expected


def test_per_net_info_source_tag_one_of_three():
    """Every returned NetWidthInfo records 'driver', 'sink', or 'unknown'."""
    c, nl = _load_netlist("tier1_minimal/full_adder.dig")
    per_net, _ = infer_net_widths(c, nl)
    for info in per_net.values():
        assert info.source in ("driver", "sink", "unknown")


def test_width_conflict_dataclass_fields():
    """WidthConflict instances carry net_id + two pin names + two widths."""
    wc = WidthConflict(
        net_id=5,
        driver_a_name="Add.s",
        driver_a_width=4,
        driver_b_name="In.out",
        driver_b_width=1,
    )
    assert wc.net_id == 5
    assert wc.driver_a_width == 4
    assert wc.driver_b_width == 1