"""快速启动脚本 - 验证TraCI API"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from server.traci_service import TraCIService
from server.state_extractor import StateExtractor
from server.reward_calculator import RewardCalculator
from configs.constants import (
    INTERSECTION_ORDER, STATE_DIMENSION, FEATURES_PER_INTERSECTION
)


def validate_imports() -> None:
    """验证核心模块导入"""
    print("=" * 50)
    print("模块导入验证")
    print("=" * 50)
    print(f"[OK] TraCIService: {TraCIService}")
    print(f"[OK] StateExtractor: {StateExtractor}")
    print(f"[OK] RewardCalculator: {RewardCalculator}")
    print(f"[OK] 路口数量: {len(INTERSECTION_ORDER)}")
    print(f"[OK] 状态维度: {STATE_DIMENSION}")
    print(f"[OK] 每路口特征: {FEATURES_PER_INTERSECTION}")


def validate_constants() -> None:
    """验证常量配置"""
    print("\n" + "=" * 50)
    print("常量配置验证")
    print("=" * 50)
    for idx, jid in enumerate(INTERSECTION_ORDER):
        offset_start = idx * FEATURES_PER_INTERSECTION
        offset_end = (idx + 1) * FEATURES_PER_INTERSECTION
        print(f"  {jid}: state[{offset_start}:{offset_end}]")
    print(f"\n[OK] 总维度: {len(INTERSECTION_ORDER) * FEATURES_PER_INTERSECTION}")


def validate_reward() -> None:
    """验证奖励计算器"""
    print("\n" + "=" * 50)
    print("奖励函数验证")
    print("=" * 50)

    import numpy as np
    calc = RewardCalculator()
    dummy_state = np.random.rand(FEATURES_PER_INTERSECTION).astype(np.float32)
    reward, breakdown = calc.compute_reward(dummy_state, 0, 0)

    print(f"  奖励值: {reward:.4f}")
    print(f"  分解:")
    for key, value in breakdown.items():
        print(f"    {key}: {value:.4f}")


def validate_network_exists() -> None:
    """验证路网文件存在"""
    print("\n" + "=" * 50)
    print("路网文件验证")
    print("=" * 50)

    from configs.constants import SUMO_FILES_DIR
    required_files = [
        "xiongan.nod.xml",
        "xiongan.edg.xml",
        "xiongan.rou.xml",
        "xiongan_morning.rou.xml",
        "xiongan_flat.rou.xml",
        "xiongan_evening.rou.xml",
    ]

    for filename in required_files:
        filepath = SUMO_FILES_DIR / filename
        exists = filepath.exists()
        size = filepath.stat().st_size if exists else 0
        status = f"[OK] ({size:,} bytes)" if exists else "[FAIL] 缺失"
        print(f"  {filename}: {status}")

    net_file = SUMO_FILES_DIR / "xiongan.net.xml"
    if net_file.exists():
<<<<<<< Updated upstream
        print(f"  xiongan.net.xml: ✅ ({net_file.stat().st_size:,} bytes)")
    else:
        print(f"  xiongan.net.xml: ⚠️ 需要运行build_and_validate.ps1生成")
=======
        print(f"  xiongan_30.net.xml: [OK] ({net_file.stat().st_size:,} bytes)")
    else:
        print(f"  xiongan_30.net.xml: [WARN] 需要运行 netconvert 生成")
>>>>>>> Stashed changes


def main() -> None:
    print("\n" + "#" * 60)
    print("# 雄安新区20路口车路云一体化协同管控平台 - 验证")
    print("#" * 60 + "\n")

    try:
        validate_imports()
    except Exception as e:
        print(f"[FAIL] 导入失败: {e}")
        sys.exit(1)

    validate_constants()
    validate_reward()
    validate_network_exists()

    print("\n" + "=" * 50)
    print("基础验证完成！")
    print("=" * 50)
    print("\n下一步操作:")
    print("1. 运行 scripts/build_and_validate.ps1 校验已提交的30路口路网与映射")
    print("2. 设置 SUMO_HOME 环境变量")
    print("3. 启动 API: python server/api_server.py")
    print("4. 启动训练: python training/train_dqn.py")


if __name__ == "__main__":
    main()
