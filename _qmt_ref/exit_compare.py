# -*- coding: utf-8 -*-
"""三种卖法对比：D 尾盘 / D+1 开盘 / D+1 尾盘（买入价统一为 D 开盘）。"""
import io
import json
import math
import os

W = r'F:\ai\deepseekharness\国金证券模拟账号'
CACHE = os.path.join(W, r'_qmt_ref\sina_cache')
OUT = os.path.join(W, r'_qmt_ref\exit_compare.txt')

recs = json.load(io.open(os.path.join(W, r'_qmt_ref\ab_recs.json'), 'r', encoding='utf-8'))


def bars_of(code):
    p = os.path.join(CACHE, '%s.json' % code)
    if not os.path.exists(p):
        return None
    return json.load(io.open(p, 'r', encoding='utf-8'))


def returns(bars, d):
    i = None
    for k, b in enumerate(bars):
        if b['d'] == d:
            i = k
            break
    if i is None or i + 1 >= len(bars):
        return None
    o = bars[i]['o']
    c0 = bars[i]['c']
    o1 = bars[i + 1]['o']
    c1 = bars[i + 1]['c']
    if not o:
        return None
    return (c0 / o - 1.0, o1 / o - 1.0, c1 / o - 1.0)


rows = []
for r in recs:
    bars = bars_of(r['code'])
    if not bars:
        continue
    t = returns(bars, r['d'])
    if not t:
        continue
    rows.append({'d': r['d'], 'code': r['code'], 'name': r['name'],
                 'tier': r['tier'], 'score': r['score'],
                 'r1': t[0], 'r2': t[1], 'r3': t[2]})

L = []


def agg(sel, label):
    if not sel:
        L.append('%-26s n=0' % label)
        return
    out = ['%-26s n=%-3d' % (label, len(sel))]
    for k, name in (('r1', 'D尾盘'), ('r2', 'D+1开盘'), ('r3', 'D+1尾盘')):
        vals = [x[k] for x in sel if x[k] is not None]
        if not vals:
            continue
        m = sum(vals) / len(vals)
        win = 100.0 * sum(1 for v in vals if v > 0) / len(vals)
        sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1)) if len(vals) > 1 else 0
        t = m / (sd / math.sqrt(len(vals))) if sd > 0 else 0
        out.append('%s=%+.2f%%(胜%.0f%%,t=%.2f)' % (name, m * 100, win, t))
    L.append('  '.join(out))


L.append('records=%d' % len(rows))
L.append('')
agg(rows, 'all')
agg([x for x in rows if x['tier'] == 1], 'T1')
agg([x for x in rows if x['tier'] == 2], 'T2')
agg([x for x in rows if x['tier'] == 3], 'T3')
L.append('')
L.append('T1 detail:')
for x in sorted([x for x in rows if x['tier'] == 1], key=lambda y: y['d']):
    L.append('  %s %-6s D尾盘=%+6.2f%%  D+1开=%+6.2f%%  D+1尾=%+6.2f%%'
             % (x['d'], x['code'], x['r1'] * 100, x['r2'] * 100, x['r3'] * 100))

io.open(OUT, 'w', encoding='utf-8').write('\n'.join(L))
print('\n'.join(L))
