import argparse
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import psutil

from edge_deploy.inference import EdgeInference
from configs.constants import FEATURES_PER_INTERSECTION


def run_comprehensive_benchmark(args):
    print("=" * 60)
    print("Xiongan Traffic Control - Edge Deployment Benchmark")
    print("=" * 60)

    inference = EdgeInference(args.model)

    print("\n1. Model Size Analysis")
    print("-" * 40)
    model_size_bytes = os.path.getsize(inference.model_path)
    print(f"Model file size: {model_size_bytes:,} bytes")
    print(f"Model file size: {model_size_bytes / 1024:.2f} KB")
    print(f"Model file size: {model_size_bytes / 1024 / 1024:.2f} MB")

    print("\n2. Inference Latency Benchmark")
    print("-" * 40)
    results = inference.benchmark(args.n)

    print("\n3. System Resource Usage")
    print("-" * 40)
    
    process = psutil.Process()
    mem_info = process.memory_info()
    
    print(f"Memory usage: {mem_info.rss / 1024 / 1024:.2f} MB")
    print(f"Virtual memory: {mem_info.vms / 1024 / 1024:.2f} MB")

    print("\n4. Throughput Benchmark")
    print("-" * 40)
    
    start_time = time.perf_counter()
    for _ in range(args.n):
        dummy = np.random.randn(FEATURES_PER_INTERSECTION).astype(np.float32)
        inference.predict(dummy)
    end_time = time.perf_counter()
    
    total_time = end_time - start_time
    throughput = args.n / total_time
    
    print(f"Total time for {args.n} inferences: {total_time:.2f} seconds")
    print(f"Throughput: {throughput:.2f} inferences/second")

    print("\n5. Cold Start Time")
    print("-" * 40)
    
    cold_start_times = []
    for _ in range(5):
        start = time.perf_counter()
        _ = EdgeInference(args.model)
        cold_start_time = (time.perf_counter() - start) * 1000
        cold_start_times.append(cold_start_time)
        print(f"Cold start {_+1}: {cold_start_time:.2f} ms")
    
    print(f"Average cold start: {np.mean(cold_start_times):.2f} ms")

    print("\n" + "=" * 60)
    print("Benchmark Summary")
    print("=" * 60)
    print(f"✅ Model size < 1MB: {results['model_size_kb'] < 1024}")
    print(f"✅ Mean latency < 5ms: {results['mean_latency_ms'] < 5}")
    print(f"✅ P99 latency < 10ms: {results['p99_latency_ms'] < 10}")
    print(f"✅ Throughput > 100 inf/sec: {throughput > 100}")
    print("=" * 60)


def profile_memory(args):
    print("Memory Profiling...")
    
    process = psutil.Process()
    initial_mem = process.memory_info().rss
    
    inference = EdgeInference(args.model)
    
    after_load_mem = process.memory_info().rss
    load_overhead = (after_load_mem - initial_mem) / 1024 / 1024
    
    print(f"Memory overhead after loading model: {load_overhead:.2f} MB")

    for _ in range(100):
        dummy = np.random.randn(FEATURES_PER_INTERSECTION).astype(np.float32)
        inference.predict(dummy)
    
    after_inference_mem = process.memory_info().rss
    inference_overhead = (after_inference_mem - after_load_mem) / 1024 / 1024
    
    print(f"Memory overhead after 100 inferences: {inference_overhead:.2f} MB")


def main():
    parser = argparse.ArgumentParser(description='Comprehensive benchmark for edge deployment')
    parser.add_argument('--model', type=str, default=None, help='Path to model file')
    parser.add_argument('--n', type=int, default=1000, help='Number of benchmark iterations')
    parser.add_argument('--profile_memory', action='store_true', help='Run memory profiling')
    
    args = parser.parse_args()

    if args.profile_memory:
        profile_memory(args)
    else:
        run_comprehensive_benchmark(args)


if __name__ == '__main__':
    main()
