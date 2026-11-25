# -*- coding: utf-8 -*-
"""用 bid_rules 跑一遍 37 天导出，看看每天预设入选多少只（N 的分布）。"""
import csv
import glob
import io
import os
import sys

W = r'F:\ai\deepseekharness\国金证券模拟账号'
sys.path.insert(0, W)
import bid_rules as R

EX = os.path.join(W, r'_data_20261124\export')
OUT = os.path.join(W, r'_qmt_ref\n_stats.out')

rows_out = []
counts = []
for path in sorted(glob.glob(os.path.join(EX, '竞价数据_*.csv'))):
    tag = os.path.basename(path).replace('竞价数据_', '').replace('.csv', '')
    rows = []
    with io.open(path, 'r', encoding='utf-8-sig', newline='') as fh:
        for raw in csv.DictReader(fh):
            rows.append(R.build_row(raw))
    picked = R.select(rows)
    counts.append(len(picked))
    rows_out.append('%s  rows=%-5d picked=%-4d' % (tag, len(rows), len(picked)))

rows_out.append('')
rows_out.append('days=%d  min=%d  max=%d  avg=%.1f  median=%d  zero_days=%d'
                % (len(counts), min(counts), max(counts), sum(counts) / float(len(counts)),
                   sorted(counts)[len(counts) // 2], sum(1 for c in counts if c == 0)))
io.open(OUT, 'w', encoding='utf-8').write('\n'.join(rows_out))
