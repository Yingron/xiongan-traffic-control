"""Static regression checks for the repository-wide 30-intersection contract."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from configs.constants import (
    INTERSECTION_COUNT,
    INTERSECTION_ORDER,
    STATE_DIMENSION,
    STATE_LAYOUT_VERSION,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNITY_MAP = PROJECT_ROOT / "frontend" / "CitySimulation" / "Assets" / "Scripts" / "Maps" / "xiongan_30.json"
UNITY_SCRIPT_ROOT = PROJECT_ROOT / "frontend" / "CitySimulation" / "Assets" / "Scripts"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_core_contract_is_30_by_22() -> None:
    assert INTERSECTION_COUNT == 30
    assert INTERSECTION_ORDER == tuple(f"J{i:02d}" for i in range(1, 31))
    assert STATE_DIMENSION == 660
    assert STATE_LAYOUT_VERSION == "v1-30x22"


def test_interface_registry_and_mappings_match_contract() -> None:
    interface = _read_json(PROJECT_ROOT / "docs" / "interface_contract.json")
    registry = _read_json(PROJECT_ROOT / "configs" / "model_registry.json")
    lane_mapping = _read_json(PROJECT_ROOT / "docs" / "lane_mapping.json")
    tls_mapping = _read_json(PROJECT_ROOT / "docs" / "tls_mapping.json")

    assert tuple(interface["junction_order"]) == INTERSECTION_ORDER
    assert interface["intersection_count"] == INTERSECTION_COUNT
    assert interface["global_state_dimension"] == STATE_DIMENSION
    assert interface["state_layout_version"] == STATE_LAYOUT_VERSION
    assert tuple(lane_mapping) == INTERSECTION_ORDER
    assert tuple(tls_mapping) == INTERSECTION_ORDER
    for entry in registry["models"].values():
        assert entry["intersection_count"] == INTERSECTION_COUNT
        assert entry["global_state_dimension"] == STATE_DIMENSION
        assert entry["state_layout_version"] == STATE_LAYOUT_VERSION


def test_sumo_and_unity_assets_expose_exactly_j01_through_j30() -> None:
    net_root = ET.parse(PROJECT_ROOT / "sumo_files" / "xiongan_30.net.xml").getroot()
    net_ids = {logic.attrib["id"] for logic in net_root.findall("tlLogic")}
    assert set(INTERSECTION_ORDER).issubset(net_ids)

    assert UNITY_MAP.is_file(), f"missing generated Unity map: {UNITY_MAP}"
    snapshot = _read_json(UNITY_MAP)["snapshot"]
    ids = [item["id"] for item in snapshot["trafficLights"]]
    assert len(ids) == INTERSECTION_COUNT
    assert set(ids) == set(INTERSECTION_ORDER)


def test_unity_runtime_defaults_to_formal_map() -> None:
    map_manager = (UNITY_SCRIPT_ROOT / "GameObjects" / "MapManager.cs").read_text(encoding="utf-8")
    function_interface = (
        UNITY_SCRIPT_ROOT / "Runtime" / "Simulation" / "FunctionInterface.cs"
    ).read_text(encoding="utf-8")
    network_interface = (
        UNITY_SCRIPT_ROOT / "Runtime" / "Simulation" / "NetworkInterface.cs"
    ).read_text(encoding="utf-8")
    assert 'mapId = "xiongan_30"' in map_manager
    assert 'Reset("xiongan_30")' in function_interface
    assert 'req.map_id) ? "xiongan_30" : req.map_id' in network_interface
