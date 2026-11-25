# -*- coding: utf-8 -*-
"""离线复算：300209 周线KDJ(K<35) 每次买10万，初始100万。"""
import struct, datetime, io

PATH = r'D:\国金QMT交易端模拟\datadir\SZ\86400\300209.DAT'
OUT = r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\wkdj_sim.out'

KDJ_N, BUY_K = 9, 35.0
AMOUNT, CASH0 = 100000.0, 1000000.0
START, END = datetime.date(2023, 1, 1), datetime.date(2026, 11, 17)
MIN_WEEKS = KDJ_N + 5

b = open(PATH, 'rb').read()
n = (len(b) - 8) // 64
bars = []
for k in range(n):
    off = 8 + k * 64
    ts = struct.unpack_from('<i', b, off)[0]
    o, h, l, c = struct.unpack_from('<4i', b, off + 4)
    d = datetime.datetime.utcfromtimestamp(ts + 8 * 3600).date()
    bars.append((d, h / 100.0, l / 100.0, c / 100.0))

lines = ['日线 %d 根 %s ~ %s' % (len(bars), bars[0][0], bars[-1][0])]

# 按 ISO 周合成
weeks = []
for (d, h, l, c) in bars:
    key = d.isocalendar()[:2]
    if weeks and weeks[-1][0] == key:
        weeks[-1][1] = max(weeks[-1][1], h)
        weeks[-1][2] = min(weeks[-1][2], l)
        weeks[-1][3] = c
        weeks[-1][4] = d
    else:
        weeks.append([key, h, l, c, d])
lines.append('周线 %d 根' % len(weeks))

# KDJ
kdj = []
k = d_ = 50.0
for i in range(len(weeks)):
    lo = max(0, i - KDJ_N + 1)
    hh = max(w[1] for w in weeks[lo:i + 1])
    ll = min(w[2] for w in weeks[lo:i + 1])
    c = weeks[i][3]
    rsv = 50.0 if hh == ll else (c - ll) / (hh - ll) * 100.0
    k = (2 * k + rsv) / 3.0
    d_ = (2 * d_ + k) / 3.0
    kdj.append((k, d_, 3 * k - 2 * d_))

cash, shares, trades = CASH0, 0, []
for i in range(1, len(weeks)):
    w = weeks[i]
    if not (START <= w[4] <= END):
        continue
    if i + 1 < MIN_WEEKS:
        continue
    k1, d1, _ = kdj[i - 1]
    k2, d2, j2 = kdj[i]
    px = w[3]
    if k1 <= d1 and k2 > d2 and k2 < BUY_K and shares == 0:
        vol = int(AMOUNT / px / 100) * 100
        if vol >= 100 and vol * px <= cash:
            cash -= vol * px
            shares = vol
            trades.append(('B', w[4], px, vol, k2, d2))
    elif k1 >= d1 and k2 < d2 and shares > 0:
        cash += shares * px
        trades.append(('S', w[4], px, shares, k2, d2))
        shares = 0

last_px = [w for w in weeks if START <= w[4] <= END][-1][3]
final = cash + shares * last_px
lines.append('')
for t in trades:
    lines.append('%s %s @%.2f x%d  K=%.1f D=%.1f' % (t[0], t[1], t[2], t[3], t[4], t[5]))
lines.append('')
lines.append('成交 %d 条, 期末资金 %.0f, 持仓 %d 股 @%.2f' % (len(trades), cash, shares, last_px))
lines.append('总资产 %.0f  收益率 %.2f%%' % (final, (final / CASH0 - 1) * 100))
bh = (last_px / [w for w in weeks if START <= w[4] <= END][0][3] - 1) * 100
lines.append('同期买入持有 %.2f%%' % bh)

io.open(OUT, 'w', encoding='utf-8').write('\n'.join(lines))
