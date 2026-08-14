"""Build the canonical 30-intersection SUMO network from committed sources.

The formal network is a 6 x 5 grid (J01-J30).  Node and edge sources are
versioned in ``sumo_files``; this command regenerates ``xiongan_30.net.xml``
with SUMO's ``netconvert`` and verifies the public intersection contract.
Traffic demand is maintained separately by ``generate_real_demand_scenarios``.
"""
from __future__ import annotations

> ⚠️ 已废弃：本脚本生成的是旧版 20 路口（5×4）路网。当前项目以 30 路口
> （6×5，J01–J30）路网为准，路网文件为仓库内已提交的 sumo_files/xiongan_30.*
> 系列（nod/edg/net/rou/sumocfg 均保留）。运行本脚本会重建已删除的
> xiongan_20.* 旧文件，仅保留作历史参考。

使用netconvert工具配合nod.xml和edg.xml文件生成路网，避免手动编写复杂的net.xml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMO_FILES_DIR = PROJECT_ROOT / "sumo_files"
NODE_FILE = SUMO_FILES_DIR / "xiongan_30.nod.xml"
EDGE_FILE = SUMO_FILES_DIR / "xiongan_30.edg.xml"
NET_FILE = SUMO_FILES_DIR / "xiongan_30.net.xml"
EXPECTED_IDS = tuple(f"J{i:02d}" for i in range(1, 31))


def find_netconvert() -> str:
    """Return the configured netconvert executable."""
    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        candidate = Path(sumo_home) / "bin" / (
            "netconvert.exe" if os.name == "nt" else "netconvert"
        )
        if candidate.is_file():
            return str(candidate)
    executable = shutil.which("netconvert")
    if executable:
        return executable
    raise FileNotFoundError("未找到 netconvert；请先设置 SUMO_HOME")


def validate_sources() -> None:
    """Ensure the source files describe exactly J01-J30."""
    missing_files = [str(path) for path in (NODE_FILE, EDGE_FILE) if not path.is_file()]
    if missing_files:
        raise FileNotFoundError("缺少30路口源文件: " + ", ".join(missing_files))

    root = ET.parse(NODE_FILE).getroot()
    actual = tuple(
        node.get("id") for node in root.findall("node")
        if (node.get("id") or "").startswith("J") and (node.get("id") or "")[1:].isdigit()
    )
    if set(actual) != set(EXPECTED_IDS):
        raise ValueError(f"节点契约不一致：期望 J01-J30，实际核心节点 {sorted(actual)}")


def validate_network(path: Path) -> None:
    """Verify the generated network exposes all 30 controlled junctions."""
    root = ET.parse(path).getroot()
    traffic_lights = {logic.get("id") for logic in root.findall("tlLogic")}
    missing = sorted(set(EXPECTED_IDS) - traffic_lights)
    if missing:
        raise ValueError(f"生成路网缺少信号灯: {missing}")


def build_network(output: Path = NET_FILE) -> Path:
    validate_sources()
    command = [
        find_netconvert(),
        "--node-files", str(NODE_FILE),
        "--edge-files", str(EDGE_FILE),
        "--output-file", str(output),
        "--no-turnarounds", "true",
    ]
    subprocess.run(command, cwd=SUMO_FILES_DIR, check=True)
    validate_network(output)
    print(f"[OK] 已生成30路口路网: {output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="生成并验证雄安 J01-J30 SUMO 路网")
    parser.add_argument("--output", type=Path, default=NET_FILE, help="输出 net.xml 路径")
    args = parser.parse_args()
    try:
        build_network(args.output.resolve())
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
