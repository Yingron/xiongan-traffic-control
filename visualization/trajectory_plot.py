import argparse
import os
import sys

import matplotlib.pyplot as plt
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from training.config import VISUALIZATION_DIR


def plot_trajectories(args):
    print("Generating trajectory plots...")
    
    np.random.seed(42)
    
    n_vehicles = 20
    n_steps = 200
    
    trajectories = []
    for _ in range(n_vehicles):
        x = np.cumsum(np.random.randn(n_steps) * 0.5)
        y = np.cumsum(np.random.randn(n_steps) * 0.5)
        speeds = np.random.rand(n_steps) * 15
        
        trajectories.append((x, y, speeds))
    
    plt.figure(figsize=(10, 8))
    
    for x, y, speeds in trajectories:
        plt.scatter(x, y, c=speeds, cmap='coolwarm', s=10, alpha=0.7)
    
    plt.colorbar(label='Speed (m/s)')
    plt.title('Vehicle Trajectories with Speed Color Mapping', fontsize=14, fontweight='bold')
    plt.xlabel('X Position (m)', fontsize=12)
    plt.ylabel('Y Position (m)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    
    output_path = os.path.join(VISUALIZATION_DIR, 'trajectories.png')
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"Saved: {output_path}")


def plot_speed_profile(args):
    print("Generating speed profile plot...")
    
    time_steps = np.arange(0, 3600, 60)
    speed_limit = np.ones_like(time_steps) * 13.89
    
    np.random.seed(42)
    avg_speed = 13.89 + np.sin(time_steps / 600 * 2 * np.pi) * 3 + np.random.randn(len(time_steps)) * 1
    
    morning_peak = np.logical_and(time_steps >= 25200, time_steps <= 32400)
    evening_peak = np.logical_and(time_steps >= 61200, time_steps <= 68400)
    
    avg_speed[morning_peak] -= 4
    avg_speed[evening_peak] -= 3.5
    
    avg_speed = np.clip(avg_speed, 0, 13.89)
    
    plt.figure(figsize=(12, 6))
    plt.plot(time_steps / 3600, speed_limit, 'r--', label='Speed Limit', linewidth=2)
    plt.plot(time_steps / 3600, avg_speed, 'b-', label='Average Speed', linewidth=2)
    
    plt.fill_between(time_steps / 3600, avg_speed, 0, alpha=0.3, color='blue')
    
    plt.title('Average Speed Profile - 24 Hour Period', fontsize=14, fontweight='bold')
    plt.xlabel('Time (hours)', fontsize=12)
    plt.ylabel('Speed (m/s)', fontsize=12)
    plt.legend(fontsize=10)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.xlim(0, 24)
    plt.tight_layout()
    
    output_path = os.path.join(VISUALIZATION_DIR, 'speed_profile.png')
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"Saved: {output_path}")


def plot_queue_evolution(args):
    print("Generating queue evolution plot...")
    
    time_steps = np.arange(0, 3600, 10)
    
    np.random.seed(42)
    queue_north = np.cumsum(np.random.randn(len(time_steps)) * 0.5 + 0.2)
    queue_south = np.cumsum(np.random.randn(len(time_steps)) * 0.5 + 0.15)
    queue_east = np.cumsum(np.random.randn(len(time_steps)) * 0.5 + 0.25)
    queue_west = np.cumsum(np.random.randn(len(time_steps)) * 0.5 + 0.1)
    
    queue_north = np.maximum(0, queue_north)
    queue_south = np.maximum(0, queue_south)
    queue_east = np.maximum(0, queue_east)
    queue_west = np.maximum(0, queue_west)
    
    plt.figure(figsize=(12, 6))
    plt.plot(time_steps, queue_north, 'r-', label='North', linewidth=2)
    plt.plot(time_steps, queue_south, 'g-', label='South', linewidth=2)
    plt.plot(time_steps, queue_east, 'b-', label='East', linewidth=2)
    plt.plot(time_steps, queue_west, 'purple', label='West', linewidth=2)
    
    plt.title('Queue Length Evolution at Intersection J1', fontsize=14, fontweight='bold')
    plt.xlabel('Time (seconds)', fontsize=12)
    plt.ylabel('Queue Length (vehicles)', fontsize=12)
    plt.legend(fontsize=10)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    
    output_path = os.path.join(VISUALIZATION_DIR, 'queue_evolution.png')
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Generate trajectory and profile plots')
    parser.add_argument('--trajectories', action='store_true', help='Generate trajectory plot')
    parser.add_argument('--speed', action='store_true', help='Generate speed profile')
    parser.add_argument('--queue', action='store_true', help='Generate queue evolution')
    parser.add_argument('--all', action='store_true', help='Generate all plots')
    
    args = parser.parse_args()
    
    if args.all or args.trajectories:
        plot_trajectories(args)
    
    if args.all or args.speed:
        plot_speed_profile(args)
    
    if args.all or args.queue:
        plot_queue_evolution(args)
    
    print("\nPlots generated successfully!")


if __name__ == '__main__':
    main()