# -*- coding: utf-8 -*-
"""重新验证今天的竞价选股：重抓快照 -> 重跑预设 -> 和实际推送的 8 只对比。"""
import io
import json
import os
import sys

W = r'F:\ai\deepseekharness\国金证券模拟账号'
sys.path.insert(0, W)
import bid_fetch as F
import bid_rules as R

OUT = os.path.join(W, r'out\verify_20261127.txt')
AUDIT = os.path.join(W, r'out\fetch_20261127.json')

lines = []


def log(s):
    lines.append(s)


try:
    text = F.fetch_json()
    rows, total = F.to_rows(text)
    cands = R.select(rows)

    audit = json.load(io.open(AUDIT, 'r', encoding='utf-8'))
    picked = [p['code'] for p in audit['picked']]
    now_codes = [c['code'] for c in cands]

    log('时间: %s' % __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    log('抓取行数: %d' % total)
    log('重跑命中: %d 只' % len(now_codes))
    log('当时推送: %d 只' % len(picked))
    log('')

    log('重跑名单: %s' % ','.join(now_codes))
    log('当时名单: %s' % ','.join(picked))
    log('')

    only_now = [c for c in now_codes if c not in picked]
    only_then = [c for c in picked if c not in now_codes]
    log('重跑多出: %s' % (','.join(only_now) or '无'))
    log('当时有/现在没有: %s' % (','.join(only_then) or '无'))
    log('')

    # 逐只对比指标
    then_map = {p['code']: p for p in audit['picked']}
    log('%-8s %-10s %8s %8s %6s %6s %8s' % ('code', 'name', 'bid_now', 'bid_then', 'prob', 'score', 'mv'))
    for c in cands:
        t = then_map.get(c['code'])
        log('%-8s %-10s %8.2f %8s %6d %6d %8.1f' % (
            c['code'], c['name'], c['bid_change'],
            ('%.2f' % t['bid']) if t else '-', c['prob'], c['score'], c['mv_yi']))
except Exception as e:
    import traceback
    log('ERR: %s\n%s' % (e, traceback.format_exc()))

io.open(OUT, 'w', encoding='utf-8').write('\n'.join(lines))
