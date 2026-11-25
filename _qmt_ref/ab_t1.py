# -*- coding: utf-8 -*-
"""T1 明细 + 统计显著性 + 去掉 11-05 的敏感性。"""
import io
import json
import math

W = r'F:\ai\deepseekharness\国金证券模拟账号'
recs = json.load(io.open(W + r'\_qmt_ref\ab_recs.json', 'r', encoding='utf-8'))

L = []


def stats(sel, label):
    if not sel:
        L.append('%s n=0' % label)
        return
    rs = [x['ret'] for x in sel]
    n = len(rs)
    m = sum(rs) / n
    var = sum((r - m) ** 2 for r in rs) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    t = m / (sd / math.sqrt(n)) if sd > 0 and n > 1 else 0.0
    L.append('%-22s n=%-3d mean=%+.2f%% sd=%.2f%% t=%.2f win=%.0f%%' %
             (label, n, m * 100, sd * 100, t,
              100.0 * sum(1 for r in rs if r > 0) / n))


t1 = [x for x in recs if x['tier'] == 1]
L.append('T1 trades:')
for x in sorted(t1, key=lambda y: y['d']):
    L.append('  %s %-6s %-10s score=%-3d bid=%+.1f%% ret=%+.2f%%' %
             (x['d'], x['code'], x['name'][:8], x['score'], x['bid'], x['ret'] * 100))
L.append('')
stats(t1, 'T1 all')
stats([x for x in t1 if x['d'] != '2026-11-05'], 'T1 excl 11-05')
stats([x for x in recs if x['tier'] == 2], 'T2')
stats([x for x in recs if x['tier'] == 3], 'T3')
stats(recs, 'all')
io.open(W + r'\_qmt_ref\ab_t1.txt', 'w', encoding='utf-8').write('\n'.join(L))
