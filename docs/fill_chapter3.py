# -*- coding: utf-8 -*-
import sys, os, copy
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph
from docx.table import Table

BASE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(BASE, '\u7cfb\u7edf\u8bbe\u8ba1\u4e0e\u7b97\u6cd5\u62a5\u544a .docx')
CHARTS = os.path.join(BASE, 'charts')
OUT = DOC

def find_heading(doc, text_prefix):
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip().startswith(text_prefix):
            return i
    return None

def add_heading_after(doc, ref_elem, text, level=3):
    new_p = OxmlElement('w:p')
    ref_elem.addnext(new_p)
    p = Paragraph(new_p, doc)
    try:
        p.style = doc.styles['Heading %d' % level]
    except:
        pass
    p.add_run(text)
    return p, new_p

def add_para_after(doc, ref_elem, text='', bold_parts=None):
    new_p = OxmlElement('w:p')
    ref_elem.addnext(new_p)
    p = Paragraph(new_p, doc)
    try:
        p.style = doc.styles['Normal']
    except:
        pass
    if bold_parts:
        for part, is_bold in bold_parts:
            r = p.add_run(part)
            r.bold = is_bold
            r.font.size = Pt(10.5)
    elif text:
        r = p.add_run(text)
        r.font.size = Pt(10.5)
    return p, new_p

def add_bullet_after(doc, ref_elem, text):
    new_p = OxmlElement('w:p')
    ref_elem.addnext(new_p)
    p = Paragraph(new_p, doc)
    try:
        p.style = doc.styles['List Bullet']
    except:
        r = p.add_run('\u2022 ' + text)
        r.font.size = Pt(10.5)
        return p, new_p
    r = p.add_run(text)
    r.font.size = Pt(10.5)
    return p, new_p

def add_image_after(doc, ref_elem, img_path, width_in=5.5, caption=None):
    new_p = OxmlElement('w:p')
    ref_elem.addnext(new_p)
    p = Paragraph(new_p, doc)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run()
    r.add_picture(img_path, width=Inches(width_in))
    if caption:
        cp, ce = add_para_after(doc, new_p, caption)
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for r in cp.runs:
            r.font.size = Pt(9)
            r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        return cp, ce
    return p, new_p

def add_table_after(doc, ref_elem, headers, rows):
    tbl = OxmlElement('w:tbl')
    tblPr = OxmlElement('w:tblPr')
    tblW = OxmlElement('w:tblW')
    tblW.set(qn('w:w'), '5000')
    tblW.set(qn('w:type'), 'pct')
    tblPr.append(tblW)
    jc = OxmlElement('w:jc')
    jc.set(qn('w:val'), 'center')
    tblPr.append(jc)
    tblBorders = OxmlElement('w:tblBorders')
    for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        border = OxmlElement('w:' + border_name)
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '4')
        border.set(qn('w:space'), '0')
        border.set(qn('w:color'), 'auto')
        tblBorders.append(border)
    tblPr.append(tblBorders)
    tbl.append(tblPr)
    tblGrid = OxmlElement('w:tblGrid')
    for _ in headers:
        gc = OxmlElement('w:gridCol')
        tblGrid.append(gc)
    tbl.append(tblGrid)
    ref_elem.addnext(tbl)
    table = Table(tbl, doc)
    row = table.add_row()
    for i, h in enumerate(headers):
        c = row.cells[i]
        c.text = h
        for p in c.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(9)
    for row_data in rows:
        row = table.add_row()
        for i, val in enumerate(row_data):
            c = row.cells[i]
            c.text = str(val)
            for p in c.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    r.font.size = Pt(9)
    try:
        table.style = doc.styles['Table Grid']
    except:
        pass
    return table, tbl

def build_content(doc, start_elem):
    ref = start_elem
    c = CHARTS

    # === 3.1 ===
    ref = add_heading_after(doc, ref, '3.1 \u7b97\u6cd5\u5b9e\u73b0\u7ec6\u8282\u4e0e\u8bad\u7ec3\u6d41\u7a0b', 2)[1]

    # 3.1.1
    ref = add_heading_after(doc, ref, '3.1.1 \u73af\u5883\u5c01\u88c5\u4e0e\u72b6\u6001\u63d0\u53d6', 3)[1]
    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u591a\u8def\u53e3RL\u73af\u5883\u63d0\u4f9b660\u7ef4\u89c2\u6d4b\u300130\u00d74\u52a8\u4f5c\u7a7a\u95f4\u4e0e\u5b8c\u6574\u7684\u56de\u5408\u63a5\u53e3\uff08\u91cd\u7f6e\u3001\u5355\u6b65\u63a8\u8fdb\u3001\u72b6\u6001\u63d0\u53d6\u3001\u6279\u91cf\u52a8\u4f5c\u6267\u884c\uff09\u3002\u5168\u5c40\u72b6\u6001\u63d0\u53d6\u7531', False),
        ('get_global_state()', True),
        ('\u51fd\u6570\u5b9e\u73b0\uff0c\u8fd4\u56de30\u00d722=660\u7ef4\u6d6e\u70b9\u6570\u7ec4\u3002\u8f66\u9053\u6620\u5c04\u6309\u8f66\u9053\u7f16\u53f7\u9996\u5b57\u7b26\u5224\u65ad\u65b9\u5411\uff08N/S/E/W\uff09\uff0c\u4f18\u5148\u53d6\u76f4\u884c\u8f66\u9053\uff1b\u5bb9\u9519\u673a\u5236\u8986\u76d6\u65b9\u5411\u7f3a\u5931\u3001\u76f8\u4f4d\u8d8a\u754c\u3001\u8def\u53e3\u4e0d\u8db3\u7b49\u60c5\u51b5\u3002', False),
    ])[1]

    ref = add_para_after(doc, ref, '\u6bcf\u4e2a\u8def\u53e3\u516c\u5f0022\u7ef4\u7279\u5f81\uff0c\u7279\u5f81\u5212\u5206\u5982\u4e0b\u8868\u6240\u793a\uff1a')[1]

    ref = add_table_after(doc, ref,
        ['\u5c40\u90e8\u7d22\u5f15', '\u7279\u5f81', '\u7ef4\u5ea6', '\u5f52\u4e00\u5316/\u7f16\u7801'],
        [
            ['0-3', 'N/S/E/W \u6392\u961f\u957f\u5ea6', '4', 'min(queue/15, 1)'],
            ['4-7', 'N/S/E/W \u5e73\u5747\u7b49\u5f85\u65f6\u95f4', '4', 'min(wait/120, 1)'],
            ['8-11', 'N/S/E/W \u8f66\u9053\u5360\u6709\u7387', '4', '[0,1] \u539f\u503c'],
            ['12-15', 'N/S/E/W \u6ea2\u51fa\u98ce\u9669', '4', 'min(queue/15, 1)'],
            ['16-19', '\u5f53\u524d\u76f8\u4f4d', '4', 'One-Hot'],
            ['20-21', '\u65f6\u6bb5\u7279\u5f81', '2', 'sin/cos \u5468\u671f\u7f16\u7801'],
        ]
    )[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u8bbe\u8ba1\u8003\u91cf\uff1a', True),
        ('\u6ea2\u51fa\u98ce\u9669\u7279\u5f81\u9488\u5bf9\u7a84\u8def\u5bc6\u7f51\u201c\u8d85\u5bb9\u201d\u98ce\u9669\uff0c\u63d0\u9192\u6a21\u578b\u4f18\u5148\u5904\u7406\u9ad8\u98ce\u9669\u65b9\u5411\uff1bsin/cos\u7f16\u7801\u89e3\u51b3\u96f6\u70b9\u4e0e0\u70b9\u7684\u5468\u671f\u4e0d\u8fde\u7eed\uff1b\u76f8\u4f4dOne-Hot\u8ba9\u6a21\u578b\u611f\u77e5\u5f53\u524d\u65f6\u5e8f\u72b6\u6001\u3002', False),
    ])[1]

    img = os.path.join(c, 'fig3_2_dqn_architecture.png')
    if os.path.exists(img):
        ref = add_image_after(doc, ref, img, 5.5, '\u56fe3-2 \u53c2\u6570\u5171\u4eab\u63a9\u7801DQN\u7f51\u7edc\u7ed3\u6784\u4e0e\u6570\u636e\u6d41')[1]

    # 3.1.2
    ref = add_heading_after(doc, ref, '3.1.2 \u5956\u52b1\u51fd\u6570\u5b9e\u73b0', 3)[1]
    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u5956\u52b1\u51fd\u6570\u5b9e\u73b0\u7248\u672c\u53f7v3\uff08\u63a5\u53e3\u540d\u79f0V5\uff09\uff0c\u91c7\u7528\u201c\u60e9\u7f5a\u9879 + \u6b63\u5411\u5956\u52b1\u201d\u7684\u590d\u5408\u7ed3\u6784\u3002\u5176\u4e2d\u60e9\u7f5a\u9879\u5305\u542b\u6e29\u5ea6\u3001\u538b\u529b\u3001\u6ea2\u51fa\u3001\u5747\u8861\u3001\u505c\u6ede\u7b49\u591a\u4e2a\u5b50\u9879\uff0c\u6b63\u5411\u5956\u52b1\u5305\u542b\u901a\u8fc7\u8f66\u8f86\u6570\u548c\u7b49\u5f85\u51cf\u5c11\u3002\u5404\u9879\u6743\u91cd\u5982\u4e0b\u8868\u6240\u793a\uff1a', False),
    ])[1]

    ref = add_table_after(doc, ref,
        ['\u9879', '\u6743\u91cd', '\u7269\u7406\u610f\u4e49'],
        [
            ['\u6ea2\u51fa\u98ce\u9669 p_overflow', '2.0', '\u5b89\u5168\u6027\uff08\u7a84\u8def\u5bc6\u7f51\u6392\u961f\u56de\u5835\uff09'],
            ['\u771f\u5b9e\u901a\u8fc7\u6570 n_crossed', '2.0', '\u672c\u6b65\u8d8a\u8fc7\u505c\u8f66\u7ebf\u7684\u8f66\u8f86\u6570'],
            ['\u961f\u5217\u538b\u529b q_pressure', '0.8', '\u901a\u884c\u6548\u7387\uff08\u5e73\u5747\u6392\u961f\uff09'],
            ['\u6700\u5927\u6392\u961f q_max', '0.6', '\u516c\u5e73\u6027\uff08\u6700\u5835\u65b9\u5411\uff09'],
            ['\u961f\u5217\u51cf\u5c11 r_queue', '0.5', '\u901a\u8fc7\u8f66\u8f86\u6570\u7684\u4ee3\u7406\u6b63\u5411\u5956\u52b1'],
            ['\u5e73\u5747\u7b49\u5f85 avg_wait', '0.4', '\u901a\u884c\u6548\u7387'],
            ['\u7b49\u5f85\u51cf\u5c11 r_wait', '0.3', '\u603b\u7b49\u5f85\u65f6\u95f4\u51cf\u5c11\u7684\u6b63\u5411\u5956\u52b1'],
            ['\u5747\u8861\u60e9\u7f5a p_balance', '0.1', '\u5404\u65b9\u5411\u6392\u961f\u65b9\u5dee'],
            ['\u505c\u6ede\u60e9\u7f5a p_stag', '0.08', '\u6b7b\u5b88\u76f8\u4f4d\u4e0d\u670d\u52a1\u8f66\u8f86\uff08\u8fde\u7eed\u540c\u52a8\u4f5c>2\u6b65\uff09'],
            ['\u76f8\u4f4d\u5207\u6362 c_switch', '0.01', '\u7a33\u5b9a\u6027\uff08\u4f4e\u6743\u91cd\uff0c\u907f\u514d\u538b\u5236\u6b63\u5e38\u66f4\u66ff\uff09'],
        ]
    )[1]

    img = os.path.join(c, 'fig3_6_reward_weights.png')
    if os.path.exists(img):
        ref = add_image_after(doc, ref, img, 5.0, '\u56fe3-3 V5\u5956\u52b1\u51fd\u6570\u5404\u9879\u6743\u91cd\u5206\u5e03')[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u5b9e\u73b0\u7ec6\u8282\uff1a', True),
        ('\u5956\u52b1\u7531', False),
        ('compute_reward()', True),
        ('\u51fd\u6570\u8ba1\u7b97\uff0c\u63a5\u53d7\u5c40\u90e8\u72b6\u6001\u3001\u5f53\u524d\u52a8\u4f5c\u3001\u524d\u4e00\u52a8\u4f5c\u3001\u524d\u4e00\u72b6\u6001\u3001\u540c\u52a8\u4f5c\u8ba1\u6570\u548c\u8d8a\u8fc7\u8f66\u8f86\u6570\u7b49\u53c2\u6570\uff0c\u8fd4\u56de\u6807\u91cf\u5956\u52b1\u548c\u5206\u9879\u660e\u7ec6\u5b57\u5178\u3002\u6bcf\u4e2a\u8def\u53e3\u72ec\u7acb\u8ba1\u7b97\u5956\u52b1\uff0c\u5168\u5c40\u5956\u52b1\uff0830\u8def\u53e3\u5e73\u5747\u503c\uff09\u4ec5\u7528\u4e8e\u76d1\u63a7\u3002', False),
    ])[1]

    # 3.1.3
    ref = add_heading_after(doc, ref, '3.1.3 \u7f51\u7edc\u67b6\u6784\u4e0e\u8bad\u7ec3\u914d\u7f6e', 3)[1]
    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u6b63\u5f0f\u6a21\u578b\u4e3a64\u00d764\u53cc\u5c42MLP + Double-DQN + \u9700\u6c42\u95e8\u63a7\u63a9\u7801\uff0c\u603b\u53c2\u6570\u91cf\u7ea611,784\u3002\u63a8\u7406\u65f6\u8f93\u516526\u7ef4\uff0822\u72b6\u6001+4\u63a9\u7801\uff09\uff0c\u8f93\u51fa4\u4e2aQ\u503c\u3002\u63a9\u7801\u5b9e\u73b0\u91c7\u7528', False),
        ('MASK_FILL = 3.0e38', True),
        ('\u7684\u5927\u503c\u60e9\u7f5a\u7b56\u7565\uff1a\u6709\u6548\u52a8\u4f5c\u4fdd\u6301\u539f\u59cbQ\u503c\uff0c\u65e0\u6548\u52a8\u4f5c\u88ab\u8d4b\u4e88\u6781\u5927\u8d1f\u503c\uff0c\u786e\u4fddargmax\u6c38\u4e0d\u9009\u62e9\u88ab\u63a9\u7801\u7684\u52a8\u4f5c\u3002', False),
    ])[1]

    ref = add_table_after(doc, ref,
        ['\u914d\u7f6e\u540d\u79f0', '\u5b66\u4e60\u7387', '\u7f13\u51b2\u533a', '\u6279\u5927\u5c0f', '\u7f51\u7edc\u7ed3\u6784', '\u63a2\u7d22\u7387', '\u7528\u9014'],
        [
            ['DQN_CONFIG', '1e-4', '1,000,000', '64', '-', '1.0\u21920.05(10%)', '\u6807\u51c6\u8bad\u7ec3'],
            ['PERF_DQN_CONFIG', '3e-4', '200,000', '256', '[64,64]', '1.0\u21920.1(50%)', '\u9ad8\u6027\u80fd\u5feb\u901f\u8bad\u7ec3'],
            ['ANTICOLLAPSE', '5e-4', '500,000', '128', '[256,256,128]', '1.0\u21920.1(30%)', '\u6297\u7b56\u7565\u574d\u7f29'],
        ]
    )[1]

    img = os.path.join(c, 'fig3_3_training_loop.png')
    if os.path.exists(img):
        ref = add_image_after(doc, ref, img, 4.5, '\u56fe3-4 \u591a\u8def\u53e3DQN\u8bad\u7ec3\u4e3b\u5faa\u73af\u6d41\u7a0b')[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u8bad\u7ec3\u4e3b\u5faa\u73af\uff1a', True),
        ('\u542f\u52a8SUMO\u83b7\u53d6\u4fe1\u53f7\u706fID \u2192 \u91cd\u7f6e\u5e76\u5207\u7247660\u7ef4\u72b6\u6001 \u2192 \u6bcf\u8def\u53e3\u72ec\u7acb\u03b5-\u8d2a\u5a6a\u9009\u62e9\u52a8\u4f5c \u2192 \u6279\u91cf\u8bbe\u7f6e30\u8def\u53e3\u76f8\u4f4d\u5e76\u63a8\u8fdb\u4eff\u771f\uff085s\u6b65\u957f\uff09 \u2192 \u8ba1\u7b97\u5956\u52b1\u5b58\u5165\u5171\u4eab\u56de\u653e\u6c60 \u2192 \u6bcf4\u6b65\u91c7\u6837\u66f4\u65b0\u7f51\u7edc \u2192 \u03b5\u7ebf\u6027\u8870\u51cf\u3002\u8bad\u7ec3\u6027\u80fd\u74f6\u9888\u5206\u6790\u663e\u793a\u4eff\u771f\u536041.2%\u3001\u7f51\u7edc\u66f4\u65b058.8%\uff0cGPU\u5b9e\u6d4b\u7ea618 steps/s\u3002', False),
    ])[1]

    # 3.1.4
    ref = add_heading_after(doc, ref, '3.1.4 \u52a8\u4f5c\u63a9\u7801\u673a\u5236\u5b9e\u73b0', 3)[1]
    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u9700\u6c42\u95e8\u63a7\u52a8\u4f5c\u63a9\u7801\u7531', False),
        ('compute_action_mask()', True),
        ('\u51fd\u6570\u5b9e\u73b0\uff0c\u7b97\u6cd5\u5982\u4e0b\uff1a\u5bf9\u4e8e\u975eC\u6a21\u677f\u8def\u53e3\uff0c\u8fd4\u56de\u5168[1,1,1,1]\uff1b\u5bf9\u4e8erl4\u6a21\u677f\u8def\u53e3\uff0c\u8bfb\u53d6\u6bcf\u4e2a\u76f8\u4f4d\u7684\u72b6\u6001\u5b57\u7b26\u4e32\uff0c\u8bc6\u522b\u7eff\u706f\u94fe\u8def\uff08"G"\u6216"g"\uff09\uff0c\u7edf\u8ba1\u8fd9\u4e9b\u94fe\u8def\u4e0a\u7684\u505c\u8f66\u8f86\u6570\uff0c\u82e5\u505c\u8f66\u8f86\u6570\u22651\u5219\u8be5\u52a8\u4f5c\u63a9\u7801\u4e3a1\uff0c\u5168\u90e8\u52a8\u4f5c\u65e0\u9700\u6c42\u65f6\u5151\u5e95\u51681\u907f\u514d\u6b7b\u9501\u3002', False),
    ])[1]

    img = os.path.join(c, 'fig3_11_action_mask.png')
    if os.path.exists(img):
        ref = add_image_after(doc, ref, img, 5.5, '\u56fe3-5 \u9700\u6c42\u95e8\u63a7\u52a8\u4f5c\u63a9\u7801\u673a\u5236')[1]

    img = os.path.join(c, 'fig3_7_template_distribution.png')
    if os.path.exists(img):
        ref = add_image_after(doc, ref, img, 4.0, '\u56fe3-6 30\u8def\u53e3\u76f8\u4f4d\u6a21\u677f\u5206\u5e03\u4e0e\u91c7\u6837\u6743\u91cd')[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u6a21\u677f\u5206\u5c42\u91c7\u6837\uff1a', True),
        ('30\u4e2a\u8def\u53e3\u76844\u52a8\u4f5c\u7a0b\u5e8f\u5e76\u975e\u540c\u6784\uff0c\u8def\u7f51\u4e2d\u5b58\u57285\u79cdrl4\u76f8\u4f4d\u6a21\u677f\uff08A:20/B:4/C:3/D:2/E:1\uff09\u3002\u5171\u4eab\u53c2\u6570DQN\u82e5\u6309\u8def\u53e3\u5747\u5300\u91c7\u6837\uff0c\u6a21\u677fA\uff0867%\uff09\u4f1a\u4e3b\u5bfc\u68af\u5ea6\uff0c\u628aaction_0/3\u5b66\u6210\u201c\u9ad8\u4ef7\u503c\u76f4\u884c\u76f8\u4f4d\u201d\uff0c\u5728\u6a21\u677fC\u4e0a90%\u65f6\u95f4\u8bef\u9009\u5168\u7ea2\u76f8\u4f4d\u3002\u56e0\u6b64\u8bad\u7ec3\u6309\u6a21\u677f\u52a0\u6743\u91c7\u6837\uff08A:0.45/B:0.15/C:0.20/D:0.10/E:0.10\uff09\uff0c\u6a21\u677fC\u53cc\u500d\u52a0\u6743\u3002', False),
    ])[1]

    # 3.1.5
    ref = add_heading_after(doc, ref, '3.1.5 \u57fa\u7ebf\u7b97\u6cd5\u5b9e\u73b0', 3)[1]
    ref = add_bullet_after(doc, ref, 'Fixed-Time\uff08\u771f\u5b9e\u5b9a\u5468\u671f\uff09\uff1a\u8bfb\u53d6\u771f\u5b9e\u914d\u65f6\u65b9\u6848\u5b89\u88c5\u4e3aSUMO\u4fe1\u53f7\u7a0b\u5e8f\uff0c\u73af\u5883\u6b65\u8fdb\u4e0d\u505a\u76f8\u4f4d\u8986\u76d6\uff08\u54e8\u5175\u52a8\u4f5c-1\uff09\uff0c\u4fdd\u8bc1\u201c\u771f\u5b9e\u5b9a\u5468\u671f\u57fa\u7ebf\u201d\u800c\u975e\u7406\u60f3\u5316\u914d\u65f6\u3002')[1]
    ref = add_bullet_after(doc, ref, 'Max-Pressure\u611f\u5e94\u63a7\u5236\uff1a\u9009\u62e9\u80fd\u91ca\u653e\u6700\u5927\u6392\u961f\u538b\u529b\u7684\u76f8\u4f4d\uff08NS\u538b\u529b=queue[N]+queue[S]\uff0cEW\u538b\u529b=queue[E]+queue[W]\uff09\uff0c\u9075\u5b88\u6700\u5c0f\u7eff\u706f15s\u3002')[1]
    ref = add_bullet_after(doc, ref, 'Random\uff1a\u968f\u673a\u9009\u62e9\u76f8\u4f4d\uff080-3\uff09\uff0c\u4ec5\u4f5c\u4e0b\u9650\u53c2\u8003\u3002')[1]
    ref = add_bullet_after(doc, ref, '\u7b97\u6cd5\u63a5\u5165\u9002\u914d\u5668\uff1a\u6a21\u578b\u6ce8\u518c\u8868+\u57fa\u7ebf\u5b9e\u73b0\u7684\u53ef\u63d2\u62d4\u7ed3\u6784\uff0c\u652f\u6301\u4e0d\u540c\u7b97\u6cd5\u63a5\u5165\u5e73\u53f0\u8fd0\u884c\u4e0e\u6d4b\u8bd5\u3002')[1]

    # === 3.2 ===
    ref = add_heading_after(doc, ref, '3.2 \u6a21\u578b\u8f7b\u91cf\u5316\u4e0e\u4e91-\u8fb9-\u7aef\u90e8\u7f72', 2)[1]

    # 3.2.1
    ref = add_heading_after(doc, ref, '3.2.1 \u8fb9\u7f18DQN\u6a21\u578b\u8f7b\u91cf\u5316', 3)[1]
    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u8f7b\u91cf\u5316\u94fe\u8def\uff1a', True),
        ('\u6b63\u5f0fSB3\u6559\u5e08\uff08zip\u7ea6121KB\uff09\u2192 TorchScript \u2192 ONNX\uff08opset 17\uff0c\u52a8\u6001batch\uff0c\u8f93\u5165float32[batch,26]\uff0c\u8f93\u51fafloat32[batch,4]\uff09\u2192 \u4f53\u79ef25,742B\uff08\u7ea625.14KB\uff0c\u8f83\u6559\u5e08\u51cf\u5c11\u7ea679%\uff09\u3002\u5bfc\u51fa\u4e0e\u6559\u5e08\u6743\u91cd\u7cbe\u786e\u590d\u5236\uff0c\u4fdd\u6301shared-dqn-26x4-v1\u5951\u7ea6\u4e0e\u7edd\u5bf9\u52a8\u4f5c\u63a9\u7801\u8bed\u4e49\u3002', False),
    ])[1]

    img = os.path.join(c, 'fig3_4_lightweighting.png')
    if os.path.exists(img):
        ref = add_image_after(doc, ref, img, 5.5, '\u56fe3-7 DQN\u6a21\u578b\u8f7b\u91cf\u5316\u5bfc\u51fa\u4e0e\u9a8c\u8bc1\u94fe\u8def')[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u4fdd\u771f\u9a8c\u8bc1\uff08\u90e8\u7f72\u95e8\u69db\uff09\uff1a', True),
        ('\u4ee5\u771f\u5b9eSUMO\u72b6\u6001\u4e09\u573a\u666f\u00d78\u4ee3\u8868\u8def\u53e3\uff08J01/J05/J10/J15/J20/J21/J25/J30\uff09\u00d7\u6bcf\u8def\u53e3\u8fde\u7eed120\u4e2a\u51b3\u7b56\u72b6\u6001 = 2,880\u6761\u89c2\u6d4b\u8fdb\u884c\u9a8c\u8bc1\uff0cFP32 ONNX\u4e0e\u6559\u5e08\u52a8\u4f5c\u4e00\u81f4\u7387100%\uff08\u9a8c\u8bc1\u7ed3\u679c\u5df2\u767b\u8bb0\u4e3a\u90e8\u7f72\u9a8c\u6536\u4f9d\u636e\uff09\u3002\u4e0d\u4ee5\u79bb\u7ebf\u968f\u673a\u72b6\u6001\u4e00\u81f4\u7387\u4ee3\u66ff\u771f\u5b9e\u72b6\u6001\u9a8c\u8bc1\u3002', False),
    ])[1]

    ref = add_table_after(doc, ref,
        ['\u6a21\u578b', '\u5355\u8def\u53e3mean', '\u5355\u8def\u53e3P95', '30\u8def\u53e3\u6279\u91cfmean', '30\u8def\u53e3\u6279\u91cfP95'],
        [
            ['\u65e9\u9ad8\u5cf0 FP32 ONNX', '0.022 ms', '0.028 ms', '0.029 ms', '0.048 ms'],
            ['\u665a\u9ad8\u5cf0 FP32 ONNX', '0.023 ms', '0.042 ms', '0.031 ms', '0.053 ms'],
        ]
    )[1]

    img = os.path.join(c, 'fig3_9_inference_performance.png')
    if os.path.exists(img):
        ref = add_image_after(doc, ref, img, 5.5, '\u56fe3-8 ONNX\u8fb9\u7f18\u63a8\u7406\u6027\u80fd\u57fa\u51c6')[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u6d88\u878d\u4e0e\u8d1f\u9762\u53d1\u73b0\uff1a', True),
        ('\u52a8\u6001INT8\uff08\u7b2c\u4e00\u9690\u85cf\u5c42\u901a\u9053\u52a8\u6001\u91cf\u5316\uff0c\u51b3\u7b56\u5934\u4fdd\u6301FP32\uff09\uff1a\u79bb\u7ebf10,000\u6761\u72b6\u6001\u4e00\u81f4\u738799.3%\uff0c\u4f46\u771f\u5b9eSUMO\u8f68\u8ff9\u4e0a\u964d\u4e3a\u65e9\u9ad8\u5cf084.38%/ \u665a\u9ad8\u5cf093.23%/ \u5e73\u5cf092.60%\uff0c\u5224\u5b9a\u4e3a\u5b9e\u9a8c\u5931\u8d25\u3002\u7ed3\u6784\u5316\u526a\u679d\uff0864\u00d764\u219256\u00d756\uff09+\u84b8\u998f\uff1a\u526a\u679dFP32\u79bb\u7ebf\u52a8\u4f5c\u4e00\u81f4\u7387\u7ea696.7%\uff0c\u4f5c\u4e3a\u5019\u9009/\u6d88\u878d\u4ea7\u7269\u4fdd\u7559\u3002\u8f7b\u91cf\u5316\u624b\u6bb5\u5fc5\u987b\u9010\u4efb\u52a1\u5b9e\u6d4b\u9a8c\u8bc1------\u91cf\u5316/\u526a\u679d\u5728\u201c\u7406\u60f3\u72b6\u6001\u8868\u73b0\u597d\u3001\u771f\u5b9e\u90e8\u7f72\u5931\u6548\u201d\u7684\u73b0\u8c61\uff0c\u6b63\u662f\u8d5b\u9898\u70b9\u540d\u7684\u884c\u4e1a\u75db\u70b9\u3002', False),
    ])[1]

    # 3.2.2
    ref = add_heading_after(doc, ref, '3.2.2 \u5bb9\u5668\u5316\u90e8\u7f72', 3)[1]
    ref = add_para_after(doc, ref, '\u5bb9\u5668\u5316\u65b9\u6848\u5c06SUMO\u3001TraCI\u7684Python\u4f9d\u8d56\u3001FastAPI\u548cONNX Runtime\u5b89\u88c5\u4e8e\u540c\u4e00\u53ef\u590d\u73b0\u8fd0\u884c\u65f6\u955c\u50cf\uff1b\u6a21\u578b\u76ee\u5f55\u4e0e\u8def\u7f51\u76ee\u5f55\u901a\u8fc7\u53ea\u8bfb\u5377\u6302\u8f7d\uff0c\u907f\u514d\u8fd0\u884c\u65f6\u8986\u76d6\u4ea4\u4ed8\u7269\u3002\u8fb9\u7f18\u63a8\u7406\u670d\u52a1\u5728\u72ec\u7acb\u7aef\u53e3\u66b4\u9732\u5065\u5eb7\u68c0\u67e5\u4e0e\u63a8\u7406\u63a5\u53e3\uff1bAPI\u670d\u52a1\u5728\u4e1a\u52a1\u7aef\u53e3\u66b4\u9732\u5168\u90e8\u4e1a\u52a1\u63a5\u53e3\uff0c\u5e76\u4f9d\u8d56\u8fb9\u7f18\u670d\u52a1\u7684\u5065\u5eb7\u68c0\u67e5\u3002')[1]

    img = os.path.join(c, 'fig3_10_container_architecture.png')
    if os.path.exists(img):
        ref = add_image_after(doc, ref, img, 5.5, '\u56fe3-9 Docker\u5bb9\u5668\u5316\u90e8\u7f72\u67b6\u6784')[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u9a8c\u6536\u7ed3\u679c\uff082026-08-23\uff09\uff1a', True),
        ('edge + api\u53cc\u5bb9\u5668\u4e00\u952e\u542f\u52a8\uff0c\u955c\u50cf394 MiB\uff0c\u95ed\u73af\u5192\u70df\u6d4b\u8bd5\u5168PASS\uff08\u5065\u5eb7\u68c0\u67e5\u3001\u72b6\u6001\u67e5\u8be2\u3001\u6279\u91cf\u63a8\u7406\u3001\u52a8\u4f5c\u6267\u884c\u5168\u94fe\u8def\u901a\u8fc7\uff09\u3002API\u7684\u6279\u91cf\u63a8\u7406\u80fd\u529b\u5c06\u5f53\u524d\u4f1a\u8bdd\u7684660\u7ef4\u72b6\u6001\u62c6\u5206\u4e3a30\u00d722\uff0c\u518d\u628a30\u00d74\u63a9\u7801\u548c\u6a21\u578bID\u53d1\u9001\u81f3\u5bb9\u5668\u7f51\u7edc\u5185\u7684ONNX\u670d\u52a1\uff0c\u8fd4\u56de\u768430\u4e2a\u52a8\u4f5c\u4ecd\u9700\u7ecf\u8fc7\u670d\u52a1\u7aef\u5b89\u5168\u7ea6\u675f\u540e\u5199\u5165SUMO\u3002', False),
    ])[1]

    # 3.2.3
    ref = add_heading_after(doc, ref, '3.2.3 LLM\u4e91\u8111\u51b3\u7b56\u652f\u6301\uff08\u8d5b\u9053C\uff09', 3)[1]
    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u53cc\u6a21\u578b\u5206\u5c42\u67b6\u6784\uff1a', True),
        ('LLM\u4e0d\u53c2\u4e0e\u5b9e\u65f6\u4fe1\u53f7\u63a7\u5236\uff08\u6beb\u79d2\u7ea7\u54cd\u5e94\u65e0\u6cd5\u4fdd\u8bc1\u3001\u53ef\u9760\u6027\u98ce\u9669\u9ad8\uff09\uff0c\u800c\u662f\u627f\u62c5\u201c\u57ce\u5e02\u5927\u8111\u201d\u7684\u6162\u5468\u671f\u51b3\u7b56\u652f\u6301\u89d2\u8272\u3002\u8fb9\u7f18DQN\u627f\u62c55\u79d2\u5468\u671f\u768430\u8def\u53e3\u5b9e\u65f6\u4fe1\u53f7\u63a7\u5236\uff1b\u4e91\u7aefLoRA\u5fae\u8c03LLM\u627f\u62c5\u6bcf2-5\u5206\u949f\u7684\u4ea4\u901a\u4e8b\u4ef6\u8bc6\u522b\u4e0e\u4e2d\u6587\u7ba1\u63a7\u5efa\u8bae\u751f\u6210\u3002', False),
    ])[1]

    ref = add_table_after(doc, ref,
        ['\u5c42\u7ea7', '\u6a21\u578b', '\u5468\u671f', '\u804c\u8d23'],
        [
            ['\u8fb9\u7f18', 'FP32 ONNX DQN\uff0825KB, 0.022ms/\u8def\u53e3\uff09', '5s', '\u5b9e\u65f6\u4fe1\u53f7\u63a7\u5236\uff0830\u8def\u53e3\u6279\u91cf\uff09'],
            ['\u4e91\u7aef', '\u5fae\u8c03Qwen2.5-0.5B + llama.cpp\uff08f32 GGUF\uff09', '\u6bcf2-5\u5206\u949f', '\u4ea4\u901a\u4e8b\u4ef6\u8bc6\u522b + \u4e2d\u6587\u7ba1\u63a7\u5efa\u8bae'],
        ]
    )[1]

    img = os.path.join(c, 'fig3_8_llm_pipeline.png')
    if os.path.exists(img):
        ref = add_image_after(doc, ref, img, 5.5, '\u56fe3-10 LLM\u4e91\u8111\u6570\u636e\u5904\u7406\u4e0e\u5fae\u8c03\u6d41\u6c34\u7ebf')[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u6570\u636e\u5904\u7406\uff1a', True),
        ('SUMO 30\u8def\u53e3\u771f\u5b9e\u573a\u666f\u5728Fixed-Time\u4e0b\u8fd0\u884c\uff0c\u6bcf5s\u63d0\u53d6\u8def\u53e3\u539f\u59cb\u7279\u5f81\uff08\u6392\u961f\u8f86\u6570/\u5e73\u5747\u7b49\u5f85/\u5360\u6709\u7387/\u5747\u901f/\u76f8\u4f4d\uff09\uff0c\u630930s\u7a97\u53e3\u7531\u89c4\u5219oracle\u81ea\u52a8\u6807\u6ce8\u56db\u7c7b\u4e8b\u4ef6\uff1a\u4e8b\u4ef6\uff08\u6270\u52a8\u6ce8\u5165\u771f\u503c\uff09> \u6ea2\u51fa > \u62e5\u5835 > \u6b63\u5e38\uff0c\u5e76\u751f\u6210\u76f8\u4f4d\u611f\u77e5\u7684\u4e2d\u6587\u7ba1\u63a7\u5efa\u8bae\u3002\u5171\u751f\u6210136,440\u6761\u53bb\u91cd\u6837\u672c\uff0c\u6309\u7c7b\u522b\u5e73\u8861\u62bd\u68376,531\u6761\u6784\u6210\u5fae\u8c03\u96c6\u3002', False),
    ])[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u6a21\u578b\u5fae\u8c03\uff08LoRA\uff09\uff1a', True),
        ('\u57fa\u5ea7Qwen2.5-0.5B-Instruct\uff08\u7ea61GB\uff0c8GB\u663e\u5b58\u53ef\u8bad\uff09\uff0cLoRA\uff08r=16, \u03b1=32\uff09\u53ea\u8bad\u7ec3\u7ea61%\u53c2\u6570\u3002\u4efb\u52a1\u683c\u5f0f\uff1a\u8f93\u5165\u8def\u53e3\u72b6\u6001\u7a97\u53e3\u6587\u672c\uff0c\u8f93\u51fa\u4e8b\u4ef6/\u7f6e\u4fe1\u5ea6/\u4e2d\u6587\u5efa\u8bae\u7684JSON\u3002\u8bad\u7ec33 epochs\u540etrain_loss\u22480.025\uff0c\u9002\u914d\u5668\u4ec535MB\u3002', False),
    ])[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u6a21\u578b\u8f6c\u6362\u4e0e\u8f7b\u91cf\u5316\u9a8c\u8bc1\uff1a', True),
        ('\u5408\u5e76LoRA \u2192 GGUF\u5bfc\u51fa \u2192 \u91cf\u5316\u5bf9\u6bd4\uff08100\u6761\u5747\u8861\u9a8c\u8bc1\u96c6\uff0c\u7ecf\u63a8\u7406\u670d\u52a1\u5b9e\u6d4b\uff09\uff1a', False),
    ])[1]

    ref = add_table_after(doc, ref,
        ['\u6a21\u578b\u5f62\u6001', '\u4f53\u79ef', '\u4e8b\u4ef6\u51c6\u786e\u7387', '\u4e8b\u4ef6\u53ec\u56de', '\u5355\u6761\u5ef6\u8fdf'],
        [
            ['\u57fa\u5ea7bf16\uff08\u5fae\u8c03\u524d\uff09', '~1 GB', '25.0%', '0%', '-'],
            ['\u5fae\u8c03\u540ebf16\uff08HF\u63a8\u7406\uff09', '~1 GB', '99.5%', '100%', '~6.1 s'],
            ['\u5fae\u8c03\u540ef32 GGUF\uff08\u6b63\u5f0f\u90e8\u7f72\uff09', '1.98 GB', '100.0%', '100%', '~5.0 s (P95 6.2s)'],
            ['Q6_K', '506 MB', '66.0%', '4%', '~3.2 s'],
            ['Q4_K_M', '379 MB', '62.0%', '0%', '~3.2 s'],
        ]
    )[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u91cf\u5316\u9002\u7528\u6027\u7ed3\u8bba\uff08\u6709\u4ef7\u503c\u7684\u8d1f\u9762\u53d1\u73b0\uff09\uff1a', True),
        ('INT4/INT6/INT8\u91cf\u5316\u5728\u672c\u4efb\u52a1\u4e0d\u53ef\u7528------0.5B\u5c0f\u6a21\u578b\u7684\u201c\u4e8b\u4ef6\u201d\u5224\u522b\u4f9d\u8d56\u201c\u4f4e\u5747\u901f\u201d\u7b49\u7cbe\u7ec6\u6570\u503c\u4fe1\u53f7\uff0c\u91cf\u5316\u540e\u4e8b\u4ef6\u53ec\u56de\u4ece100%\u6389\u52300-4%\uff1bllama.cpp\u7684f16\u8ba1\u7b97\u540c\u6837\u635f\u5931\u7cbe\u5ea6\uff0866%\uff09\uff0c\u5fc5\u987bf32\u8ba1\u7b97\u3002\u6b63\u5f0f\u90e8\u7f72f32 GGUF\uff081.98 GB\uff09\uff0c\u5bf9\u6bd4\u901a\u5e387B\u6a21\u578b\uff0814 GB+\uff0cQ4\u540e\u4ecd4.5 GB\uff09\u4f53\u79ef\u7ea61/7\uff0c\u4f9d\u7136\u6ee1\u8db3\u8f7b\u91cf\u5316\u53d9\u4e8b\u3002', False),
    ])[1]

    # 3.2.4
    ref = add_heading_after(doc, ref, '3.2.4 \u53cc\u6a21\u578b\u5206\u5c42\u67b6\u6784\u4e0e\u63a5\u53e3', 3)[1]
    ref = add_para_after(doc, ref, '\u8fb9\u7f18\u6beb\u79d2\u7ea7\u63a7\u5236\uff08DQN ONNX\uff09+ \u4e91\u7aef\u6162\u5468\u671f\u51b3\u7b56\uff08LLM\uff09\u901a\u8fc7\u7edf\u4e00\u7684REST\u89c4\u8303\u63a5\u5165\u7cfb\u7edf\uff1a\u8fb9\u7f18\u63a8\u7406\u63a5\u53e3\u4e0e\u4e91\u8111\u5206\u6790\u63a5\u53e3\u5171\u4eab\u540c\u4e00\u5957\u9519\u8bef\u7801\u4f53\u7cfb\u4e0e\u9274\u6743\u8fb9\u754c\uff0c\u4e91\u8111\u7f51\u5173\u670d\u52a1\u9694\u79bb\u63a8\u7406\u670d\u52a1\u7684\u5b9e\u73b0\u7ec6\u8282\u3002\u53ef\u9009\u6269\u5c55\uff08\u5217\u4e3a\u5c55\u671b\uff09\uff1aLLM\u5efa\u8bae \u2192 DQN\u63a9\u7801\u95ed\u73af\u5e72\u9884\uff08SUMO A/B\u5bf9\u6bd4\uff09\u3002')[1]

    # === 3.3 ===
    ref = add_heading_after(doc, ref, '3.3 \u9ad8\u4fdd\u771f\u4eff\u771f\u73af\u5883\u6784\u5efa', 2)[1]

    # 3.3.1
    ref = add_heading_after(doc, ref, '3.3.1 \u8def\u7f51\u8bbe\u8ba1\u4e0e\u6784\u5efa', 3)[1]
    ref = add_para_after(doc, ref, '\u8def\u7f51\u914d\u7f6e\u5305\u542b30\u8def\u53e3\u8def\u7f51\u6587\u4ef6\u4e0e\u4eff\u771f\u914d\u7f6e\u6587\u4ef6\uff1b\u7edf\u4e00\u8def\u53e3\u987a\u5e8f\u5728\u5168\u5c40\u914d\u7f6e\u4e2d\u5b9a\u4e49\u4e3aJ01-J30\uff0cSUMO\u3001API\u3001Unity\u56db\u5c42\u4e00\u81f4\u300230\u8def\u53e36\u00d75\u7f51\u683c\u5e03\u5c40\uff0c\u8fb9\u754c\u8282\u70b9\u4e3apriority\u3001\u5185\u90e8\u8def\u53e3\u4e3atraffic_light\uff1b\u53cc\u54113\u8f66\u9053\u3001\u9650\u901f50km/h\uff0813.89 m/s\uff09\uff1b\u8def\u53e3\u95f4\u8ddd\u77ed\uff0c\u7b26\u5408\u201c\u7a84\u8def\u5bc6\u7f51\u201d\u8fd1\u8ddd\u8def\u53e3\u3001\u4e0a\u6e38\u6392\u961f\u6613\u56de\u5835\u7684\u7279\u5f81\u3002')[1]

    img = os.path.join(c, 'fig3_1_road_network.png')
    if os.path.exists(img):
        ref = add_image_after(doc, ref, img, 5.5, '\u56fe3-11 30\u8def\u53e3\u8def\u7f51\u62d3\u6251\u793a\u610f\u56fe')[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u751f\u6210\u4e0e\u9a8c\u8bc1\u6d41\u7a0b\uff1a', True),
        ('SUMO netconvert\u751f\u6210 \u2192 \u6821\u9a8cJ01-J30\u5168\u90e8\u4e3atraffic_light\u7c7b\u578b\u3001\u6bcf\u8def\u53e34\u4e2a\u6709\u6548\u52a8\u4f5c\u3001N/S/E/W\u6620\u5c04\u5b8c\u6574\u3002\u8def\u7f51\u5b9e\u6d4b\u5b58\u57285\u79cdrl4\u76f8\u4f4d\u6a21\u677f\uff08A:20/B:4/C:3/D:2/E:1\uff09\uff0c\u6a21\u677f\u95f4\u52a8\u4f5c\u8bed\u4e49\u4e0d\u540c------\u8fd9\u662f\u5171\u4eab\u7b56\u7565\u8bbe\u8ba1\u4e0e\u8bc4\u4f30\u5206\u6790\u7684\u57fa\u7840\u4e8b\u5b9e\u3002', False),
    ])[1]

    # 3.3.2
    ref = add_heading_after(doc, ref, '3.3.2 \u4fe1\u53f7\u65b9\u6848\u89c4\u8303\u5316\u4e0e\u5b89\u5168\u4f18\u5316', 3)[1]
    ref = add_bullet_after(doc, ref, '\u539f\u59cb\u8def\u7f51\u76f8\u4f4d1\u548c\u76f8\u4f4d3\u4e3a\u9ec4\u706f\uff0c\u4e0d\u80fd\u4f5c\u4e3a\u6709\u6548RL\u52a8\u4f5c \u2192 \u89c4\u8303\u4e3a\u6bcf\u8def\u53e34\u4e2a\u53ef\u63a7\u76f8\u4f4d\u3002')[1]
    ref = add_bullet_after(doc, ref, '\u5c06\u53f3\u8f6c\u548c\u6389\u5934\u8fde\u63a5\u6539\u4e3a\u8ba9\u884c\u7eff\u706fg\uff0c\u6d88\u9664SUMO\u7684Unsafe green\u51b2\u7a81\u3002')[1]
    ref = add_bullet_after(doc, ref, '\u590d\u9a8c\u7ed3\u679c\uff1a1,527\u8f86\u5230\u8fbe\uff0c\u5e73\u5747\u7b49\u5f850.94s\uff0c\u5e73\u5747\u884c\u7a0b58.60s\uff0c0\u78b0\u649e\uff0c0\u4f20\u9001\u3002')[1]
    ref = add_bullet_after(doc, ref, '\u5b89\u5168\u7ea6\u675f\uff1a\u6bcf\u8def\u53e34\u4e2a\u53ef\u63a7\u76f8\u4f4d\uff0c\u63a7\u5236\u5668\u540c\u65f6\u6267\u884c\u6700\u5c0f\u7eff\u706f15s\u4e0e\u9ec4\u706f\u8fc7\u6e213s\u3002')[1]

    # 3.3.3
    ref = add_heading_after(doc, ref, '3.3.3 \u591a\u65f6\u6bb5\u771f\u5b9e\u4ea4\u901a\u6d41\u914d\u7f6e', 3)[1]
    ref = add_para_after(doc, ref, '\u4e09\u4e2a\u573a\u666f\u5747\u4f7f\u75287,200s\u65f6\u95f4\u7a97\uff0c\u8f66\u8f86\u89c4\u6a21\u548c\u9700\u6c42\u56e0\u5b50\u4e0d\u540c\u3002\u9700\u6c42\u56e0\u5b50\u6309\u771f\u5b9e\u5b9a\u5468\u671f\u57fa\u7ebf\u5bb9\u91cf\u6807\u5b9a\uff0c\u4fdd\u8bc1\u57fa\u7ebf\u201c\u901a\u800c\u4e0d\u5835\u201d\uff0c\u5bf9\u6bd4\u5b9e\u9a8c\u5728\u76f8\u540c\u8d1f\u8377\u4e0b\u8fdb\u884c\u3002')[1]

    ref = add_table_after(doc, ref,
        ['\u573a\u666f', '\u8f66\u8f86\u6570', '\u65f6\u95f4\u7a97', '\u9700\u6c42\u56e0\u5b50'],
        [
            ['\u65e9\u9ad8\u5cf0', '51,868', '7,200s', '0.48'],
            ['\u5e73\u5cf0', '44,947', '7,200s', '0.60'],
            ['\u665a\u9ad8\u5cf0', '50,296', '7,200s', '0.42'],
        ]
    )[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u68c0\u6d4b\u5668\u914d\u7f6e\uff1a', True),
        ('\u73af\u5f62\u68c0\u6d4b\u5668\uff08e1Detector\uff09\u91c7\u96c6\u6392\u961f\u957f\u5ea6\u3001\u5360\u6709\u7387\uff1b\u8fdb\u51fa\u68c0\u6d4b\u5668\uff08entryExitDetector\uff09\u7edf\u8ba1\u901a\u8fc7\u8f66\u8f86\u6570\u3001\u884c\u7a0b\u65f6\u95f4\u3002', False),
    ])[1]

    # 3.3.4
    ref = add_heading_after(doc, ref, '3.3.4 \u6270\u52a8\u4e8b\u4ef6\u6ce8\u5165\u4e0e\u573a\u666f\u6269\u5c55', 3)[1]
    ref = add_para_after(doc, ref, '\u65bd\u5de5\u5360\u9053\u573a\u666f\u7528\u4e8eLLM\u4e8b\u4ef6\u8bc6\u522b\u6570\u636e\u751f\u6210\u4e0e\u6f14\u793a\u3002\u6270\u52a8\u89c4\u683c\u5b9a\u4e49\u4e3aJ25\u5317\u5411\u65bd\u5de5\u5360\u9053\uff0c\u7a97\u53e360-300s\uff0c\u9650\u901f5 m/s\u3002\u53c2\u6570\u5316\u914d\u7f6e\u652f\u6301\u5927\u578b\u6d3b\u52a8\u7b49\u6270\u52a8\u4e8b\u4ef6\u6ce8\u5165\uff0c\u4e3a\u7b97\u6cd5\u6d4b\u8bd5\u63d0\u4f9b\u903c\u8fd1\u771f\u5b9e\u7684\u201c\u6570\u5b57\u9776\u573a\u201d\u3002')[1]

    # 3.3.5
    ref = add_heading_after(doc, ref, '3.3.5 \u73af\u5883\u9a8c\u6536\u4e0e\u9c81\u68d2\u6027\u9a8c\u8bc1', 3)[1]
    ref = add_bullet_after(doc, ref, '\u9a8c\u6536\u95e8\u69db\uff1aTraCI\u5fc5\u987b\u67e5\u8be2\u5230\u6070\u597d30\u4e2a\u4fe1\u53f7\u706f\uff0c\u4e14\u53ef\u6620\u5c04\u4e3aJ01-J30\u3002')[1]
    ref = add_bullet_after(doc, ref, '\u9c81\u68d2\u6027\u6d4b\u8bd5\uff1aJ01\u968f\u673a\u52a8\u4f5c\u6d4b\u8bd5100\u6b65\uff08\u76f8\u4f4d\u5207\u6362/\u6700\u5c0f\u7eff\u706f/\u9ec4\u706f\u8fc7\u6e21\u5747\u6b63\u5e38\uff09\u3002')[1]
    ref = add_bullet_after(doc, ref, '\u771f\u5b9e\u5b9a\u5468\u671f\u57fa\u7ebf7,200s\u5168\u901a\u65e0\u6b7b\u9501\u3002')[1]

    # === 3.4 ===
    ref = add_heading_after(doc, ref, '3.4 \u5b9e\u9a8c\u9a8c\u8bc1\u4e0e\u6027\u80fd\u8bc4\u4f30', 2)[1]

    # 3.4.1
    ref = add_heading_after(doc, ref, '3.4.1 \u8bc4\u4f30\u65b9\u6848\u8bbe\u8ba1', 3)[1]
    ref = add_table_after(doc, ref,
        ['\u7ef4\u5ea6', '\u53d6\u503c'],
        [
            ['\u63a7\u5236\u7b56\u7565', 'Fixed-Time\uff08\u771f\u5b9e\u914d\u65f6\uff09\u3001Max-Pressure\u3001Random\u3001\u5171\u4eab\u63a9\u7801DQN'],
            ['\u573a\u666f', '\u65e9\u9ad8\u5cf0\u3001\u5e73\u5cf0\u3001\u665a\u9ad8\u5cf0\uff08\u540c\u8d1f\u8377\u5bf9\u6bd4\uff09'],
            ['\u8bc4\u4f30\u53e3\u5f84', '8\u4ee3\u8868\u8def\u53e3\u00d75\u56de\u5408\u00d7720\u6b65\uff1b30\u8def\u53e3\u5168\u91cf\u00d73\u56de\u5408\u00d7720\u6b65'],
            ['\u6307\u6807\u96c6', 'Mobility\uff08\u6392\u961f/\u7b49\u5f85/\u884c\u7a0b\u65f6\u95f4/\u541e\u5410\u91cf\uff09\u3001Environment\uff08\u71c3\u6cb9/CO2\uff09\u3001Safety\uff08\u505c\u8f66\u6b21\u6570/\u65f6\u95f4\u635f\u5931/\u78b0\u649e\uff09'],
        ]
    )[1]

    ref = add_para_after(doc, ref, '8\u8def\u53e3\u4ee3\u8868\u6309\u6a21\u677f\u8986\u76d6\u9009\u53d6\uff08A/B/C/D/E\u5404\u542b\u4ee3\u8868\uff09\uff0c\u62a5\u544a\u4e2d\u9700\u660e\u786e\u53e3\u5f84\u5dee\u5f02\u3002\u6307\u6807\u91c7\u96c6\u7531\u6307\u6807\u91c7\u96c6\u6a21\u5757\u7edf\u4e00\u5b8c\u6210\uff0c\u5e76\u5c06\u6bcf\u4e00\u7b56\u7565\u3001\u573a\u666f\u3001\u968f\u673a\u79cd\u5b50\u3001\u6a21\u578b\u54c8\u5e0c\u3001\u8def\u7f51\u54c8\u5e0c\u3001SUMO\u7248\u672c\u5199\u5165\u7ed3\u679c\u5143\u6570\u636e\u3002')[1]

    # 3.4.2
    ref = add_heading_after(doc, ref, '3.4.2 \u8bad\u7ec3\u8fc7\u7a0b\u5206\u6790', 3)[1]
    ref = add_bullet_after(doc, ref, '\u8bad\u7ec3\u8282\u70b9\uff1a\u65e9\u671f30\u6b65GPU/SUMO\u94fe\u8def\u9a8c\u8bc1\uff08\u5e73\u5747\u5956\u52b1-167.24\uff09\uff1b5,000\u6b65\u521d\u6b65\u6536\u655b\uff08-114.99\uff09\uff1b10,000\u6b65J01\u5bf9\u6bd4\u5b9e\u9a8c\u6a21\u578b\uff08-43.09\uff09\uff1b\u6b63\u5f0f\u6a21\u578b1,000,000\u6b65\u3002')[1]
    ref = add_bullet_after(doc, ref, '\u8bad\u7ec3\u8fd0\u884c\u7edf\u8ba1\uff1a\u65e9\u9ad8\u5cf0\u4e13\u75281M\u6b65\u6b63\u5f0f\u8bad\u7ec3\uff1b\u665a\u9ad8\u5cf0\u4e13\u75281M\u6b65\u6b63\u5f0f\u8bad\u7ec3\uff1b\u5e73\u5cf0\u4e24\u6b21\u75c5\u6001\u8bad\u7ec3\uff08\u5f52\u6863\uff09\uff1b\u8d85\u53c2\u6570\u626b\u53c26\u7ec4\u3002')[1]
    ref = add_bullet_after(doc, ref, '\u8bad\u7ec3\u7edf\u8ba1\u6570\u636e\uff1a\u6b63\u5f0f\u65e9\u9ad8\u5cf0\u6a21\u578b\u603b\u53c2\u6570\u91cf11,784\uff0c\u6279\u5927\u5c0f256\uff0c\u5b66\u4e60\u73873e-4\uff0c\u5e73\u5747\u5956\u52b12,401.35\uff0c\u8017\u65f6\u7ea627,348s\u3002')[1]

    # 3.4.3
    ref = add_heading_after(doc, ref, '3.4.3 \u4e09\u573a\u666f\u5bf9\u6bd4\u5b9e\u9a8c', 3)[1]
    ref = add_para_after(doc, ref, '', bold_parts=[
        ('8\u8def\u53e3\u4ee3\u8868\u53e3\u5f84', True),
        ('\uff08\u63a9\u7801\u914d\u65b9\uff1a26\u7ef4\u89c2\u6d4b + Double-DQN + \u6a21\u677f\u5206\u5c42\u91c7\u6837\uff09\uff1a', False),
    ])[1]

    ref = add_table_after(doc, ref,
        ['\u573a\u666f', '\u6a21\u578b', 'reward \u0394%', 'waiting \u0394%', 'throughput \u0394%', '\u80dc/8'],
        [
            ['\u65e9\u9ad8\u5cf0', '\u65e9\u9ad8\u5cf0\u4e13\u75281M', '+13.7% (19948 vs 17537)', '+0.9%', '+0.3%', '5/8'],
            ['\u5e73\u5cf0', '\u665a\u9ad8\u5cf0\u6cdb\u53161M', '+5.4% (16299 vs 15468)', '+60.5% (\u52a3)', '-0.1%', '6/8'],
            ['\u665a\u9ad8\u5cf0', '\u665a\u9ad8\u5cf0\u4e13\u75281M', '+15.4% (18924 vs 16397)', '-2.1%', '+0.4%', '5/8'],
        ]
    )[1]

    img = os.path.join(c, 'fig3_5_three_scenarios.png')
    if os.path.exists(img):
        ref = add_image_after(doc, ref, img, 5.5, '\u56fe3-12 \u4e09\u573a\u666fDQN\u4e0eFixed-Time\u5bf9\u6bd4\uff088\u8def\u53e3\u4ee3\u8868\u53e3\u5f84\uff09')[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('30\u8def\u53e3\u5168\u91cf\u53e3\u5f84', True),
        ('\uff08\u00d73\u56de\u5408\u00d7720\u6b65\u00d72\u7b56\u7565\uff09\uff1a', False),
    ])[1]

    ref = add_table_after(doc, ref,
        ['\u573a\u666f', 'reward \u0394%', 'waiting \u0394%', '\u80dc/30'],
        [
            ['\u65e9\u9ad8\u5cf0', '+11.0% (79,367 vs 71,520)', '+3.4%', '20/30'],
            ['\u5e73\u5cf0', '-1.6% (63,010 vs 64,059, \u52a3)', '158,824 vs 6,031 (\u4f4e\u6d41\u91cf\u8def\u53e3\u7b49\u5f85\u5267\u589e)', '22/30'],
            ['\u665a\u9ad8\u5cf0', '+9.9% (76,175 vs 69,340)', '+14.1%', '20/30'],
        ]
    )[1]

    img = os.path.join(c, 'fig3_12_30_eval.png')
    if os.path.exists(img):
        ref = add_image_after(doc, ref, img, 5.0, '\u56fe3-13 30\u8def\u53e3\u5168\u91cf\u8bc4\u4f30\u7ed3\u679c')[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u6309\u6a21\u677f\u80dc\u8d25', True),
        ('\uff08DQN\u80dc\u8def\u53e3\u6570/\u6a21\u677f\u8def\u53e3\u6570\uff09\uff1a\u65e9\u9ad8\u5cf0\u6a21\u677fA 14/20\u3001B 3/4\u3001C 2/3\u3001D 0/2\u3001E 1/1\uff1b\u5e73\u5cf0A 14/20\u3001B 3/4\u3001C 2/3\u3001D 2/2\u3001E 1/1\uff1b\u665a\u9ad8\u5cf0A 13/20\u3001B 2/4\u3001C 2/3\u3001D 2/2\u3001E 1/1\u3002', False),
    ])[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u5e73\u5cf0\u75c5\u6839\u5206\u6790\uff08\u5982\u5b9e\u5448\u73b0\uff09\uff1a', True),
        ('\u5e73\u5cf0\u5168\u91cfreward -1.6%\u7684\u4e3b\u56e0\u662fJ16\uff08wait 68,384s vs 68s\uff09\u4e0eJ18\uff0881,943s vs 88s\uff09\u4e24\u4e2a\u4f4e\u6d41\u91cf\u8def\u53e3\uff0c\u5408\u8ba1\u8d21\u732e\u7ea615\u4e07\u79d2\u7b49\u5f85\u3002\u6839\u56e0\u5df2\u9a8c\u8bc1\uff1aDQN\u6bcf\u76f8\u4f4d\u6700\u5c0f15s\u7eff\u706f + \u9ec4\u706f\u8fc7\u6e21\u7684\u56fa\u5b9a\u5207\u6362\u5f00\u9500\u5728\u8f66\u5c11\u65f6\u5927\u91cf\u7a7a\u8f6c------\u8fd9\u662f\u673a\u5236\u6027\u5f31\u70b9\uff0c\u91cd\u8bad/\u6362\u79cd\u5b50\u65e0\u6cd5\u89e3\u51b3\u3002', False),
    ])[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u5b89\u5168\u53e3\u5f84\u8bf4\u660e\uff1a', True),
        ('8\u8def\u53e3\u8bc4\u4f30\u8bb0\u5f55\u5230DQN\u4fa7\u5c11\u91cf\u78b0\u649e\uff08\u65e9\u9ad8\u5cf05\u3001\u5e73\u5cf02\u3001\u665a\u9ad8\u5cf01\uff0cFixed-Time\u4e3a0\uff09\u3002', False),
    ])[1]

    # 3.4.4
    ref = add_heading_after(doc, ref, '3.4.4 \u8f7b\u91cf\u5316\u4e0e\u90e8\u7f72\u6027\u80fd\u9a8c\u8bc1', 3)[1]
    ref = add_table_after(doc, ref,
        ['\u6307\u6807', '\u8d5b\u9898\u76ee\u6807', '\u5b9e\u6d4b', '\u5224\u5b9a'],
        [
            ['\u6a21\u578b\u4f53\u79ef', '< 1 MB', '25.14 KB (FP32 ONNX)', '\u2705 \u8fdc\u8d85\u76ee\u6807'],
            ['\u5355\u8def\u53e3\u63a8\u7406\u5ef6\u8fdf', '< 5 ms', '0.022 ms (mean) / 0.028 ms (P95)', '\u2705 \u8fdc\u8d85\u76ee\u6807'],
            ['30\u8def\u53e3\u6279\u91cf\u5ef6\u8fdf', '< 500 ms', '0.029 ms (mean) / 0.048 ms (P95)', '\u2705 \u8fdc\u8d85\u76ee\u6807'],
            ['\u52a8\u4f5c\u9000\u5316', '\u2264 5%', '0% (\u771f\u5b9e\u72b6\u6001100%\u4e00\u81f4\u7387)', '\u2705 \u8fbe\u6807'],
        ]
    )[1]

    ref = add_bullet_after(doc, ref, 'INT8\u4ea7\u7269\u771f\u5b9e\u72b6\u6001\u4e00\u81f4\u738784-93%\uff0c\u526a\u679d\u4ea7\u7269\u79bb\u7ebf\u4e00\u81f4\u7387\u7ea697%\uff0c\u5747\u672a\u8fbe\u5230\u4e0e\u63a8\u8350ONNX\u76f8\u540c\u7684\u90e8\u7f72\u95e8\u69db\u3002')[1]
    ref = add_bullet_after(doc, ref, '\u5bb9\u5668\u5316\u9a8c\u6536\uff1aDocker\u955c\u50cf394 MiB\uff0cedge+api\u5065\u5eb7\u68c0\u67e5\u901a\u8fc7\uff0c\u95ed\u73af\u5192\u70df\u6d4b\u8bd5\u5168PASS\u3002')[1]

    # 3.4.5
    ref = add_heading_after(doc, ref, '3.4.5 LLM\u4e91\u8111\u8bc4\u4f30', 3)[1]
    ref = add_table_after(doc, ref,
        ['\u6307\u6807', '\u5b9e\u6d4b\u7ed3\u679c', '\u5224\u5b9a'],
        [
            ['\u4e8b\u4ef6\u8bc6\u522b\u51c6\u786e\u7387\uff08100\u6761\u5747\u8861\u9a8c\u8bc1\u96c6\uff09', '\u57fa\u5ea725% \u2192 \u5fae\u8c03\u540e99.5% \u2192 f32 GGUF\u90e8\u7f72100%', '\u2705'],
            ['JSON\u8f93\u51fa\u89e3\u6790\u7387', '100%', '\u2705'],
            ['\u5355\u6761\u5206\u6790\u5ef6\u8fdf', '~5.0s (P95 6.2s, GPU, \u4e91\u8111\u6162\u5468\u671f)', '\u2705'],
            ['\u91cf\u5316\u9002\u7528\u6027', 'Q4_K_M 62% / Q6_K 66% (\u4e8b\u4ef6\u53ec\u56de0-4%) \u2192 \u91cf\u5316\u4e0d\u53ef\u7528, \u6b63\u5f0ff32', '\u26a0\ufe0f \u8d1f\u9762\u53d1\u73b0'],
            ['\u90e8\u7f72\u63a5\u53e3', '\u4e91\u8111\u5206\u6790\u63a5\u53e3\u5168\u94fe\u8def\u9a8c\u8bc1\u901a\u8fc7\uff08\u771f\u5b9e\u4e8b\u4ef6\u6837\u672c\u6b63\u786e\u8bc6\u522b\uff09', '\u2705'],
        ]
    )[1]

    # 3.4.6
    ref = add_heading_after(doc, ref, '3.4.6 \u76ee\u6807\u8fbe\u6210\u60c5\u51b5', 3)[1]
    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u7b2c1.4\u8282\u5de5\u7a0b\u76ee\u6807\u9010\u9879\u6838\u5bf9\uff1a', True),
        ('\u8def\u7f51\u89c4\u6a21\uff0830\u8def\u53e3\u2705\uff09\u3001\u72b6\u6001\u5951\u7ea6\uff08660\u7ef4\u2705\uff09\u3001\u51b3\u7b56\u7ea6\u675f\uff0826\u7ef4\u63a9\u7801\u5951\u7ea6\u2705\uff09\u3001\u4f4e\u65f6\u5ef6\u90e8\u7f72\uff0825.14KB / \u4e00\u81f4\u7387100%\u2705\uff09\u3001\u6f14\u793a\u95ed\u73af\uff08\u4e09\u573a\u666fUnity\u95ed\u73af\u2705\uff09\u3002', False),
    ])[1]

    ref = add_para_after(doc, ref, '', bold_parts=[
        ('\u5c1a\u7f3a\u7684\u6b63\u5f0f\u8bc4\u4f30', True),
        ('\uff08\u5982\u65f6\u95f4\u5141\u8bb8\u8865\u9f50\uff09\uff1a\u56db\u7b56\u7565\uff08\u542b\u72ec\u7acbDQN\u3001Max-Pressure\uff09\u5728\u76f8\u540c30\u8def\u53e3\u4e09\u573a\u666f\u3001\u540c\u4e00\u79cd\u5b50\u7ec4\u4e0a\u7684\u5b8c\u6574\u5bf9\u6bd4\uff1b\u663e\u8457\u6027\u68c0\u9a8c\u4e0e\u7f6e\u4fe1\u533a\u95f4\uff1b\u5b89\u5168\u6307\u6807\u540c\u53e3\u5f84\u7edf\u8ba1\u3002\u672a\u8865\u9f50\u524d\uff0c\u672c\u6587\u4e0d\u5c06\u5176\u5199\u6210\u201c\u5df2\u5b8c\u6210\u768430\u8def\u53e3\u6700\u7ec8\u7ed3\u8bba\u201d\u3002', False),
    ])[1]

    return ref

def main():
    print('Opening document...')
    doc = Document(DOC)
    body = doc.element.body

    c3_idx = None
    c4_idx = None
    for i, p in enumerate(doc.paragraphs):
        text = p.text.strip()
        if text.startswith('3.') and '\u6838\u5fc3\u5b9e\u73b0' in text and c3_idx is None:
            c3_idx = i
        elif text.startswith('4.') and '\u603b\u7ed3' in text and c4_idx is None:
            c4_idx = i

    if c3_idx is None or c4_idx is None:
        print('ERROR: c3=%s, c4=%s' % (c3_idx, c4_idx))
        return

    print('Found Chapter 3 at paragraph %d, Chapter 4 at paragraph %d' % (c3_idx, c4_idx))

    paras = body.findall(qn('w:p'))
    for i in range(c4_idx - 1, c3_idx, -1):
        if i < len(paras):
            body.remove(paras[i])

    print('Deleted %d paragraphs' % (c4_idx - c3_idx - 1))

    paras = body.findall(qn('w:p'))
    ch3_elem = paras[c3_idx]

    print('Building new content...')
    build_content(doc, ch3_elem)

    print('Saving...')
    doc.save(OUT)
    print('Saved: %s' % OUT)

if __name__ == '__main__':
    main()
