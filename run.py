"""主启动脚本 - 项目统一入口"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="雄安新区30路口车路云一体化协同管控平台"
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    subparsers.add_parser("validate", help="验证项目设置")
    subparsers.add_parser("build", help="构建SUMO路网")
    subparsers.add_parser("serve", help="启动API服务")
    subparsers.add_parser("train", help="启动DQN训练")
    subparsers.add_parser("eval", help="评估模型性能")

    args = parser.parse_args()

    if args.command == "validate":
        from scripts.validate_setup import main as validate
        validate()
    elif args.command == "build":
        print("请运行: scripts/build_and_validate.ps1")
    elif args.command == "serve":
        print("请运行: python server/api_server.py")
    elif args.command == "train":
        print("请运行: python training/train_dqn.py")
    elif args.command == "eval":
        print("请运行: python evaluate_policy.py")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
