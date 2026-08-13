"""Regenerate docs/tls_mapping.json from the committed 30-intersection SUMO net."""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from configs.constants import ACTION_NAMES, INTERSECTION_ORDER  # noqa: E402

NET_FILE = PROJECT_ROOT / "sumo_files" / "xiongan_30.net.xml"
OUT_FILE = PROJECT_ROOT / "docs" / "tls_mapping.json"


def main() -> None:
    root = ET.parse(NET_FILE).getroot()
    programs = {
        logic.attrib["id"]: logic
        for logic in root.findall("tlLogic")
        if logic.attrib.get("programID") == "rl4"
    }
    missing = [junction_id for junction_id in INTERSECTION_ORDER if junction_id not in programs]
    if missing:
        raise ValueError(f"Missing rl4 programs: {', '.join(missing)}")

    mapping = {}
    for junction_id in INTERSECTION_ORDER:
        phases = programs[junction_id].findall("phase")
        if len(phases) != len(ACTION_NAMES):
            raise ValueError(f"{junction_id} must expose exactly four rl4 phases")
        states = [phase.attrib["state"] for phase in phases]
        mapping[junction_id] = {
            "tls_id": junction_id,
            "action_to_phase": {str(index): index for index in range(len(ACTION_NAMES))},
            "action_semantics": {
                str(index): name for index, name in enumerate(ACTION_NAMES)
            },
            "state_length": len(states[0]),
            "phase_states": states,
        }

    OUT_FILE.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[OK] {OUT_FILE.name}: {len(mapping)} intersections")


if __name__ == "__main__":
    main()
