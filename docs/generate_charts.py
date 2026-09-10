#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.patches import Patch

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 150

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'charts')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def chart_road_network():
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_xlim(-0.5, 6.5); ax.set_ylim(-0.5, 5.5); ax.set_aspect('equal')
    ax.set_title('30路口路网拓扑示意图', fontsize=14, fontweight='bold', pad=15)
    tc = {'A':'#3B82F6','B':'#10B981','C':'#F59E0B','D':'#EF4444','E':'#8B5CF6'}
    tm = {'A':[1,3,4,6,8,9,11,12,15,16,18,19,20,21,22,23,24,25,28,29],'B':[13,26,27,30],'C':[5,7,10],'D':[14,17],'E':[2]}
    pos = {}
    for i in range(30):
        pos[i+1] = (i%6, 4-i//6)
    for jid,(cx,cy) in pos.items():
        if jid%6!=0 and jid+1<=30: ax.plot([cx,pos[jid+1][0]],[cy,pos[jid+1][1]],'k-',lw=2.5,zorder=1)
        if jid+6<=30: ax.plot([cx,pos[jid+6][0]],[cy,pos[jid+6][1]],'k-',lw=2.5,zorder=1)
    for jid,(cx,cy) in pos.items():
        t=[k for k,v in tm.items() if jid in v][0]
        c=tc.get(t,'#888')
        ax.add_patch(plt.Circle((cx,cy),0.28,color=c,zorder=3,ec='white',lw=1.5))
        ax.text(cx,cy,f'J{jid:02d}',ha='center',va='center',fontsize=6.5,fontweight='bold',color='white',zorder=4)
    for t,c in tc.items():
        ax.plot([],[],'o',color=c,markersize=10,label=f'模板{t} ({len(tm[t])}路口)')
    ax.legend(loc='upper right',fontsize=9,framealpha=0.9,title='相位模板分布',title_fontsize=10)
    ax.set_xlabel('东西方向',fontsize=10); ax.set_ylabel('南北方向',fontsize=10); ax.grid(False)
    plt.tight_layout(); plt.savefig(os.path.join(OUTPUT_DIR,'fig3_1_road_network.png'),bbox_inches='tight'); plt.close()
    print('Saved: fig3_1_road_network.png')

def chart_dqn_architecture():
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.set_xlim(0,14); ax.set_ylim(0,7); ax.set_aspect('equal')
    ax.set_title('参数共享掩码DQN网络结构与数据流', fontsize=14, fontweight='bold', pad=15)
    ax.axis('off')
    def db(x,y,w,h,t,c,fs=9):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.15',facecolor=c,edgecolor='none'))
        ax.text(x+w/2,y+h/2,t,ha='center',va='center',fontsize=fs,fontweight='bold',color='white')
    def da(x1,y1,x2,y2):
        ax.annotate('',xy=(x2,y2),xytext=(x1,y1),arrowprops=dict(arrowstyle='->',color='#555',lw=1.8))
    db(0.5,2.5,2,1,'局部状态\n22维','#3B82F6'); db(0.5,1,2,1,'动作掩码\n4维','#F59E0B')
    db(3.2,1.5,1.5,1.5,'拼接\n26维','#6B7280')
    db(5.5,2.5,2.5,1,'全连接层1\n64 neurons\nReLU','#2E86AB'); db(5.5,1,2.5,1,'全连接层2\n64 neurons\nReLU','#2E86AB')
    db(9,1.75,2,1.5,'Q值\n4维','#8B5CF6'); db(11.8,1.75,2,1.5,'掩码后\nQ值','#06A77D')
    da(2.5,3,3.2,2.75); da(2.5,1.5,3.2,2.25); da(4.7,2.25,5.5,3); da(4.7,2.25,5.5,1.5)
    da(8,3,9,2.5); da(8,1.5,9,2.5); da(11,2.5,11.8,2.5)
    ax.text(10.4,0.5,'Q * mask - (1-mask) * 3e38',ha='center',fontsize=8,style='italic',color='#D62828',bbox=dict(boxstyle='round,pad=0.3',facecolor='#FFF3CD',edgecolor='#D62828'))
    ax.text(6.75,4.2,'总参数量: ~11,784',ha='center',fontsize=10,fontweight='bold',color='#2E86AB')
    ax.text(7,5.5,'30个路口共享同一套网络参数',ha='center',fontsize=11,fontweight='bold',color='#A23B72',bbox=dict(boxstyle='round,pad=0.4',facecolor='#FCE4EC',edgecolor='#A23B72'))
    plt.tight_layout(); plt.savefig(os.path.join(OUTPUT_DIR,'fig3_2_dqn_architecture.png'),bbox_inches='tight'); plt.close()
    print('Saved: fig3_2_dqn_architecture.png')

def chart_training_loop():
    fig, ax = plt.subplots(figsize=(10, 12))
    ax.set_xlim(0,10); ax.set_ylim(0,14)
    ax.set_title('多路口DQN训练主循环流程', fontsize=14, fontweight='bold', pad=15)
    ax.axis('off')
    def ds(x,y,w,h,t,c,fs=9):
        ax.add_patch(FancyBboxPatch((x-w/2,y-h/2),w,h,boxstyle='round,pad=0.2',facecolor=c,edgecolor='none'))
        ax.text(x,y,t,ha='center',va='center',fontsize=fs,fontweight='bold',color='white')
    def da(x1,y1,x2,y2):
        ax.annotate('',xy=(x2,y2),xytext=(x1,y1),arrowprops=dict(arrowstyle='->',color='#555',lw=2))
    steps=[(5,13,4,0.8,'1. 启动SUMO\n获取30信号灯ID','#3B82F6'),(5,11.5,4,0.8,'2. 重置环境\n切片660维状态','#3B82F6'),
    (2.5,10,3.5,0.8,'3a. 计算动作掩码\n(需求门控)','#F59E0B'),(7.5,10,3.5,0.8,'3b. epsilon-贪婪选择动作\n(仅合法动作)','#F59E0B'),
    (5,8.5,4,0.8,'4. 批量设置30路口相位\n推进仿真(5s步长)','#2E86AB'),(5,7,4,0.8,'5. 计算各路口奖励\n(V5奖励函数)','#A23B72'),
    (5,5.5,4,0.8,'6. 存入共享经验回放池\n(1M容量)','#06A77D'),(2.5,4,3.5,0.8,'7a. 每4步采样\n批量更新网络','#8B5CF6'),
    (7.5,4,3.5,0.8,'7b. 目标网络\n每10000步同步','#8B5CF6'),(5,2.5,4,0.8,'8. epsilon线性衰减\n(1.0 -> 0.05)','#6B7280'),
    (5,1,4,0.8,'9. 重复至1M步\n(Double-DQN)','#D62828')]
    for x,y,w,h,t,c in steps: ds(x,y,w,h,t,c)
    da(5,12.6,5,11.9); da(5,11.1,2.5,10.4); da(5,11.1,7.5,10.4)
    da(2.5,9.6,4.5,8.9); da(7.5,9.6,5.5,8.9); da(5,8.1,5,7.4)
    da(5,6.6,5,5.9); da(5,5.1,2.5,4.4); da(5,5.1,7.5,4.4)
    da(2.5,3.6,4.5,2.9); da(7.5,3.6,5.5,2.9); da(5,2.1,5,1.4); da(5,0.6,5,0.2)
    ax.annotate('',xy=(0.5,11.5),xytext=(0.5,1),arrowprops=dict(arrowstyle='->',color='#D62828',lw=1.5,linestyle='dashed'))
    ax.text(0.3,6.5,'循环',rotation=90,ha='center',va='center',fontsize=9,color='#D62828',fontweight='bold')
    plt.tight_layout(); plt.savefig(os.path.join(OUTPUT_DIR,'fig3_3_training_loop.png'),bbox_inches='tight'); plt.close()
    print('Saved: fig3_3_training_loop.png')

def chart_lightweighting_pipeline():
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.set_xlim(0,14); ax.set_ylim(0,5)
    ax.set_title('DQN模型轻量化导出与验证链路', fontsize=14, fontweight='bold', pad=15)
    ax.axis('off')
    def db(x,y,w,h,t,c,fs=9):
        ax.add_patch(FancyBboxPatch((x-w/2,y-h/2),w,h,boxstyle='round,pad=0.15',facecolor=c,edgecolor='none'))
        ax.text(x,y,t,ha='center',va='center',fontsize=fs,fontweight='bold',color='white')
    def da(x1,y1,x2,y2,l=''):
        ax.annotate('',xy=(x2,y2),xytext=(x1,y1),arrowprops=dict(arrowstyle='->',color='#555',lw=2))
        if l: ax.text((x1+x2)/2,(y1+y2)/2+0.3,l,ha='center',fontsize=8,color='#555',style='italic')
    db(2,3,2.5,1.2,'SB3教师模型\n(zip, ~121KB)\n[64,64] MLP','#3B82F6')
    da(3.3,3,4.7,3,'权重复制')
    db(6,3,2.5,1.2,'MaskedEdgeQNetwork\n(TorchScript)\n可移植定义','#8B5CF6')
    da(7.3,3,8.7,3,'ONNX导出\nopset 17')
    db(10,3,2.5,1.2,'ONNX FP32\n25,742 B (~25KB)\n动态batch','#06A77D')
    db(10,1,2.5,1.2,'保真验证\n2880条真实状态\n一致率100%','#F18F01')
    da(10,2.4,10,1.6,'验证')
    db(2,1,2.5,1.2,'INT8量化(消融)\n真实一致率\n84-93%','#EF4444')
    db(6,1,2.5,1.2,'结构化剪枝(消融)\n离线一致率\n~96.7%','#EF4444')
    da(2,1.6,2,2.4); da(6,1.6,6,2.4)
    ax.text(7,4.5,'体积减少79% | 单路口推理0.022ms | 30路口批量0.029ms',ha='center',fontsize=10,fontweight='bold',color='#06A77D',bbox=dict(boxstyle='round,pad=0.3',facecolor='#D1FAE5',edgecolor='#06A77D'))
    plt.tight_layout(); plt.savefig(os.path.join(OUTPUT_DIR,'fig3_4_lightweighting.png'),bbox_inches='tight'); plt.close()
    print('Saved: fig3_4_lightweighting.png')

def chart_three_scenarios():
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle('三场景DQN与Fixed-Time对比（8路口代表口径）', fontsize=14, fontweight='bold')
    scenarios=['早高峰','平峰','晚高峰']
    rd=[19948,16299,18924]; rf=[17537,15468,16397]
    wd=[2679,2243,2537]; wf=[2654,1397,2592]
    x=np.arange(3); w=0.35
    ax1=axes[0]
    b1=ax1.bar(x-w/2,rd,w,label='DQN',color='#3B82F6'); b2=ax1.bar(x+w/2,rf,w,label='Fixed-Time',color='#F59E0B')
    ax1.set_xticks(x); ax1.set_xticklabels(scenarios); ax1.set_ylabel('Reward'); ax1.set_title('总奖励对比'); ax1.legend()
    for b,v in zip(b1,rd): ax1.text(b.get_x()+b.get_width()/2,b.get_height()+200,f'{v}',ha='center',fontsize=8)
    for b,v in zip(b2,rf): ax1.text(b.get_x()+b.get_width()/2,b.get_height()+200,f'{v}',ha='center',fontsize=8)
    ax2=axes[1]
    imp=[13.7,5.4,15.4]; cs=['#06A77D','#F59E0B','#06A77D']
    bars=ax2.bar(x,imp,width=0.5,color=cs); ax2.set_xticks(x); ax2.set_xticklabels(scenarios)
    ax2.set_ylabel('Reward提升 (%)'); ax2.set_title('DQN相对Fixed-Time的Reward提升'); ax2.axhline(y=0,color='gray',lw=0.5)
    for b,v in zip(bars,imp): ax2.text(b.get_x()+b.get_width()/2,b.get_height()+0.3,f'+{v}%',ha='center',fontsize=10,fontweight='bold')
    ax3=axes[2]
    b3=ax3.bar(x-w/2,wd,w,label='DQN',color='#3B82F6'); b4=ax3.bar(x+w/2,wf,w,label='Fixed-Time',color='#F59E0B')
    ax3.set_xticks(x); ax3.set_xticklabels(scenarios); ax3.set_ylabel('等待时间 (s)'); ax3.set_title('总等待时间对比'); ax3.legend()
    for b,v in zip(b3,wd): ax3.text(b.get_x()+b.get_width()/2,b.get_height()+30,f'{v}',ha='center',fontsize=8)
    for b,v in zip(b4,wf): ax3.text(b.get_x()+b.get_width()/2,b.get_height()+30,f'{v}',ha='center',fontsize=8)
    plt.tight_layout(); plt.savefig(os.path.join(OUTPUT_DIR,'fig3_5_three_scenarios.png'),bbox_inches='tight'); plt.close()
    print('Saved: fig3_5_three_scenarios.png')

def chart_reward_weights():
    fig, ax = plt.subplots(figsize=(10, 6))
    cats=['溢出风险\np_overflow','真实通过数\nn_crossed','队列压力\nq_pressure','最大排队\nq_max','平均等待\navg_wait','队列减少\nr_queue','等待减少\nr_wait','均衡惩罚\np_balance','停滞惩罚\np_stag','相位切换\nc_switch']
    weights=[2.0,2.0,0.8,0.6,0.4,0.5,0.3,0.1,0.08,0.01]
    colors=['#EF4444','#06A77D','#3B82F6','#3B82F6','#3B82F6','#06A77D','#06A77D','#F59E0B','#F59E0B','#6B7280']
    y=np.arange(len(cats))
    bars=ax.barh(y,weights,color=colors,edgecolor='white',height=0.6)
    ax.set_yticks(y); ax.set_yticklabels(cats,fontsize=9); ax.invert_yaxis()
    ax.set_xlabel('权重',fontsize=11); ax.set_title('V5奖励函数各项权重分布',fontsize=14,fontweight='bold',pad=15)
    for b,v in zip(bars,weights): ax.text(b.get_width()+0.03,b.get_y()+b.get_height()/2,f'{v}',ha='left',va='center',fontsize=9,fontweight='bold')
    le=[Patch(facecolor='#EF4444',label='安全惩罚项'),Patch(facecolor='#3B82F6',label='效率惩罚项'),Patch(facecolor='#06A77D',label='正向奖励项'),Patch(facecolor='#F59E0B',label='稳定性惩罚项'),Patch(facecolor='#6B7280',label='切换惩罚项')]
    ax.legend(handles=le,loc='lower right',fontsize=8); ax.set_xlim(0,2.5)
    plt.tight_layout(); plt.savefig(os.path.join(OUTPUT_DIR,'fig3_6_reward_weights.png'),bbox_inches='tight'); plt.close()
    print('Saved: fig3_6_reward_weights.png')

def chart_template_distribution():
    fig, ax = plt.subplots(figsize=(8, 6))
    labels=['模板A\n(20路口)','模板B\n(4路口)','模板C\n(3路口)','模板D\n(2路口)','模板E\n(1路口)']
    sizes=[20,4,3,2,1]; colors=['#3B82F6','#10B981','#F59E0B','#EF4444','#8B5CF6']; explode=(0,0,0.1,0.1,0.15)
    _,_,at=ax.pie(sizes,explode=explode,labels=labels,colors=colors,autopct='%1.1f%%',startangle=90,textprops={'fontsize':9})
    for a in at: a.set_fontweight('bold')
    ax.set_title('30路口相位模板分布与采样权重',fontsize=14,fontweight='bold',pad=15)
    ax.text(0,-1.4,'采样权重: A=0.45 | B=0.15 | C=0.20 | D=0.10 | E=0.10',ha='center',fontsize=9,style='italic',color='#555')
    plt.tight_layout(); plt.savefig(os.path.join(OUTPUT_DIR,'fig3_7_template_distribution.png'),bbox_inches='tight'); plt.close()
    print('Saved: fig3_7_template_distribution.png')

def chart_llm_pipeline():
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.set_xlim(0,14); ax.set_ylim(-0.5,6)
    ax.set_title('LLM云脑数据处理与微调流水线', fontsize=14, fontweight='bold', pad=15)
    ax.axis('off')
    def db(x,y,w,h,t,c,fs=8):
        ax.add_patch(FancyBboxPatch((x-w/2,y-h/2),w,h,boxstyle='round,pad=0.12',facecolor=c,edgecolor='none'))
        ax.text(x,y,t,ha='center',va='center',fontsize=fs,fontweight='bold',color='white')
    def da(x1,y1,x2,y2,l=''):
        ax.annotate('',xy=(x2,y2),xytext=(x1,y1),arrowprops=dict(arrowstyle='->',color='#555',lw=1.8))
        if l: ax.text((x1+x2)/2,(y1+y2)/2+0.25,l,ha='center',fontsize=7,color='#555',style='italic')
    db(2,5,2.2,0.9,'SUMO 30路口\n仿真运行','#3B82F6'); db(5,5,2.2,0.9,'每5s提取\n路口特征','#3B82F6')
    db(8,5,2.2,0.9,'30s窗口\n规则Oracle\n自动标注','#F59E0B'); db(11,5,2.2,0.9,'136,440条\n去重样本','#06A77D')
    da(3.1,5,3.9,5); da(6.1,5,6.9,5); da(9.1,5,9.9,5)
    db(5,3.2,3,0.9,'类别平衡抽样\n正常2000/拥堵2000\n溢出2000/事件231','#8B5CF6')
    db(9,3.2,3,0.9,'6,531条\n微调训练集','#06A77D')
    da(5,4.55,5,3.65); da(8,3.2,7.5,3.2)
    db(2,1.5,2.5,0.9,'Qwen2.5-0.5B\n基座模型\n(~1GB)','#3B82F6')
    db(5,1.5,2.5,0.9,'LoRA微调\nr=16, alpha=32\n~1%参数','#A23B72')
    db(8,1.5,2.5,0.9,'训练3 epochs\nloss~0.025\n适配器35MB','#06A77D')
    db(11,1.5,2.5,0.9,'准确率\n25%->99.5%','#06A77D')
    da(3.25,1.5,3.75,1.5); da(6.25,1.5,6.75,1.5); da(9.25,1.5,9.75,1.5); da(9,2.75,5,1.95)
    db(2,0.3,2.5,0.6,'合并LoRA\n->GGUF导出','#6B7280'); db(5,0.3,2.5,0.6,'f32 GGUF\n(1.98GB)','#06A77D')
    db(8,0.3,2.5,0.6,'llama.cpp\n部署服务','#D62828'); db(11,0.3,2.5,0.6,'准确率100%\n延迟~5s','#06A77D')
    da(3.25,0.3,3.75,0.3); da(6.25,0.3,6.75,0.3); da(8,0.6,8,1.05); da(9.25,0.3,9.75,0.3)
    plt.tight_layout(); plt.savefig(os.path.join(OUTPUT_DIR,'fig3_8_llm_pipeline.png'),bbox_inches='tight'); plt.close()
    print('Saved: fig3_8_llm_pipeline.png')

def chart_inference_performance():
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle('ONNX边缘推理性能基准', fontsize=14, fontweight='bold')
    models=['早高峰 FP32','晚高峰 FP32']; x=np.arange(2); w=0.3
    ax1=axes[0]
    mv=[0.022,0.023]; pv=[0.028,0.042]
    b1=ax1.bar(x-w/2,mv,w,label='均值',color='#3B82F6'); b2=ax1.bar(x+w/2,pv,w,label='P95',color='#F59E0B')
    ax1.set_xticks(x); ax1.set_xticklabels(models); ax1.set_ylabel('延迟 (ms)'); ax1.set_title('单路口推理延迟'); ax1.legend()
    ax1.axhline(y=5,color='#EF4444',lw=1.5,ls='--')
    for b,v in zip(b1,mv): ax1.text(b.get_x()+b.get_width()/2,b.get_height()+0.001,f'{v}',ha='center',fontsize=9)
    for b,v in zip(b2,pv): ax1.text(b.get_x()+b.get_width()/2,b.get_height()+0.001,f'{v}',ha='center',fontsize=9)
    ax2=axes[1]
    mv2=[0.029,0.031]; pv2=[0.048,0.053]
    b3=ax2.bar(x-w/2,mv2,w,label='均值',color='#3B82F6'); b4=ax2.bar(x+w/2,pv2,w,label='P95',color='#F59E0B')
    ax2.set_xticks(x); ax2.set_xticklabels(models); ax2.set_ylabel('延迟 (ms)'); ax2.set_title('30路口批量推理延迟'); ax2.legend()
    ax2.axhline(y=500,color='#EF4444',lw=1.5,ls='--')
    for b,v in zip(b3,mv2): ax2.text(b.get_x()+b.get_width()/2,b.get_height()+0.002,f'{v}',ha='center',fontsize=9)
    for b,v in zip(b4,pv2): ax2.text(b.get_x()+b.get_width()/2,b.get_height()+0.002,f'{v}',ha='center',fontsize=9)
    plt.tight_layout(); plt.savefig(os.path.join(OUTPUT_DIR,'fig3_9_inference_performance.png'),bbox_inches='tight'); plt.close()
    print('Saved: fig3_9_inference_performance.png')

def chart_container_architecture():
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_xlim(0,12); ax.set_ylim(0,7)
    ax.set_title('Docker容器化部署架构', fontsize=14, fontweight='bold', pad=15)
    ax.axis('off')
    def db(x,y,w,h,t,c,fs=9):
        ax.add_patch(FancyBboxPatch((x-w/2,y-h/2),w,h,boxstyle='round,pad=0.15',facecolor=c,edgecolor='none'))
        ax.text(x,y,t,ha='center',va='center',fontsize=fs,fontweight='bold',color='white')
    def da(x1,y1,x2,y2,l=''):
        ax.annotate('',xy=(x2,y2),xytext=(x1,y1),arrowprops=dict(arrowstyle='->',color='#555',lw=1.8))
        if l: ax.text((x1+x2)/2,(y1+y2)/2+0.2,l,ha='center',fontsize=7,color='#555',style='italic')
    ax.add_patch(Rectangle((0.5,0.5),11,6,lw=2,edgecolor='#3B82F6',facecolor='#F0F7FF',ls='dashed'))
    ax.text(0.7,6.3,'Docker Host',fontsize=10,color='#3B82F6',fontweight='bold')
    db(4,4.5,3,1.5,'xiongan-api容器\n(FastAPI, :8000)\n- 仿真会话管理\n- 660维状态拆分\n- 安全约束校验','#3B82F6',8)
    db(8.5,4.5,3,1.5,'xiongan-edge容器\n(ONNX, :8001)\n- 模型加载\n- 批量推理\n- 健康检查','#06A77D',8)
    da(5.5,4.5,7,4.5,'HTTP 30x26维')
    db(2,1.5,2.5,1,'models/\n(只读卷)','#F59E0B',8); db(5,1.5,2.5,1,'sumo_files/\n(只读卷)','#F59E0B',8); db(8.5,1.5,2.5,1,'image:\n394 MiB','#A23B72',8)
    da(2,2,3.5,3.75,'挂载'); da(5,2,4.5,3.75,'挂载'); da(8.5,2,8.5,3.75,'构建')
    db(4,6,3,0.6,'Unity / 客户端','#6B7280',9); da(4,5.25,4,5.7,'REST/WS')
    ax.text(6,0.7,'资源限制: 每容器 1 CPU / 512MB | 依赖: edge健康 -> api启动',ha='center',fontsize=8,color='#555',bbox=dict(boxstyle='round,pad=0.3',facecolor='#FFF3CD',edgecolor='#F59E0B'))
    plt.tight_layout(); plt.savefig(os.path.join(OUTPUT_DIR,'fig3_10_container_architecture.png'),bbox_inches='tight'); plt.close()
    print('Saved: fig3_10_container_architecture.png')

def chart_action_mask():
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.set_xlim(0,12); ax.set_ylim(-0.5,6)
    ax.set_title('需求门控动作掩码机制', fontsize=14, fontweight='bold', pad=15)
    ax.axis('off')
    def db(x,y,w,h,t,c,fs=9):
        ax.add_patch(FancyBboxPatch((x-w/2,y-h/2),w,h,boxstyle='round,pad=0.12',facecolor=c,edgecolor='none'))
        ax.text(x,y,t,ha='center',va='center',fontsize=fs,fontweight='bold',color='white')
    def da(x1,y1,x2,y2):
        ax.annotate('',xy=(x2,y2),xytext=(x1,y1),arrowprops=dict(arrowstyle='->',color='#555',lw=1.8))
    db(2,4.5,2.5,1,'步骤1:\n提取相位服务\n绿灯链路','#3B82F6'); da(3.25,4.5,4.5,4.5)
    db(5.5,4.5,2.5,1,'步骤2:\n统计链路上\n停车车辆数','#F59E0B'); da(6.75,4.5,8,4.5)
    db(9,4.5,2.5,1,'步骤3:\nhalting>=1?\n->mask=1','#06A77D')
    ax.text(6,3,'示例: 路口J05 (模板C)',ha='center',fontsize=10,fontweight='bold',color='#A23B72')
    data=[['动作','服务方向','排队车辆','掩码'],['action_0','NS直行','3','1'],['action_1','NS左转','0','0'],['action_2','EW直行','5','1'],['action_3','EW左转','0','0']]
    for i,row in enumerate(data):
        for j,cell in enumerate(row):
            bg='#6B7280' if i==0 else ('#D1FAE5' if (j==3 and cell=='1') else ('#FEE2E2' if (j==3 and cell=='0') else '#E8F0FE'))
            ax.add_patch(Rectangle((2+j*1.8,2-i*0.5),1.8,0.45,facecolor=bg,edgecolor='white',lw=1))
            tc='white' if i==0 else ('#06A77D' if (j==3 and cell=='1') else ('#EF4444' if (j==3 and cell=='0') else '#333'))
            ax.text(2.9+j*1.8,2.22-i*0.5,cell,ha='center',va='center',fontsize=8,color=tc,fontweight='bold')
    db(9,1,2.5,1,'有效动作\n仅action_0,2\n(避免空转)','#06A77D')
    ax.text(6,0.2,'全部动作无需求时兜底全1，避免死锁',ha='center',fontsize=8,style='italic',color='#555')
    plt.tight_layout(); plt.savefig(os.path.join(OUTPUT_DIR,'fig3_11_action_mask.png'),bbox_inches='tight'); plt.close()
    print('Saved: fig3_11_action_mask.png')

def chart_30_eval():
    fig,(ax1,ax2)=plt.subplots(2,1,figsize=(10,8),gridspec_kw={'height_ratios':[2,1]})
    fig.suptitle('30路口全量评估结果',fontsize=14,fontweight='bold')
    scenarios=['早高峰','平峰','晚高峰']
    dr=[79367,63010,76175]; fr=[71520,64059,69340]; imp=[11.0,-1.6,9.9]
    x=np.arange(3); w=0.35
    b1=ax1.bar(x-w/2,dr,w,label='DQN',color='#3B82F6'); b2=ax1.bar(x+w/2,fr,w,label='Fixed-Time',color='#F59E0B')
    ax1.set_xticks(x); ax1.set_xticklabels(scenarios); ax1.set_ylabel('总奖励')
    ax1.set_title('DQN vs Fixed-Time 总奖励对比（30路口x3回合x720步）'); ax1.legend()
    for b,v in zip(b1,dr): ax1.text(b.get_x()+b.get_width()/2,b.get_height()+500,f'{v:,}',ha='center',fontsize=9)
    for b,v in zip(b2,fr): ax1.text(b.get_x()+b.get_width()/2,b.get_height()+500,f'{v:,}',ha='center',fontsize=9)
    cs=['#06A77D' if v>0 else '#EF4444' for v in imp]
    b3=ax2.bar(x,imp,width=0.5,color=cs); ax2.set_xticks(x); ax2.set_xticklabels(scenarios)
    ax2.set_ylabel('Reward变化 (%)'); ax2.set_title('DQN相对Fixed-Time的Reward变化率'); ax2.axhline(y=0,color='gray',lw=0.5)
    for b,v in zip(b3,imp):
        s='+' if v>0 else ''; o=0.3 if v>=0 else -0.5
        ax2.text(b.get_x()+b.get_width()/2,b.get_height()+o,f'{s}{v}%',ha='center',fontsize=11,fontweight='bold')
    plt.tight_layout(); plt.savefig(os.path.join(OUTPUT_DIR,'fig3_12_30_eval.png'),bbox_inches='tight'); plt.close()
    print('Saved: fig3_12_30_eval.png')

def main():
    print('Generating charts for Chapter 3...')
    chart_road_network(); chart_dqn_architecture(); chart_training_loop()
    chart_lightweighting_pipeline(); chart_three_scenarios(); chart_reward_weights()
    chart_template_distribution(); chart_llm_pipeline(); chart_inference_performance()
    chart_container_architecture(); chart_action_mask(); chart_30_eval()
    print(f'All charts saved to: {OUTPUT_DIR}')

if __name__=='__main__': main()
