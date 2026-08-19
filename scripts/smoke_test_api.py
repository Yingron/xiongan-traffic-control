"""api_server 冒烟测试：session → predict（掩码链路）→ actions → state

验证正式模型（26 维掩码）通过 api_server 完整推理链路可跑通。
用法: python scripts/smoke_test_api.py
"""
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://127.0.0.1:8000/api/v1"
API_PREFIX = "/api/v1"


def call(method: str, path: str, payload: dict | None = None) -> dict:
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        raise SystemExit(f"[FAIL] {method} {path}: HTTP {e.code} {body}")


def main() -> None:
    # 1. 启动仿真 session（晚高峰场景）
    r = call("POST", "/simulation/start", {"scenario": "real_evening", "use_gui": False})
    sid = r["session_id"]
    print(f"[OK] simulation/start -> session {sid}")

    # 2. 用 evening 正式模型 predict（26 维掩码链路）
    r = call("POST", "/model/predict", {"session_id": sid, "model_id": "shared-dqn-real-evening-masked-1m-v1"})
    actions = r["actions"]
    assert set(actions) == {f"J{i:02d}" for i in range(1, 31)}, "actions 应覆盖 J01-J30"
    assert all(0 <= a <= 3 for a in actions.values()), "动作应在 [0,3]"
    print(f"[OK] predict(evening) -> 30 动作, 耗时 {r['inference_latency_ms']}ms, "
          f"契约 {r['model_contract_version']}, 示例 J01={actions['J01']}")

    # 3. 用 offpeak 别名（指向 evening）predict
    r = call("POST", "/model/predict", {"session_id": sid, "model_id": "shared-dqn-real-offpeak-via-evening-v1"})
    print(f"[OK] predict(offpeak-alias) -> 30 动作, 契约 {r['model_contract_version']}")

    # 4. 提交动作
    r = call("POST", "/simulation/actions",
             {"session_id": sid, "expected_transition_id": 0, "actions": actions, "step_seconds": 5})
    print(f"[OK] simulation/actions -> transition {r.get('transition_id')}")

    # 5. 读状态（660 维契约）
    r = call("GET", "/simulation/state?session_id=" + sid)
    flat = r.get("state_vector")
    n = len(flat) if flat is not None else -1
    assert n == 660, f"state_vector 应为 660 维，实际 {n}"
    print(f"[OK] simulation/state -> {n} 维 (30x22 契约)")

    # 6. 收尾
    call("POST", "/simulation/stop", {"session_id": sid})
    print("[OK] simulation/stop")
    print("\n=== api_server 冒烟测试全部通过 ===")


if __name__ == "__main__":
    main()
