#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate chart assets for Chapter 3 PPT slides."""
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

OUTPUT_DIR = r'C:\Users\荣光\Desktop\挑战杯\xiongan-traffic-control\docs\ppt_charts'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Color palette matching PPT
COLORS = {
    'primary': '#17365D',
    'secondary': '#334155',
    'accent_blue': '#2563EB',
    'accent_teal': '#0D9488',
    'accent_green': '#059669',
    'accent_red': '#DC2626',
    'accent_orange': '#D97706',
    'light_bg': '#F1F5F9',
    'white': '#FFFFFF',
}

def save_chart(fig, name, w_in, h_in):
    """Save chart with dimension in filename."""
    w_px = int(w_in * 150)
    h_px = int(h_in * 150)
    path = os.path.join(OUTPUT_DIR, f'{name}_{w_px}x{h_px}.png')
    fig.savefig(path, dpi=150, bbox_inches='tight', transparent=False,
                facecolor=COLORS['light_bg'], edgecolor='none')
    plt.close(fig)
    print(f'  Saved: {name} ({w_px}x{h_px})')
    return path

# ============================================================
# Chart 1: Three-scenario reward comparison (bar chart)
# ============================================================
def chart_scenario_comparison():
    fig, ax = plt.subplots(figsize=(7, 4), facecolor=COLORS['light_bg'])
    
    scenarios = ['早高峰', '平峰', '晚高峰']
    dqn_rewards = [19948, 16299, 18924]
    ft_rewards = [17537, 15468, 16397]
    
    x = np.arange(len(scenarios))
    width = 0.35
    
    bars1 = ax.bar(x - width/2, ft_rewards, width, label='Fixed-Time',
                   color='#94A3B8', edgecolor='white', linewidth=1)
    bars2 = ax.bar(x + width/2, dqn_rewards, width, label='DQN (共享掩码)',
                   color=COLORS['accent_blue'], edgecolor='white', linewidth=1)
    
    # Add percentage labels
    for i, (dqn, ft) in enumerate(zip(dqn_rewards, ft_rewards)):
        pct = (dqn - ft) / ft * 100
        color = COLORS['accent_green'] if pct > 0 else COLORS['accent_red']
        sign = '+' if pct > 0 else ''
        ax.text(i + width/2, dqn + 200, f'{sign}{pct:.1f}%',
                ha='center', va='bottom', fontsize=11, fontweight='bold', color=color)
    
    ax.set_ylabel('累计奖励', fontsize=12, color=COLORS['secondary'])
    ax.set_title('三场景DQN vs Fixed-Time 奖励对比（8路口代表口径）',
                 fontsize=13, fontweight='bold', color=COLORS['primary'], pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, fontsize=11, color=COLORS['secondary'])
    ax.legend(fontsize=10, frameon=True, facecolor='white', edgecolor='#CBD5E1')
    ax.set_ylim(0, max(dqn_rewards) * 1.18)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#CBD5E1')
    ax.spines['bottom'].set_color('#CBD5E1')
    ax.tick_params(colors=COLORS['secondary'])
    ax.grid(axis='y', alpha=0.3, color='#CBD5E1')
    ax.set_facecolor(COLORS['light_bg'])
    
    plt.tight_layout()
    return save_chart(fig, 'scenario_comparison', 7, 4)

# ============================================================
# Chart 2: Model lightweighting comparison
# ============================================================
def chart_lightweight_comparison():
    fig, ax = plt.subplots(figsize=(6, 3.5), facecolor=COLORS['light_bg'])
    
    methods = ['SB3教师\n(zip)', 'FP32 ONNX\n(正式部署)', 'INT8量化\n(失败)', '结构化剪枝\n(候选)']
    sizes = [121, 25.14, 8, 20]
    colors = ['#94A3B8', COLORS['accent_green'], COLORS['accent_red'], COLORS['accent_orange']]
    
    bars = ax.barh(methods, sizes, color=colors, edgecolor='white', linewidth=1.5, height=0.6)
    
    for bar, size in zip(bars, sizes):
        ax.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2,
                f'{size:.1f} KB', va='center', ha='left',
                fontsize=11, fontweight='bold', color=COLORS['secondary'])
    
    ax.set_xlabel('模型体积 (KB)', fontsize=11, color=COLORS['secondary'])
    ax.set_title('模型轻量化方案体积对比', fontsize=13, fontweight='bold',
                 color=COLORS['primary'], pad=12)
    ax.set_xlim(0, 145)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#CBD5E1')
    ax.spines['bottom'].set_color('#CBD5E1')
    ax.tick_params(colors=COLORS['secondary'])
    ax.grid(axis='x', alpha=0.3, color='#CBD5E1')
    ax.set_facecolor(COLORS['light_bg'])
    
    plt.tight_layout()
    return save_chart(fig, 'lightweight_comparison', 6, 3.5)

# ============================================================
# Chart 3: Road network topology (simplified)
# ============================================================
def chart_road_network_simple():
    fig, ax = plt.subplots(figsize=(5, 4), facecolor=COLORS['light_bg'])
    ax.set_xlim(-0.5, 6.5)
    ax.set_ylim(-0.5, 5.5)
    ax.set_aspect('equal')
    
    tc = {'A': '#2563EB', 'B': '#059669', 'C': '#D97706', 'D': '#DC2626', 'E': '#7C3AED'}
    tm = {
        'A': [1,3,4,6,8,9,11,12,15,16,18,19,20,21,22,23,24,25,28,29],
        'B': [13,26,27,30],
        'C': [5,7,10],
        'D': [14,17],
        'E': [2]
    }
    pos = {}
    for i in range(30):
        pos[i+1] = (i % 6, 4 - i // 6)
    
    # Draw roads
    for jid, (cx, cy) in pos.items():
        if jid % 6 != 0 and jid + 1 <= 30:
            ax.plot([cx, pos[jid+1][0]], [cy, pos[jid+1][1]],
                    '#CBD5E1', lw=4, zorder=1)
        if jid + 6 <= 30:
            ax.plot([cx, pos[jid+6][0]], [cy, pos[jid+6][1]],
                    '#CBD5E1', lw=4, zorder=1)
    
    # Draw intersections
    for jid, (cx, cy) in pos.items():
        t = [k for k, v in tm.items() if jid in v][0]
        c = tc.get(t, '#888')
        ax.add_patch(plt.Circle((cx, cy), 0.3, color=c, zorder=3,
                                ec='white', lw=2))
        ax.text(cx, cy, f'{jid:02d}', ha='center', va='center',
                fontsize=7, fontweight='bold', color='white', zorder=4)
    
    ax.set_title('30路口路网拓扑（5种相位模板）', fontsize=12,
                 fontweight='bold', color=COLORS['primary'], pad=10)
    ax.axis('off')
    ax.set_facecolor(COLORS['light_bg'])
    
    # Legend
    legend_handles = [plt.Rectangle((0,0),1,1, color=tc[t]) for t in ['A','B','C','D','E']]
    legend_labels = [f'模板{t}（{len(tm[t])}个）' for t in ['A','B','C','D','E']]
    ax.legend(legend_handles, legend_labels, loc='lower center',
              ncol=5, fontsize=9, frameon=False,
              bbox_to_anchor=(0.5, -0.08))
    
    plt.tight_layout()
    return save_chart(fig, 'road_network_simple', 5, 4)

# ============================================================
# Chart 4: Inference latency comparison
# ============================================================
def chart_inference_latency():
    fig, ax = plt.subplots(figsize=(5.5, 3.5), facecolor=COLORS['light_bg'])
    
    categories = ['单路口\nmean', '单路口\nP95', '30路口批量\nmean', '30路口批量\nP95']
    values = [0.022, 0.028, 0.029, 0.048]
    targets = [5, 5, 500, 500]  # ms
    
    colors = [COLORS['accent_teal'], COLORS['accent_blue'],
              COLORS['accent_teal'], COLORS['accent_blue']]
    
    bars = ax.bar(categories, values, color=colors, edgecolor='white',
                  linewidth=1.5, width=0.55)
    
    for bar, val, target in zip(bars, values, targets):
        ratio = val / target * 100
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.002,
                f'{val} ms\n(目标的{ratio:.1f}%)',
                ha='center', va='bottom', fontsize=9,
                fontweight='bold', color=COLORS['secondary'])
    
    ax.set_ylabel('推理延迟 (ms)', fontsize=11, color=COLORS['secondary'])
    ax.set_title('ONNX边缘推理性能（远低于赛题目标）',
                 fontsize=12, fontweight='bold', color=COLORS['primary'], pad=10)
    ax.set_ylim(0, 0.08)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#CBD5E1')
    ax.spines['bottom'].set_color('#CBD5E1')
    ax.tick_params(colors=COLORS['secondary'])
    ax.grid(axis='y', alpha=0.3, color='#CBD5E1')
    ax.set_facecolor(COLORS['light_bg'])
    
    plt.tight_layout()
    return save_chart(fig, 'inference_latency', 5.5, 3.5)

# ============================================================
# Chart 5: 30-intersection win/loss by template
# ============================================================
def chart_template_wins():
    fig, ax = plt.subplots(figsize=(6, 3.5), facecolor=COLORS['light_bg'])
    
    templates = ['模板A\n(20个)', '模板B\n(4个)', '模板C\n(3个)', '模板D\n(2个)', '模板E\n(1个)']
    morning_wins = [14, 3, 2, 0, 1]
    evening_wins = [13, 2, 2, 2, 1]
    total = [20, 4, 3, 2, 1]
    
    x = np.arange(len(templates))
    width = 0.35
    
    bars1 = ax.bar(x - width/2, morning_wins, width, label='早高峰',
                   color=COLORS['accent_blue'], edgecolor='white', linewidth=1)
    bars2 = ax.bar(x + width/2, evening_wins, width, label='晚高峰',
                   color=COLORS['accent_teal'], edgecolor='white', linewidth=1)
    
    # Add "X/Y" labels
    for i, (mw, ew, tot) in enumerate(zip(morning_wins, evening_wins, total)):
        ax.text(i - width/2, mw + 0.3, f'{mw}/{tot}', ha='center', va='bottom',
                fontsize=9, fontweight='bold', color=COLORS['secondary'])
        ax.text(i + width/2, ew + 0.3, f'{ew}/{tot}', ha='center', va='bottom',
                fontsize=9, fontweight='bold', color=COLORS['secondary'])
    
    ax.set_ylabel('DQN胜出路口数', fontsize=11, color=COLORS['secondary'])
    ax.set_title('按相位模板的DQN胜路口数（30路口全量）',
                 fontsize=12, fontweight='bold', color=COLORS['primary'], pad=10)
    ax.set_xticks(x)
    ax.set_xticklabels(templates, fontsize=9, color=COLORS['secondary'])
    ax.legend(fontsize=9, frameon=True, facecolor='white', edgecolor='#CBD5E1')
    ax.set_ylim(0, 24)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#CBD5E1')
    ax.spines['bottom'].set_color('#CBD5E1')
    ax.tick_params(colors=COLORS['secondary'])
    ax.grid(axis='y', alpha=0.3, color='#CBD5E1')
    ax.set_facecolor(COLORS['light_bg'])
    
    plt.tight_layout()
    return save_chart(fig, 'template_wins', 6, 3.5)

# ============================================================
# Generate all charts
# ============================================================
print('Generating PPT chart assets...')
chart_scenario_comparison()
chart_lightweight_comparison()
chart_road_network_simple()
chart_inference_latency()
chart_template_wins()
print(f'\nAll charts saved to: {OUTPUT_DIR}')
