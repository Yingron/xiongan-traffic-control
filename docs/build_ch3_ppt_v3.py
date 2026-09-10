#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build Chapter 3 slides - clean approach: reorder without pre-deletion."""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn

SRC_PPT = r'c:\Users\荣光\.trae-cn\attachments\6a98e1978ea12dc3cddad2ca\3358e612-925d-4106-b4ca-83a32daf0481_5f3d1812-c513-4bce-9420-2e58c6f7c952_答辩PPT.pptx'
OUT_PPT = r'C:\Users\荣光\Desktop\挑战杯\xiongan-traffic-control\docs\答辩PPT_第3章完成版.pptx'
CHARTS_DIR = r'C:\Users\荣光\Desktop\挑战杯\xiongan-traffic-control\docs\ppt_charts'

# Style constants
C_PRIMARY = RGBColor(0x17, 0x36, 0x5D)
C_SECONDARY = RGBColor(0x33, 0x41, 0x55)
C_ACCENT_BLUE = RGBColor(0x25, 0x63, 0xEB)
C_ACCENT_TEAL = RGBColor(0x0D, 0x94, 0x88)
C_ACCENT_GREEN = RGBColor(0x05, 0x96, 0x69)
C_ACCENT_RED = RGBColor(0xDC, 0x26, 0x26)
C_ACCENT_PURPLE = RGBColor(0x7C, 0x3A, 0xED)
C_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
C_LIGHT_BG = RGBColor(0xF1, 0xF5, 0xF9)
C_CARD_BG = RGBColor(0xFF, 0xFF, 0xFF)
C_CARD_HEADER_BG = RGBColor(0x1E, 0x40, 0x6E)
C_BORDER = RGBColor(0xCB, 0xD5, 0xE1)
C_BANNER_BG = RGBColor(0x17, 0x36, 0x5D)

TITLE_FONT = Pt(28)
CARD_TITLE_FONT = Pt(18)
BODY_FONT = Pt(14)
BANNER_FONT = Pt(14)
BIG_NUMBER_FONT = Pt(36)

LEFT_MARGIN = 2.56
CONTENT_W = 10.27
TITLE_Y = 0.41
TITLE_H = 0.55
DIVIDER_Y = 0.96
CONTENT_START_Y = 1.25
BANNER_Y = 6.80
BANNER_H = 0.58
COL_GAP = 0.28
COL_W = (CONTENT_W - 2 * COL_GAP) / 3

def col_x(idx):
    return LEFT_MARGIN + idx * (COL_W + COL_GAP)

def add_title(slide, text):
    s1 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(LEFT_MARGIN), Inches(TITLE_Y+0.04), Inches(0.33), Inches(0.33))
    s1.fill.solid(); s1.fill.fore_color.rgb = C_PRIMARY; s1.line.fill.background()
    s2 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(LEFT_MARGIN+0.09), Inches(TITLE_Y+0.11), Inches(0.33), Inches(0.33))
    s2.fill.solid(); s2.fill.fore_color.rgb = C_ACCENT_TEAL; s2.line.fill.background()
    tx = slide.shapes.add_textbox(Inches(LEFT_MARGIN+0.50), Inches(TITLE_Y), Inches(CONTENT_W-0.5), Inches(TITLE_H))
    tf = tx.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.text = text; p.font.size = TITLE_FONT; p.font.bold = True
    p.font.color.rgb = C_PRIMARY; p.font.name = '微软雅黑'

def add_divider_line(slide):
    ln = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(LEFT_MARGIN), Inches(DIVIDER_Y), Inches(CONTENT_W-0.16), Inches(0.04))
    ln.fill.solid(); ln.fill.fore_color.rgb = C_BORDER; ln.line.fill.background()

def add_bottom_banner(slide, text):
    bn = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(LEFT_MARGIN-0.07), Inches(BANNER_Y), Inches(CONTENT_W+0.26), Inches(BANNER_H))
    bn.fill.solid(); bn.fill.fore_color.rgb = C_BANNER_BG; bn.line.fill.background()
    tx = slide.shapes.add_textbox(Inches(LEFT_MARGIN+0.15), Inches(BANNER_Y+0.08), Inches(CONTENT_W-0.3), Inches(BANNER_H-0.16))
    tf = tx.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.text = text; p.font.size = BANNER_FONT; p.font.bold = True
    p.font.color.rgb = C_WHITE; p.font.name = '微软雅黑'

def add_card(slide, col_idx, y, h, header_text, body_lines, hc=None):
    if hc is None: hc = C_CARD_HEADER_BG
    x = col_x(col_idx)
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(COL_W), Inches(h))
    card.fill.solid(); card.fill.fore_color.rgb = C_CARD_BG; card.line.color.rgb = C_BORDER; card.line.width = Pt(1)
    hd = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(COL_W), Inches(0.65))
    hd.fill.solid(); hd.fill.fore_color.rgb = hc; hd.line.fill.background()
    htx = slide.shapes.add_textbox(Inches(x+0.15), Inches(y+0.08), Inches(COL_W-0.3), Inches(0.5))
    htf = htx.text_frame; htf.word_wrap = True; htf.vertical_anchor = MSO_ANCHOR.MIDDLE
    hp = htf.paragraphs[0]; hp.text = header_text; hp.font.size = CARD_TITLE_FONT
    hp.font.bold = True; hp.font.color.rgb = C_WHITE; hp.font.name = '微软雅黑'
    btx = slide.shapes.add_textbox(Inches(x+0.18), Inches(y+0.78), Inches(COL_W-0.36), Inches(h-0.9))
    btf = btx.text_frame; btf.word_wrap = True
    for i, line in enumerate(body_lines):
        p = btf.paragraphs[0] if i == 0 else btf.add_paragraph()
        if isinstance(line, tuple):
            t, b = line; p.text = t; p.font.bold = b
        else:
            p.text = line; p.font.bold = False
        p.font.size = BODY_FONT; p.font.color.rgb = C_SECONDARY
        p.font.name = '微软雅黑'; p.space_after = Pt(6)

def add_stat_card(slide, col_idx, y, h, val, label, color=None):
    if color is None: color = C_ACCENT_BLUE
    x = col_x(col_idx)
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(COL_W), Inches(h))
    card.fill.solid(); card.fill.fore_color.rgb = C_CARD_BG; card.line.color.rgb = C_BORDER; card.line.width = Pt(1)
    nb = slide.shapes.add_textbox(Inches(x+0.15), Inches(y+0.25), Inches(COL_W-0.3), Inches(1.3))
    nf = nb.text_frame; nf.word_wrap = True
    np_ = nf.paragraphs[0]; np_.text = val; np_.font.size = BIG_NUMBER_FONT
    np_.font.bold = True; np_.font.color.rgb = color; np_.font.name = '微软雅黑'; np_.alignment = PP_ALIGN.CENTER
    lb = slide.shapes.add_textbox(Inches(x+0.15), Inches(y+h-0.95), Inches(COL_W-0.3), Inches(0.8))
    lf = lb.text_frame; lf.word_wrap = True
    lp = lf.paragraphs[0]; lp.text = label; lp.font.size = BODY_FONT
    lp.font.color.rgb = C_SECONDARY; lp.font.name = '微软雅黑'; lp.alignment = PP_ALIGN.CENTER

def add_intro(slide, text):
    tx = slide.shapes.add_textbox(Inches(LEFT_MARGIN+0.10), Inches(CONTENT_START_Y), Inches(CONTENT_W-0.2), Inches(0.6))
    tf = tx.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.text = text; p.font.size = Pt(15)
    p.font.color.rgb = C_SECONDARY; p.font.name = '微软雅黑'

def add_chart(slide, name, x, y, w, h):
    import glob
    files = glob.glob(os.path.join(CHARTS_DIR, name + '_*.png'))
    if not files:
        print(f'WARNING: Chart not found: {name}'); return None
    return slide.shapes.add_picture(files[0], Inches(x), Inches(y), width=Inches(w), height=Inches(h))

# ============================================================
# SLIDE BUILDERS
# ============================================================

def build_divider(ppt, num, title):
    slide = ppt.slides.add_slide(ppt.slide_layouts[10])
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(2.12), Inches(1.72), Inches(11.22), Inches(3.92))
    bg.fill.solid(); bg.fill.fore_color.rgb = C_PRIMARY; bg.line.fill.background()
    ac = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.86), Inches(5.64), Inches(11.66), Inches(0.16))
    ac.fill.solid(); ac.fill.fore_color.rgb = C_ACCENT_TEAL; ac.line.fill.background()
    nb = slide.shapes.add_textbox(Inches(7.06), Inches(2.31), Inches(1.33), Inches(0.64))
    p = nb.text_frame.paragraphs[0]; p.text = num; p.font.size = Pt(36)
    p.font.bold = True; p.font.color.rgb = C_ACCENT_TEAL; p.font.name = '微软雅黑'
    tb = slide.shapes.add_textbox(Inches(2.87), Inches(3.20), Inches(10.56), Inches(1.45))
    tf = tb.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.text = title; p.font.size = Pt(40)
    p.font.bold = True; p.font.color.rgb = C_WHITE; p.font.name = '微软雅黑'
    return slide

def build_3_1(ppt):
    s = ppt.slides.add_slide(ppt.slide_layouts[10])
    add_title(s, '3.1 高保真仿真环境构建')
    add_divider_line(s)
    add_intro(s, '30路口"窄路密网"场景 + 三时段真实交通流 + 规范化信号方案，构建可复现的数字靶场')
    add_card(s, 0, CONTENT_START_Y+0.75, 4.3, '路网设计', [
        ('30路口 6×5 网格布局', True), '双向3车道，限速50km/h',
        '路口间距短，贴近"窄路密网"特征',
        '5种rl4相位模板（A:20/B:4/C:3/D:2/E:1）',
        ('统一路口顺序 J01-J30', True),
    ], C_ACCENT_BLUE)
    add_card(s, 1, CONTENT_START_Y+0.75, 4.3, '信号方案规范化', [
        ('4个可控相位（排除黄灯相位）', True),
        '最小绿灯 15s + 黄灯过渡 3s',
        '右转/掉头改为让行绿灯g',
        '消除 Unsafe green 冲突',
        ('复验：0碰撞，0传送', True),
    ], C_ACCENT_TEAL)
    add_card(s, 2, CONTENT_START_Y+0.75, 4.3, '三场景交通流', [
        ('早高峰：51,868 辆', True),
        '平峰：44,947 辆（需求因子0.60）',
        ('晚高峰：50,296 辆', True),
        '均为 7,200s 时间窗',
        '按定周期基线容量标定',
    ], C_ACCENT_GREEN)
    add_bottom_banner(s, '环境验收：TraCI查询到恰好30个信号灯，真实定周期基线7200s全通无死锁')
    return s

def build_3_2(ppt):
    s = ppt.slides.add_slide(ppt.slide_layouts[10])
    add_title(s, '3.2 DQN算法实现与训练')
    add_divider_line(s)
    add_intro(s, '共享参数 Double-DQN + 需求门控动作掩码 + 模板分层采样，适配异构路口结构')
    add_card(s, 0, CONTENT_START_Y+0.75, 2.0, '状态与动作', [
        ('660维全局状态（30×22）', True),
        '22维局部观测 + 4维掩码 = 26维',
        '4动作 + 需求门控掩码',
    ], C_ACCENT_BLUE)
    add_card(s, 0, CONTENT_START_Y+2.95, 2.1, '奖励函数 V5', [
        ('溢出风险权重 2.0', True),
        '真实通过数权重 2.0',
        '队列压力 0.8 + 最大排队 0.6',
        '均衡/停滞/切换惩罚项',
    ], C_ACCENT_TEAL)
    add_card(s, 1, CONTENT_START_Y+0.75, 4.3, '网络与训练配置', [
        ('Double-DQN + 64×64 双层 MLP', True),
        '总参数量约 11,784',
        '掩码：MASK_FILL = 3.0e38',
        '模板分层采样（A:0.45/B:0.15/C:0.20/D:0.10/E:0.10）',
        '学习率 3e-4，批大小 256',
        '回放缓冲 200,000，ε 1.0→0.1',
        ('GPU 实测约 18 steps/s', True),
    ], C_PRIMARY)
    add_card(s, 2, CONTENT_START_Y+0.75, 4.3, '动作掩码机制', [
        ('需求门控，根治相位锁死', True),
        '非C模板：全[1,1,1,1]',
        'rl4模板：统计绿灯链路停车辆数',
        '停车辆数 ≥ 1 → 该动作掩码为1',
        '全动作无需求时兜底全1',
        ('解决异构拓扑上的相位锁死问题', True),
    ], C_ACCENT_PURPLE)
    add_bottom_banner(s, '核心创新：需求门控动作掩码 + 模板分层采样，统一策略在5种异构路口上合法运行')
    return s

def build_3_3(ppt):
    s = ppt.slides.add_slide(ppt.slide_layouts[10])
    add_title(s, '3.3 模型轻量化与容器化部署')
    add_divider_line(s)
    add_intro(s, 'SB3教师模型 → ONNX导出 → Docker容器化，全链路保真验证达标')
    add_stat_card(s, 0, CONTENT_START_Y+0.75, 2.0, '25.14 KB', '模型体积（目标 <1MB）', C_ACCENT_GREEN)
    add_stat_card(s, 0, CONTENT_START_Y+2.95, 2.1, '0.022 ms', '单路口推理（目标 <5ms）', C_ACCENT_BLUE)
    add_card(s, 1, CONTENT_START_Y+0.75, 4.3, '轻量化链路', [
        ('SB3 教师模型 (zip ~121KB)', True),
        '↓ TorchScript 转换',
        '↓ ONNX opset 17 导出',
        ('FP32 ONNX：25,742B（~25.14KB）', True),
        '体积较教师减少约 79%', '',
        ('保真验证：100% 动作一致', True),
        '2,880条真实SUMO状态',
        '三场景 × 8代表路口 × 120决策',
    ], C_ACCENT_TEAL)
    add_chart(s, 'lightweight_comparison', col_x(2), CONTENT_START_Y+0.75, COL_W, 2.2)
    add_card(s, 2, CONTENT_START_Y+3.10, 1.95, 'Docker 部署', [
        ('镜像 394 MiB，双容器一键启动', True),
        'edge + api 健康检查全 PASS',
        '模型/路网只读卷挂载',
    ], C_PRIMARY)
    add_bottom_banner(s, '负面发现：INT8量化真实一致率仅84-93%——轻量化必须逐任务实测验证')
    return s

def build_3_4(ppt):
    s = ppt.slides.add_slide(ppt.slide_layouts[10])
    add_title(s, '3.4 三场景对比实验结果')
    add_divider_line(s)
    add_intro(s, 'DQN vs 真实Fixed-Time 同负荷对比，8路口代表口径 + 30路口全量口径')
    add_chart(s, 'scenario_comparison', LEFT_MARGIN+0.1, CONTENT_START_Y+0.65, 5.2, 3.0)
    add_chart(s, 'template_wins', LEFT_MARGIN+0.1, CONTENT_START_Y+3.80, 5.2, 2.3)
    add_card(s, 1, CONTENT_START_Y+0.65, 2.5, '8路口代表口径', [
        ('早高峰：reward +13.7%', True),
        '平峰：+5.4%（晚高峰模型泛化）',
        ('晚高峰：reward +15.4%', True),
        '胜/8：早5 平6 晚5',
    ], C_ACCENT_BLUE)
    add_card(s, 1, CONTENT_START_Y+3.35, 2.75, '30路口全量口径', [
        ('早高峰：+11.0%（20/30胜）', True),
        ('晚高峰：+9.9%（20/30胜）', True),
        ('平峰：−1.6%（22/30胜）', True),
        '→ J16/J18低流量路口等待剧增',
        '根因：最小绿灯固定空转开销',
        ('机制性弱点，重训无法解决', True),
    ], C_ACCENT_RED)
    add_bottom_banner(s, '如实呈现：平峰收益为负——DQN在低流量场景存在最小绿灯切换开销的机制性弱点')
    return s

def build_3_5(ppt):
    s = ppt.slides.add_slide(ppt.slide_layouts[10])
    add_title(s, '3.5 工程目标达成情况')
    add_divider_line(s)
    add_intro(s, '10项工程目标逐项核对，核心指标超额完成赛题要求')
    data = [
        ['序号', '工程目标', '赛题要求', '实测结果', '判定'],
        ['1', '路网规模', '≥20路口', '30路口6×5网格', '✅ 超额'],
        ['2', '状态契约', '标准化观测', '660维全局+22维局部', '✅ 达标'],
        ['3', '决策约束', '安全动作空间', '4动作+需求门控掩码', '✅ 达标'],
        ['4', '模型体积', '< 1 MB', '25.14 KB (FP32 ONNX)', '✅ 远超'],
        ['5', '单路口推理延迟', '< 5 ms', '0.022 ms (mean)', '✅ 远超'],
        ['6', '30路口批量延迟', '< 500 ms', '0.029 ms (mean)', '✅ 远超'],
        ['7', '动作退化率', '≤5%', '0%（真实状态100%一致）', '✅ 达标'],
        ['8', '三场景对比', '同负荷对比', '早/晚高峰 +11~15%', '✅ 主体达标'],
        ['9', '演示闭环', '仿真+推理+可视化', 'Unity-WS-SUMO-ONNX闭环', '✅ 达标'],
        ['10', 'LLM云脑（赛道C）', '事件识别+建议', 'f32 GGUF准确率100%', '✅ 达标'],
    ]
    rows, cols = len(data), len(data[0])
    tx, ty = LEFT_MARGIN+0.1, CONTENT_START_Y+0.65
    tw, th = CONTENT_W-0.2, 4.6
    ts = s.shapes.add_table(rows, cols, Inches(tx), Inches(ty), Inches(tw), Inches(th))
    table = ts.table
    cw = [0.6, 1.6, 1.8, 3.2, 1.5]
    total = sum(cw)
    for i, w in enumerate(cw):
        table.columns[i].width = Inches(tw * w / total)
    for r in range(rows):
        for c in range(cols):
            cell = table.cell(r, c); cell.text = data[r][c]
            for para in cell.text_frame.paragraphs:
                para.font.name = '微软雅黑'; para.font.size = Pt(11)
                para.alignment = PP_ALIGN.CENTER
                if r == 0:
                    para.font.bold = True; para.font.color.rgb = C_WHITE; para.font.size = Pt(12)
                elif c == 4:
                    para.font.bold = True
                    para.font.color.rgb = C_ACCENT_GREEN if '✅' in data[r][c] else C_ACCENT_RED
                else:
                    para.font.color.rgb = C_SECONDARY
            if r == 0:
                cell.fill.solid(); cell.fill.fore_color.rgb = C_PRIMARY
            elif r % 2 == 0:
                cell.fill.solid(); cell.fill.fore_color.rgb = C_LIGHT_BG
            else:
                cell.fill.solid(); cell.fill.fore_color.rgb = C_WHITE
    add_bottom_banner(s, '核心指标超额完成：模型体积仅为目标的2.5%，推理延迟仅为目标的0.4%')
    return s

# ============================================================
# MAIN
# ============================================================

def main():
    print('Loading source PPT...')
    ppt = Presentation(SRC_PPT)
    orig_count = len(ppt.slides)
    print(f'Original: {orig_count} slides')
    
    # Strategy: 
    # 1. Add 6 new ch3 slides at the END (making total 26)
    # 2. Reorder sldIdLst: slides 1-12, new ch3 (6 slides), slides 15-20
    #    Skip slides 13-14 (wrong content) - they stay in the file but are not shown
    
    print('Building 6 Chapter 3 slides...')
    build_divider(ppt, '03', '实验设计与结果')
    build_3_1(ppt)
    build_3_2(ppt)
    build_3_3(ppt)
    build_3_4(ppt)
    build_3_5(ppt)
    
    total = len(ppt.slides)
    print(f'After adding: {total} slides')
    
    # Now reorder the sldIdLst
    # Original order (1-based indices in slide list):
    #   1-12: ch1 + ch2 (keep)
    #   13-14: WRONG content (skip - don't include in new order)
    #   15-20: ch4 + refs (keep)
    #   21-26: new ch3 slides (insert between ch2 and ch4)
    #
    # Desired order: 1-12, 21-26, 15-20
    
    sldIdLst = ppt.slides._sldIdLst
    current = list(sldIdLst)
    
    print(f'Reordering {len(current)} slides...')
    
    # Remove all
    for elem in current:
        sldIdLst.remove(elem)
    
    # Add in desired order
    # 1. Slides 1-12 (indices 0-11): ch1 + ch2
    for i in range(12):
        sldIdLst.append(current[i])
    
    # 2. New ch3 slides (indices 20-25 = slides 21-26)
    for i in range(20, 26):
        sldIdLst.append(current[i])
    
    # 3. Slides 15-20 (indices 14-19): ch4 + refs
    for i in range(14, 20):
        sldIdLst.append(current[i])
    
    final_count = len(ppt.slides)
    print(f'Final: {final_count} slides in presentation')
    
    # Verify
    print('\nSlide order:')
    for i, slide in enumerate(ppt.slides):
        title = ''
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                title = shape.text_frame.text.strip().split('\n')[0][:55]
                break
        chapter = ''
        if i < 12: chapter = 'Ch1+2'
        elif i < 18: chapter = 'Ch3 ⭐'
        else: chapter = 'Ch4'
        print(f'  {i+1:2d}. [{chapter}] {title}')
    
    print(f'\nSaving to {OUT_PPT}...')
    ppt.save(OUT_PPT)
    print('Done!')

if __name__ == '__main__':
    main()
