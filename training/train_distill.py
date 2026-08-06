import argparse
import os
import sys

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stable_baselines3 import DQN
try:
    from stable_baselines3 import D3QN
except ImportError:
    D3QN = DQN  # 兼容旧版本
from env.xiongan_env import XionganEnv
from training.config import ENV_CONFIG, DISTILL_CONFIG, MODEL_DIR


class StudentNetwork(nn.Module):
    def __init__(self, input_dim=26, output_dim=4, hidden_layers=[64, 64]):
        super().__init__()
        layers = []
        prev_dim = input_dim
        
        for hidden_dim in hidden_layers:
            layers.append(nn.Linear(prev_dim, hidden_dim))
            layers.append(nn.ReLU())
            prev_dim = hidden_dim
        
        layers.append(nn.Linear(prev_dim, output_dim))
        
        self.model = nn.Sequential(*layers)
    
    def forward(self, x):
        return self.model(x)


def distill_knowledge(args):
    env_config = ENV_CONFIG.copy()
    env_config['use_gui'] = False
    env = XionganEnv(**env_config)

    teacher_path = DISTILL_CONFIG['teacher_model_path']
    if not os.path.exists(teacher_path):
        print(f"Teacher model not found: {teacher_path}")
        return

    print(f"Loading teacher model from {teacher_path}...")
    
    if 'd3qn' in teacher_path.lower():
        teacher_model = D3QN.load(teacher_path)
    else:
        teacher_model = DQN.load(teacher_path)

    student_net = StudentNetwork(
        input_dim=26,
        output_dim=4,
        hidden_layers=DISTILL_CONFIG['student_hidden_layers']
    )

    optimizer = optim.Adam(student_net.parameters(), lr=DISTILL_CONFIG['distill_lr'])
    criterion_ce = nn.CrossEntropyLoss()
    criterion_mse = nn.MSELoss()

    temperature = DISTILL_CONFIG['temperature']
    alpha = DISTILL_CONFIG['alpha']

    print(f"Starting knowledge distillation...")
    print(f"Epochs: {DISTILL_CONFIG['distill_epochs']}")
    print(f"Temperature: {temperature}")
    print(f"Alpha: {alpha}")

    for epoch in range(DISTILL_CONFIG['distill_epochs']):
        obs, _ = env.reset()
        done = False
        total_loss = 0
        steps = 0

        while not done:
            teacher_action, _ = teacher_model.predict(obs, deterministic=True)
            teacher_q_values = teacher_model.policy.predict_values(torch.tensor(obs, dtype=torch.float32).unsqueeze(0))
            
            student_q_values = student_net(torch.tensor(obs, dtype=torch.float32).unsqueeze(0))

            soft_teacher = nn.functional.softmax(teacher_q_values / temperature, dim=1)
            soft_student = nn.functional.log_softmax(student_q_values / temperature, dim=1)
            
            distill_loss = nn.KLDivLoss(reduction='batchmean')(soft_student, soft_teacher) * (temperature ** 2)
            
            hard_loss = criterion_mse(student_q_values, teacher_q_values)
            
            loss = alpha * distill_loss + (1 - alpha) * hard_loss

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            steps += 1

            action, _ = teacher_model.predict(obs, deterministic=True)
            obs, _, done, _, _ = env.step(action)

        avg_loss = total_loss / steps
        print(f"Epoch {epoch+1}/{DISTILL_CONFIG['distill_epochs']}: Loss={avg_loss:.4f}")

    student_path = DISTILL_CONFIG['student_model_path']
    torch.save(student_net.state_dict(), student_path.replace('.zip', '.pth'))
    print(f"Student model saved to {student_path}")

    quantized_model = torch.quantization.quantize_dynamic(
        student_net,
        {nn.Linear},
        dtype=torch.qint8
    )

    quantized_path = DISTILL_CONFIG['quantized_model_path']
    torch.jit.save(torch.jit.script(quantized_model), quantized_path)
    print(f"Quantized model saved to {quantized_path}")

    env.close()


def quantize_model(args):
    student_path = DISTILL_CONFIG['student_model_path'].replace('.zip', '.pth')
    
    if not os.path.exists(student_path):
        print(f"Student model not found: {student_path}")
        return

    student_net = StudentNetwork(
        input_dim=26,
        output_dim=4,
        hidden_layers=DISTILL_CONFIG['student_hidden_layers']
    )
    
    student_net.load_state_dict(torch.load(student_path))
    student_net.eval()

    quantized_model = torch.quantization.quantize_dynamic(
        student_net,
        {nn.Linear},
        dtype=torch.qint8
    )

    quantized_path = DISTILL_CONFIG['quantized_model_path']
    torch.jit.save(torch.jit.script(quantized_model), quantized_path)
    print(f"Quantized model saved to {quantized_path}")

    import os
    model_size = os.path.getsize(quantized_path) / 1024
    print(f"Quantized model size: {model_size:.2f} KB")


def main():
    parser = argparse.ArgumentParser(description='Knowledge distillation and model quantization')
    parser.add_argument('--distill', action='store_true', help='Perform knowledge distillation')
    parser.add_argument('--quantize', action='store_true', help='Perform model quantization')
    parser.add_argument('--gui', action='store_true', help='Use SUMO GUI')

    args = parser.parse_args()

    if args.distill:
        distill_knowledge(args)
    elif args.quantize:
        quantize_model(args)
    else:
        distill_knowledge(args)
        quantize_model(args)


if __name__ == '__main__':
    main()