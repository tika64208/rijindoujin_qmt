# -*- coding: utf-8 -*-
"""检查 App daily_bars 对竞价候选的覆盖率（能否支撑 35 天回测）。"""
import csv
import glob
import io
import os
import sqlite3
import sys

W = r'F:\ai\deepseekharness\国金证券模拟账号'
sys.path.insert(0, W)
import bid_rules as R

DB = os.path.join(W, r'_data_20261124\databases\momentum.db')
EX = os.path.join(W, r'_data_20261124\export')
OUT = os.path.join(W, r'_qmt_ref\coverage.out')

con = sqlite3.connect(DB)
cur = con.cursor()

bar_max = {}
for sym, mx, n in cur.execute('select symbol, max(date), count(*) from daily_bars group by symbol'):
    bar_max[sym] = (mx, n)
print('symbols in daily_bars:', len(bar_max))

def tx(sym):
    # sh600000 -> 600000
    return sym[2:] if sym[:2] in ('sh', 'sz', 'bj') else sym

lines = []
days = []
for path in sorted(glob.glob(os.path.join(EX, '竞价数据_*.csv'))):
    tag = os.path.basename(path).replace('竞价数据_', '').replace('.csv', '')
    rows = []
    with io.open(path, 'r', encoding='utf-8-sig', newline='') as fh:
        for raw in csv.DictReader(fh):
            rows.append(R.build_row(raw))
    picked = R.select(rows)
    days.append((tag, picked))

dates = [d for d, _ in days]
prev = {}
for i, d in enumerate(dates):
    prev[d] = dates[i - 1] if i else None

total = covered = exact = 0
for tag, picked in days:
    n_cov = n_exact = 0
    for r in picked:
        total += 1
        info = bar_max.get('sz' + r['code']) or bar_max.get('sh' + r['code'])
        if not info:
            continue
        covered += 1
        n_cov += 1
        if info[1] >= 40 and info[0] == prev.get(tag):
            exact += 1
            n_exact += 1
    lines.append('%s picked=%-4d inDB=%-4d exact=%-4d' % (tag, len(picked), n_cov, n_exact))

lines.append('')
lines.append('total=%d covered=%d exact=%d (%.1f%% / %.1f%%)'
             % (total, covered, exact, 100.0 * covered / max(1, total), 100.0 * exact / max(1, total)))
io.open(OUT, 'w', encoding='utf-8').write('\n'.join(lines))
con.close()
