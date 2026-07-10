import torch
import numpy as np
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from training.config import DISTILL_CONFIG


class EdgeInference:
    def __init__(self, model_path=None):
        if model_path is None:
            model_path = DISTILL_CONFIG['quantized_model_path']
        
        self.model_path = model_path
        self.model = None
        self.load_model()
        self.warmup()

    def load_model(self):
        if not os.path.exists(self.model_path):
            print(f"Model not found: {self.model_path}")
            print("Trying to load unquantized model...")
            unquantized_path = self.model_path.replace('.pt', '.pth')
            if os.path.exists(unquantized_path):
                from training.train_distill import StudentNetwork
                self.model = StudentNetwork()
                self.model.load_state_dict(torch.load(unquantized_path))
                self.model.eval()
                print(f"Loaded unquantized model from {unquantized_path}")
            else:
                raise FileNotFoundError(f"Neither quantized nor unquantized model found")
        else:
            self.model = torch.jit.load(self.model_path)
            self.model.eval()
            print(f"Loaded quantized model from {self.model_path}")

    def warmup(self):
        dummy = torch.randn(1, 26)
        for _ in range(10):
            _ = self.model(dummy)

    def predict(self, state):
        start = time.perf_counter()
        with torch.no_grad():
            if isinstance(state, np.ndarray):
                input_tensor = torch.tensor(state, dtype=torch.float32).unsqueeze(0)
            else:
                input_tensor = state.unsqueeze(0)
            
            q_values = self.model(input_tensor)
            action = int(torch.argmax(q_values, dim=1).item())
        
        latency = (time.perf_counter() - start) * 1000
        return action, latency

    def benchmark(self, n_iter=1000):
        latencies = []
        for _ in range(n_iter):
            dummy = np.random.randn(26).astype(np.float32)
            _, lat = self.predict(dummy)
            latencies.append(lat)

        model_size = os.path.getsize(self.model_path) / 1024

        print("=" * 50)
        print("Edge Inference Benchmark Results")
        print("=" * 50)
        print(f"Model path: {self.model_path}")
        print(f"Model size: {model_size:.2f} KB")
        print(f"Mean latency: {np.mean(latencies):.2f} ms")
        print(f"P50 latency: {np.percentile(latencies, 50):.2f} ms")
        print(f"P90 latency: {np.percentile(latencies, 90):.2f} ms")
        print(f"P99 latency: {np.percentile(latencies, 99):.2f} ms")
        print(f"Max latency: {np.max(latencies):.2f} ms")
        print(f"Min latency: {np.min(latencies):.2f} ms")
        
        if model_size < 1024:
            print("✅ Model size < 1MB: PASS")
        else:
            print("❌ Model size >= 1MB: FAIL")
        
        if np.mean(latencies) < 5:
            print("✅ Mean latency < 5ms: PASS")
        else:
            print("❌ Mean latency >= 5ms: FAIL")
        print("=" * 50)

        return {
            'model_size_kb': model_size,
            'mean_latency_ms': np.mean(latencies),
            'p99_latency_ms': np.percentile(latencies, 99),
            'p90_latency_ms': np.percentile(latencies, 90),
            'max_latency_ms': np.max(latencies),
            'min_latency_ms': np.min(latencies)
        }

    def run_online_inference(self, state_generator, callback=None):
        while True:
            state = state_generator()
            action, latency = self.predict(state)
            
            if callback:
                callback(action, latency)
            
            print(f"Action: {action}, Latency: {latency:.2f}ms")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Edge inference for traffic signal control')
    parser.add_argument('--model', type=str, default=None, help='Path to model file')
    parser.add_argument('--benchmark', action='store_true', help='Run benchmark')
    parser.add_argument('--n', type=int, default=1000, help='Number of benchmark iterations')
    
    args = parser.parse_args()

    inference = EdgeInference(args.model)

    if args.benchmark:
        inference.benchmark(args.n)
    else:
        dummy_state = np.random.randn(26).astype(np.float32)
        action, latency = inference.predict(dummy_state)
        print(f"Action: {action}, Latency: {latency:.2f}ms")


if __name__ == '__main__':
    main()