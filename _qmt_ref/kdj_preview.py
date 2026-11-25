# -*- coding: utf-8 -*-
"""解析 QMT 日线 DAT，聚合成周线，跑一遍周线KDJ逻辑，给出可对照的买卖点。"""
import struct, datetime, io

PATH = r'D:\国金QMT交易端模拟\datadir\SZ\86400\300209.DAT'
OUT = r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\kdj_preview.out'

b = open(PATH, 'rb').read()
n = (len(b) - 8) // 64
bars = []
for k in range(n):
    off = 8 + k * 64
    ts = struct.unpack_from('<i', b, off)[0]
    o, h, l, c = struct.unpack_from('<4i', b, off + 4)
    vol = struct.unpack_from('<i', b, off + 20)[0]
    d = datetime.datetime.utcfromtimestamp(ts + 8 * 3600).date()  # 北京时间
    bars.append((d, o / 100.0, h / 100.0, l / 100.0, c / 100.0, vol))

# 一致性检查
bad = sum(1 for x in bars if not (x[2] >= max(x[1], x[4]) and x[3] <= min(x[1], x[4])))
lines = ['bars=%d  %s ~ %s  异常=%d' % (len(bars), bars[0][0], bars[-1][0], bad)]
lines.append('前3根: ' + str(bars[:3]))
lines.append('后3根: ' + str(bars[-3:]))

# 周线聚合（按 ISO 周，取周五/最后一天为标签）
weeks = []
cur = None
for (d, o, h, l, c, v) in bars:
    iso = d.isocalendar()
    key = (iso[0], iso[1])
    if cur is None or cur['key'] != key:
        cur = {'key': key, 'd': d, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v}
        weeks.append(cur)
    else:
        cur['h'] = max(cur['h'], h)
        cur['l'] = min(cur['l'], l)
        cur['c'] = c
        cur['d'] = d
        cur['v'] += v
lines.append('周线根数=%d  %s ~ %s' % (len(weeks), weeks[0]['d'], weeks[-1]['d']))

# KDJ(9,3,3)
K = D = 50.0
prev = None
rows = []
for i, w in enumerate(weeks):
    if i < 8:
        rsv = 50.0
    else:
        hh = max(x['h'] for x in weeks[i - 8:i + 1])
        ll = min(x['l'] for x in weeks[i - 8:i + 1])
        rsv = 50.0 if hh == ll else (w['c'] - ll) / (hh - ll) * 100.0
    K = (rsv + 2 * K) / 3.0
    D = (K + 2 * D) / 3.0
    J = 3 * K - 2 * D
    rows.append((w, K, D, J, prev))
    prev = (K, D)

lines.append('')
lines.append('== 周线KDJ 买卖点（K<25 金叉买，死叉卖）==')
pos = None
trades = []
for i in range(1, len(rows)):
    w, K, D, J, prior = rows[i]
    K2, D2 = prior
    golden = K2 <= D2 and K > D
    death = K2 >= D2 and K < D
    if golden and K < 25 and pos is None:
        pos = (w['d'], w['c'], K, D, J)
        lines.append('买入 %s 价%.2f  K=%.1f D=%.1f J=%.1f' % (w['d'], w['c'], K, D, J))
    elif death and pos is not None:
        pnl = (w['c'] / pos[1] - 1) * 100
        trades.append(pnl)
        lines.append('卖出 %s 价%.2f  K=%.1f D=%.1f J=%.1f  盈亏%.1f%%' % (w['d'], w['c'], K, D, J, pnl))
        pos = None
if pos is not None:
    pnl = (weeks[-1]['c'] / pos[1] - 1) * 100
    lines.append('（持仓中）%s 价%.2f 浮动%.1f%%' % (weeks[-1]['d'], weeks[-1]['c'], pnl))
lines.append('完整交易 %d 笔，胜率 %.0f%%，合计 %.1f%%' % (
    len(trades), 100.0 * sum(1 for t in trades if t > 0) / max(1, len(trades)), sum(trades)))

io.open(OUT, 'w', encoding='utf-8').write('\n'.join(lines))

# ===== 诊断：K 值分布 与 各类金叉 =====
ks = [r[1] for r in rows]
lines.append('')
lines.append('== K 值分布 ==')
lines.append('K 最小 %.1f  最大 %.1f  平均 %.1f' % (min(ks), max(ks), sum(ks) / len(ks)))
lines.append('K<25 的周数: %d / %d' % (sum(1 for x in ks if x < 25), len(ks)))
lines.append('K<40 的周数: %d / %d' % (sum(1 for x in ks if x < 40), len(ks)))
gc = []
for i in range(1, len(rows)):
    w, K, D, J, prior = rows[i]
    K2, D2 = prior
    if K2 <= D2 and K > D:
        gc.append((w['d'], K, D))
lines.append('金叉次数: %d' % len(gc))
lines.append('金叉时的 K: ' + ', '.join('%.0f' % x[1] for x in gc))
lines.append('前5次金叉: ' + '; '.join('%s K=%.0f' % (x[0], x[1]) for x in gc[:5]))
io.open(OUT, 'a', encoding='utf-8').write('\n'.join(lines[-6:]))

# ===== 用 BUY_K=35 再跑一遍 =====
def simulate(buy_k):
    out = []
    pos = None
    pnls = []
    for i in range(1, len(rows)):
        w, K, D, J, prior = rows[i]
        K2, D2 = prior
        if K2 <= D2 and K > D and K < buy_k and pos is None:
            pos = (w['d'], w['c']); out.append('买 %s @%.2f K=%.0f' % (w['d'], w['c'], K))
        elif K2 >= D2 and K < D and pos is not None:
            p = (w['c'] / pos[1] - 1) * 100; pnls.append(p)
            out.append('卖 %s @%.2f  %+.1f%%' % (w['d'], w['c'], p)); pos = None
    if pos is not None:
        p = (weeks[-1]['c'] / pos[1] - 1) * 100
        out.append('持仓中 @%.2f 浮动%+.1f%%' % (pos[1], p)); pnls.append(p)
    return out, pnls

for bk in (25, 35, 45):
    o, pn = simulate(bk)
    lines2 = ['', '== BUY_K=%d：%d 笔，累计 %.1f%% ==' % (bk, len(pn), sum(pn))]
    lines2 += o
    io.open(OUT, 'a', encoding='utf-8').write('\n'.join(lines2))
