"""
训练启动脚本

使用方法：
1. 在终端运行：python training/start_training.py
2. 在另一个终端运行：tensorboard --logdir=logs/
3. 在浏览器打开：http://localhost:6006/
"""

import os
import subprocess
import sys

def main():
    # 检查是否安装了tensorboard
    try:
        import tensorboard
        print("✅ TensorBoard已安装")
    except ImportError:
        print("⚠️ 安装TensorBoard...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tensorboard"])
    
    # 创建目录
    os.makedirs("./logs", exist_ok=True)
    os.makedirs("./models", exist_ok=True)
    
    # 启动训练
    print("\n🚀 开始DQN训练...")
    print("📊 请在另一个终端运行: tensorboard --logdir=logs/")
    print("🌐 然后在浏览器打开: http://localhost:6006/")
    print("\n" + "=" * 60 + "\n")
    
    subprocess.run([sys.executable, "training/train_dqn.py"])

if __name__ == "__main__":
    main()
