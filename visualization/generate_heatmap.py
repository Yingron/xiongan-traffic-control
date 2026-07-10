import argparse
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from training.config import VISUALIZATION_DIR


def generate_queue_heatmap(args):
    print("Generating queue heatmap...")
    
    hours = 24
    intersections = ['J1', 'J2', 'J3', 'J4', 'J5', 'J6', 'J7']
    
    np.random.seed(42)
    queue_data = np.random.rand(hours, len(intersections)) * 30
    
    morning_peak = np.logical_and(np.arange(hours) >= 7, np.arange(hours) <= 9)
    evening_peak = np.logical_and(np.arange(hours) >= 17, np.arange(hours) <= 19)
    
    queue_data[morning_peak, :] *= 1.5
    queue_data[evening_peak, :] *= 1.4
    
    plt.figure(figsize=(12, 8))
    ax = sns.heatmap(queue_data, 
                     annot=True, 
                     fmt='.1f', 
                     cmap='YlOrRd',
                     xticklabels=intersections,
                     yticklabels=[f'{h:02d}:00' for h in range(hours)],
                     cbar_kws={'label': 'Queue Length (vehicles)'})
    
    plt.title('Queue Length Heatmap - 24 Hour Period', fontsize=14, fontweight='bold')
    plt.xlabel('Intersections', fontsize=12)
    plt.ylabel('Time of Day', fontsize=12)
    plt.tight_layout()
    
    output_path = os.path.join(VISUALIZATION_DIR, 'queue_heatmap.png')
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"Saved: {output_path}")


def generate_occupancy_heatmap(args):
    print("Generating occupancy heatmap...")
    
    hours = 24
    approaches = ['North', 'South', 'East', 'West']
    
    np.random.seed(42)
    occupancy_data = np.random.rand(hours, len(approaches)) * 100
    
    morning_peak = np.logical_and(np.arange(hours) >= 7, np.arange(hours) <= 9)
    evening_peak = np.logical_and(np.arange(hours) >= 17, np.arange(hours) <= 19)
    
    occupancy_data[morning_peak, :] = np.minimum(100, occupancy_data[morning_peak, :] * 1.5)
    occupancy_data[evening_peak, :] = np.minimum(100, occupancy_data[evening_peak, :] * 1.4)
    
    plt.figure(figsize=(10, 6))
    ax = sns.heatmap(occupancy_data, 
                     annot=True, 
                     fmt='.1f', 
                     cmap='Blues',
                     xticklabels=approaches,
                     yticklabels=[f'{h:02d}:00' for h in range(hours)],
                     cbar_kws={'label': 'Occupancy (%)'})
    
    plt.title('Lane Occupancy Heatmap - 24 Hour Period', fontsize=14, fontweight='bold')
    plt.xlabel('Approaches', fontsize=12)
    plt.ylabel('Time of Day', fontsize=12)
    plt.tight_layout()
    
    output_path = os.path.join(VISUALIZATION_DIR, 'occupancy_heatmap.png')
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"Saved: {output_path}")


def generate_phase_transition_matrix(args):
    print("Generating phase transition matrix...")
    
    phases = ['NS_Straight', 'NS_Left', 'EW_Straight', 'EW_Left']
    transition_matrix = np.array([
        [0.0, 0.8, 0.1, 0.1],
        [0.9, 0.0, 0.05, 0.05],
        [0.1, 0.1, 0.0, 0.8],
        [0.05, 0.05, 0.9, 0.0]
    ])
    
    plt.figure(figsize=(8, 6))
    ax = sns.heatmap(transition_matrix, 
                     annot=True, 
                     fmt='.2f', 
                     cmap='Greens',
                     xticklabels=phases,
                     yticklabels=phases,
                     cbar=False)
    
    plt.title('Phase Transition Probability Matrix', fontsize=14, fontweight='bold')
    plt.xlabel('Next Phase', fontsize=12)
    plt.ylabel('Current Phase', fontsize=12)
    plt.tight_layout()
    
    output_path = os.path.join(VISUALIZATION_DIR, 'phase_transition_matrix.png')
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Generate heatmap visualizations')
    parser.add_argument('--queue', action='store_true', help='Generate queue heatmap')
    parser.add_argument('--occupancy', action='store_true', help='Generate occupancy heatmap')
    parser.add_argument('--transition', action='store_true', help='Generate phase transition matrix')
    parser.add_argument('--all', action='store_true', help='Generate all heatmaps')
    
    args = parser.parse_args()
    
    if args.all or args.queue:
        generate_queue_heatmap(args)
    
    if args.all or args.occupancy:
        generate_occupancy_heatmap(args)
    
    if args.all or args.transition:
        generate_phase_transition_matrix(args)
    
    print("\nHeatmaps generated successfully!")


if __name__ == '__main__':
    main()