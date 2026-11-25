# -*- coding: utf-8 -*-
"""T1 相对中证1000的超额 + 去掉最强两天的敏感性。"""
import io
import json
import math
import time
import urllib.request

W = r'F:\ai\deepseekharness\国金证券模拟账号'
SINA = ('https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/'
        'CN_MarketData.getKLineData?symbol=sh000852&scale=240&ma=no&datalen=250')

req = urllib.request.Request(SINA, headers={'User-Agent': 'Mozilla/5.0',
                                            'Referer': 'https://finance.sina.com.cn/'})
with urllib.request.urlopen(req, timeout=10) as r:
    arr = json.loads(r.read().decode('utf-8', 'ignore'))
bench = {x['day']: float(x['close']) for x in arr}
opens = {x['day']: float(x['open']) for x in arr}
idx_days = sorted(bench)
nxt = {d: idx_days[i + 1] for i, d in enumerate(idx_days[:-1])}


def bench_ret(d):
    if d not in opens or d not in nxt:
        return None
    return bench[nxt[d]] / opens[d] - 1.0


recs = json.load(io.open(W + r'\_qmt_ref\ab_recs.json', 'r', encoding='utf-8'))
t1 = [x for x in recs if x['tier'] == 1]

L = []
for x in t1:
    b = bench_ret(x['d'])
    x['bench'] = b
    x['excess'] = (x['ret'] - b) if b is not None else None
    L.append('%s %-6s ret=%+6.2f%% bench=%+6.2f%% excess=%+6.2f%%' %
             (x['d'], x['code'], x['ret'] * 100,
              (b or 0) * 100, (x['excess'] or 0) * 100))


def stats(sel, label):
    rs = [x['excess'] for x in sel if x.get('excess') is not None]
    if not rs:
        L.append('%s n=0' % label)
        return
    n = len(rs)
    m = sum(rs) / n
    sd = math.sqrt(sum((r - m) ** 2 for r in rs) / (n - 1)) if n > 1 else 0.0
    t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
    L.append('%-26s n=%-3d excess_mean=%+.2f%% t=%.2f win=%.0f%%' %
             (label, n, m * 100, t, 100.0 * sum(1 for r in rs if r > 0) / n))


L.append('')
stats(t1, 'T1 excess vs CSI1000')
stats([x for x in t1 if x['d'] not in ('2026-11-09', '2026-11-10')], 'T1 excl 11-09/11-10')
stats([x for x in t1 if x['d'] != '2026-11-05'], 'T1 excl 11-05')

raw = [x['ret'] for x in t1 if x['d'] not in ('2026-11-09', '2026-11-10')]
if raw:
    m = sum(raw) / len(raw)
    sd = math.sqrt(sum((r - m) ** 2 for r in raw) / (len(raw) - 1))
    L.append('T1 excl rally raw: n=%d mean=%+.2f%% t=%.2f' %
             (len(raw), m * 100, m / (sd / math.sqrt(len(raw)))))

io.open(W + r'\_qmt_ref\ab_t1_excess.txt', 'w', encoding='utf-8').write('\n'.join(L))
