# -*- coding: utf-8 -*-
"""用磁盘 DAT 真实数据离线跑 MA5/20 三年回测，给出对照结果。"""
import struct, datetime, io

PATH = r'D:\国金QMT交易端模拟\datadir\SZ\86400\000001.DAT'
OUT = r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\ma_sim.out'

FAST, SLOW = 5, 20
CASH0 = 100000.0        # 每次买入金额
INIT_CASH = 1000000.0
START = datetime.date(2023, 1, 1)
END = datetime.date(2026, 11, 17)

b = open(PATH, 'rb').read()
n = (len(b) - 8) // 64
bars = []
for k in range(n):
    off = 8 + k * 64
    ts = struct.unpack_from('<i', b, off)[0]
    o, h, l, c = struct.unpack_from('<4i', b, off + 4)
    d = datetime.datetime.utcfromtimestamp(ts + 8 * 3600).date()
    bars.append((d, o / 100.0, h / 100.0, l / 100.0, c / 100.0))

lines = ['全部日线 %d 根: %s ~ %s' % (len(bars), bars[0][0], bars[-1][0])]
window = [x for x in bars if START <= x[0] <= END]
lines.append('回测区间内 %d 根: %s ~ %s' % (len(window), window[0][0], window[-1][0]))

# 从 START 之前取足够历史算均线
idx0 = len(bars) - len(window)
hist = bars[max(0, idx0 - 60):]
series = [x[4] for x in window]

def ma(arr, n):
    return sum(arr[-n:]) / float(n)

cash = INIT_CASH
shares = 0
trades = []
pos_price = 0.0
# 预热：用窗口前的收盘价补足
pre = [x[4] for x in hist[:-len(window)]] if len(hist) > len(window) else []
buf = list(pre)
for i, (d, o, h, l, c) in enumerate(window):
    buf.append(c)
    if len(buf) < SLOW + 2:
        continue
    fast_now, slow_now = ma(buf, FAST), ma(buf, SLOW)
    fast_pre = sum(buf[-FAST - 1:-1]) / float(FAST)
    slow_pre = sum(buf[-SLOW - 1:-1]) / float(SLOW)
    if fast_pre <= slow_pre and fast_now > slow_now and shares == 0:
        vol = int(CASH0 / c / 100) * 100
        if vol >= 100 and vol * c <= cash:
            cash -= vol * c
            shares = vol
            pos_price = c
            trades.append(('B', d, c, vol))
    elif fast_pre >= slow_pre and fast_now < slow_now and shares > 0:
        cash += shares * c
        trades.append(('S', d, c, shares))
        shares = 0

final = cash + shares * window[-1][4]
total = (final / INIT_CASH - 1) * 100
# 同期买入持有
bh = (window[-1][4] / window[0][4] - 1) * 100

lines.append('')
lines.append('买卖 %d 笔' % len(trades))
for t in trades:
    lines.append('  %s %s @%.2f x%d' % (t[0], t[1], t[2], t[3]))
lines.append('')
lines.append('期末资产 %.0f  累计收益 %.2f%%' % (final, total))
lines.append('同期买入持有 %.2f%%' % bh)
lines.append('持仓中: %s' % ('是 %d 股' % shares if shares else '否'))

io.open(OUT, 'w', encoding='utf-8').write('\n'.join(lines))
