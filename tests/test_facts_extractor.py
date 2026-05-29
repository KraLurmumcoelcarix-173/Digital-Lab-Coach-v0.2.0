"""
Tests for dlc.facts.extractor.
"""

from pathlib import Path

from dlc.parser.dig_parser import parse_dig_file
from dlc.parser.netlist import build_netlist
from dlc.parser.graph import build_signal_graph
from dlc.facts.extractor import (
    extract_facts,
    CircuitFacts,
    IOFact,
    ComponentFact,
    SubcircuitFact,
    NetFact,
    BugFact,
)


SAMPLES_DIR = Path(__file__).parent.parent / "data" / "sample_circuits"


def _facts(rel_path: str):
    c = parse_dig_file(str(SAMPLES_DIR / rel_path))
    return c, extract_facts(c)


# Shape / dataclass identity

def test_extract_facts_returns_circuit_facts_dataclass():
    c, f = _facts("tier1_minimal/single_and.dig")
    assert isinstance(f, CircuitFacts)
    assert f.source_path is not None and "single_and.dig" in f.source_path
    assert f.format_version == 2


def test_extract_facts_accepts_prebuilt_netlist_and_graph():
    """Caller can share already-built netlist / graph instead of re-doing
    the work twice."""
    c = parse_dig_file(str(SAMPLES_DIR / "tier1_minimal/single_and.dig"))
    nl = build_netlist(c)
    g = build_signal_graph(c, nl)
    f = extract_facts(c, netlist=nl, graph=g)
    assert f.header["net_count"] == len(nl.nets)


# Header / inventory

def test_header_counts_match_circuit():
    c, f = _facts("tier1_minimal/full_adder.dig")
    assert f.header["component_count"] == len(c.components)
    assert f.header["wire_count"] == len(c.wires)
    assert f.header["subcircuit_count"] == len(c.subcircuits)
    assert f.header["input_count"] == len(c.inputs())
    assert f.header["output_count"] == len(c.outputs())
    assert f.header["bug_count"] == len(f.bugs)


def test_inventory_counts_components_by_element_name():
    """full_adder.dig: 3 In, 2 Out, 2 XOr, 2 And, 1 Or."""
    c, f = _facts("tier1_minimal/full_adder.dig")
    assert f.inventory.get("In") == 3
    assert f.inventory.get("Out") == 2
    assert f.inventory.get("XOr") == 2
    assert f.inventory.get("And") == 2
    assert f.inventory.get("Or") == 1


# I/O facts

def test_io_facts_carry_label_and_bit_width():
    c, f = _facts("tier1_minimal/single_and.dig")
    in_labels = {io.label for io in f.inputs}
    assert in_labels == {"A", "B"}
    for io in f.inputs:
        assert io.bit_width == 1
        assert io.direction == "in"
    out_labels = {io.label for io in f.outputs}
    assert out_labels == {"Y"}
    for io in f.outputs:
        assert io.direction == "out"


def test_io_fact_bit_widths_pick_up_attribute():
    c, f = _facts("tier3_realistic/tier3_calculator.dig")
    by_label = {io.label: io.bit_width for io in f.inputs}
    assert by_label["A"] == 4
    assert by_label["B"] == 4
    assert by_label["Op"] == 2


# Component facts 

def test_component_topology_predecessors_successors():
    c, f = _facts("tier1_minimal/single_and.dig")
    and_fact = next(cf for cf in f.components if cf.element_name == "And")
    in_indices = {cf.index for cf in f.components if cf.element_name == "In"}
    out_indices = {cf.index for cf in f.components if cf.element_name == "Out"}
    assert set(and_fact.predecessors) == in_indices
    assert set(and_fact.successors) == out_indices


def test_component_facts_include_attributes_and_position():
    c, f = _facts("tier1_minimal/comparator_4bit.dig")
    cmp_fact = next(cf for cf in f.components if cf.element_name == "Comparator")
    assert cmp_fact.attributes.get("Bits") == 4
    assert cmp_fact.bit_width == 4
    assert isinstance(cmp_fact.position, tuple)
    assert len(cmp_fact.position) == 2


def test_component_bit_width_none_when_bits_absent():
    c, f = _facts("tier1_minimal/splitter_test.dig")
    split = next(cf for cf in f.components if cf.element_name == "Splitter")
    assert split.bit_width is None


# Net facts


def test_net_facts_cover_every_net():
    c, f = _facts("tier1_minimal/half_adder.dig")
    assert len(f.nets) == 4
    for nf in f.nets:
        assert nf.driver_count + nf.sink_count <= nf.pin_count


def test_net_facts_carry_inferred_width():
    c, f = _facts("tier1_minimal/splitter_test.dig")
    widths = sorted(n.bit_width for n in f.nets if n.bit_width is not None)
    assert widths == [1, 1, 1, 1, 4]


def test_net_facts_pin_dicts_have_pin_width_field():
    c, f = _facts("tier1_minimal/single_and.dig")
    for nf in f.nets:
        for p in nf.pins:
            assert "pin_width" in p
    and_pins = [
        p for nf in f.nets for p in nf.pins
        if p["element_name"] == "And"
    ]
    assert all(p["pin_width"] == 1 for p in and_pins)


def test_net_anomaly_tag_for_dangling_input():
    c, f = _facts("tier1_bug/dangling_input.dig")
    flagged = [n for n in f.nets if "dangling_input" in n.anomalies]
    assert len(flagged) == 1
    assert "undriven" in flagged[0].anomalies


def test_net_anomaly_tag_for_multi_driver():
    c, f = _facts("tier1_bug/multi_driver.dig")
    flagged = [n for n in f.nets if "multi_driver" in n.anomalies]
    assert len(flagged) == 1


# Subcircuit hierarchy

def test_subcircuit_facts_include_child_interface():
    c, f = _facts("tier2_structured/uses_subcircuit.dig")
    assert len(f.subcircuits) == 1
    sub = f.subcircuits[0]
    assert sub.reference == "subcircuit_inner.dig"
    assert sub.resolution_error is None
    assert sub.child_source_path is not None
    in_labels = {ci["label"] for ci in sub.child_inputs}
    out_labels = {co["label"] for co in sub.child_outputs}
    assert in_labels == {"A", "B"}
    assert out_labels == {"Y"}


def test_subcircuit_instance_index_points_to_real_component():
    c, f = _facts("tier2_structured/uses_subcircuit.dig")
    sub = f.subcircuits[0]
    assert 0 <= sub.instance_index < len(c.components)
    assert c.components[sub.instance_index].element_name.endswith(".dig")


# Bug list — clean circuits

def test_no_bugs_for_clean_tier1_circuit():
    c, f = _facts("tier1_minimal/full_adder.dig")
    assert f.bugs == []


def test_no_bugs_for_clean_tier3_calculator():
    c, f = _facts("tier3_realistic/tier3_calculator.dig")
    assert f.bugs == []


def test_width_mismatch_not_reported_at_f3_level():
    c, f = _facts("tier1_bug/width_mismatch.dig")
    assert f.bugs == []


# Bug list — bug circuits

def test_dangling_input_appears_in_bug_list():
    c, f = _facts("tier1_bug/dangling_input.dig")
    dangling = [b for b in f.bugs if b.kind == "dangling_input"]
    assert len(dangling) == 1
    bug = dangling[0]
    assert bug.net_id is not None
    assert any(
        p["element_name"] == "And" and p["pin_name"] == "in1"
        for p in bug.detail["pins"]
    )


def test_multi_driver_appears_in_bug_list():
    c, f = _facts("tier1_bug/multi_driver.dig")
    multi = [b for b in f.bugs if b.kind == "multi_driver"]
    assert len(multi) == 1
    assert len(multi[0].detail["drivers"]) >= 2
    assert multi[0].net_id is not None


def test_combinational_cycle_appears_in_bug_list():
    c, f = _facts("tier1_bug/combinational_loop.dig")
    cycles = [b for b in f.bugs if b.kind == "combinational_cycle"]
    assert len(cycles) >= 1
    cyc_order = cycles[0].detail["cycle_order"]
    elems = [c.components[i].element_name for i in cyc_order]
    assert elems.count("Not") == 2


def test_clocked_feedback_does_not_fire_combinational_cycle():
    """register_test.dig has a Register; no purely-combinational cycle
    should be reported."""
    c, f = _facts("tier1_minimal/register_test.dig")
    cycles = [b for b in f.bugs if b.kind == "combinational_cycle"]
    assert cycles == []


def test_missing_subcircuit_appears_in_bug_list(tmp_path):
    parent = tmp_path / "parent.dig"
    parent.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        '<circuit><version>2</version><attributes/>'
        '<visualElements>'
        '<visualElement><elementName>does_not_exist.dig</elementName>'
        '<elementAttributes/><pos x="0" y="0"/></visualElement>'
        '</visualElements><wires/></circuit>'
    )
    c = parse_dig_file(str(parent))
    f = extract_facts(c)
    missing = [b for b in f.bugs if b.kind == "missing_subcircuit"]
    assert len(missing) == 1
    assert "does_not_exist.dig" in missing[0].description
    assert missing[0].component_indices == [0]


def test_width_conflict_reported_when_two_drivers_differ():
    """ F3 should surface a width_conflict bug AND a multi_driver bug."""
    from dlc.parser.models import Circuit, Component, Position, Wire
    c = Circuit(
        format_version=2,
        components=[
            Component("In", Position(0, 0), {"Label": "A", "Bits": 4}, label="A"),
            Component("In", Position(0, 40), {"Label": "B", "Bits": 1}, label="B"),
            Component("Out", Position(80, 20), {"Label": "Y"}, label="Y"),
        ],
        wires=[
            Wire(Position(0, 0), Position(0, 40)),
            Wire(Position(0, 0), Position(80, 20)),
        ],
        source_path="synthetic",
    )
    f = extract_facts(c)
    width_bugs = [b for b in f.bugs if b.kind == "width_conflict"]
    assert len(width_bugs) == 1
    assert width_bugs[0].detail["driver_a"]["width"] != width_bugs[0].detail["driver_b"]["width"]


# Cross-checks

def test_inventory_total_equals_component_count():
    c, f = _facts("tier3_realistic/tier3_calculator.dig")
    assert sum(f.inventory.values()) == f.header["component_count"]

def test_every_net_id_unique_and_matches_netlist():
    c, f = _facts("tier1_minimal/full_adder.dig")
    ids = [n.net_id for n in f.nets]
    assert len(ids) == len(set(ids))
    assert max(ids) + 1 == len(ids)
