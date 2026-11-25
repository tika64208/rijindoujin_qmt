# -*- coding: utf-8 -*-
"""
ab_backtest.py -- 用 App 库导出的 35 个交易日，对「竞价预设 + T1 形态」做 A/B。

数据源：新浪日线（腾讯/东财的 kline 接口在本机被限流，新浪可用）
口径：D 日开盘买 → D+1 收盘卖；所有形态条件只用 D-1 及更早的日线。
"""
import io
import json
import os
import re
import sys
import time
import urllib.request

W = r'F:\ai\deepseekharness\国金证券模拟账号'
sys.path.insert(0, W)
import bid_rules as R
import pattern_filter as P

EX = os.path.join(W, r'_data_20261124\export')
CACHE = os.path.join(W, r'_qmt_ref\sina_cache')
OUT = os.path.join(W, r'_qmt_ref\ab_result.txt')
SKIP_DAYS = {'2026-10-31', '2026-11-08'}      # 周末副本
SINA = ('https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/'
        'CN_MarketData.getKLineData?symbol=%s&scale=240&ma=no&datalen=%d')


def sina_symbol(code):
    code = str(code).zfill(6)
    return ('sh' if code[0] in '569' else 'sz') + code


def fetch(code, n=250):
    if not os.path.isdir(CACHE):
        os.makedirs(CACHE)
    p = os.path.join(CACHE, '%s.json' % code)
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < 12 * 3600:
        try:
            return json.loads(io.open(p, 'r', encoding='utf-8').read())
        except Exception:
            pass
    url = SINA % (sina_symbol(code), n)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                               'Referer': 'https://finance.sina.com.cn/'})
    with urllib.request.urlopen(req, timeout=8) as r:
        arr = json.loads(r.read().decode('utf-8', 'ignore'))
    bars = [{'d': x['day'], 'o': float(x['open']), 'c': float(x['close']),
             'h': float(x['high']), 'l': float(x['low']),
             'v': float(x.get('volume') or 0)} for x in arr]
    io.open(p, 'w', encoding='utf-8').write(json.dumps(bars))
    return bars


def ret_open_to_next_close(bars, date):
    o = c1 = None
    for i, b in enumerate(bars):
        if b['d'] == date:
            o = b['o']
            if i + 1 < len(bars):
                c1 = bars[i + 1]['c']
            break
    return (c1 / o - 1.0) if (o and c1) else None


def ret_open_to_close(bars, date):
    for b in bars:
        if b['d'] == date:
            return b['c'] / b['o'] - 1.0 if b['o'] else None
    return None


def load_candidates():
    import csv
    days = []
    for fn in sorted(os.listdir(EX)):
        if not fn.startswith('竞价数据_'):
            continue
        tag = fn.replace('竞价数据_', '').replace('.csv', '')
        if tag in SKIP_DAYS:
            continue
        rows = []
        with io.open(os.path.join(EX, fn), 'r', encoding='utf-8-sig', newline='') as fh:
            for raw in csv.DictReader(fh):
                rows.append(R.build_row(raw))
        days.append((tag, R.select(rows)))
    return days


def main():
    days = load_candidates()
    cache = {}
    recs = []
    fail = 0
    for tag, picked in days:
        for r in picked:
            c = r['code']
            if c not in cache:
                try:
                    cache[c] = fetch(c)
                    time.sleep(0.15)
                except Exception:
                    cache[c] = None
                    fail += 1
            bars = cache[c]
            if not bars:
                continue
            st = P.eval_at_date(bars, c, tag)
            ret = ret_open_to_next_close(bars, tag)
            ret0 = ret_open_to_close(bars, tag)
            if st is None or ret is None:
                continue
            recs.append({'d': tag, 'code': c, 'name': r['name'], 'score': r['score'],
                         'prob': r['prob'], 'bid': r['bid_change'],
                         'tier': st['tier'], 'lu': st['lu'], 'pull': st['pull'],
                         'cross': st['cross'], 'ma_ok': st['ma_ok'],
                         'ret': ret, 'ret0': ret0})
    io.open(os.path.join(W, r'_qmt_ref\ab_recs.json'), 'w', encoding='utf-8').write(
        json.dumps(recs, ensure_ascii=False))

    L = []

    def agg(sel, label):
        if not sel:
            L.append('%-24s n=0' % label)
            return
        rets = [x['ret'] for x in sel]
        avg = sum(rets) / len(rets)
        win = sum(1 for x in rets if x > 0) / float(len(rets))
        med = sorted(rets)[len(rets) // 2]
        L.append('%-24s n=%-4d avg=%+.2f%% med=%+.2f%% win=%.0f%%' %
                 (label, len(rets), avg * 100, med * 100, win * 100))

    L.append('days=%d records=%d fetch_fail=%d' % (len(days), len(recs), fail))
    L.append('')
    L.append('[全部候选]')
    agg(recs, 'all')
    L.append('')
    L.append('[形态分层]')
    agg([x for x in recs if x['tier'] == 1], 'T1 涨停+回踩+突破')
    agg([x for x in recs if x['tier'] == 2], 'T2 突破(无涨停)')
    agg([x for x in recs if x['tier'] == 3], 'T3 其他')
    L.append('')
    L.append('[单条件]')
    agg([x for x in recs if x['lu']], '自选:近10日涨停')
    agg([x for x in recs if x['cross']], '自选:D-1刚上穿')
    agg([x for x in recs if x['cross'] and x['lu']], '自选:涨停+刚上穿')
    L.append('')
    L.append('[每日取前N(按评分)]')

    for n in (3, 5, 10):
        sel = []
        for tag, picked in days:
            top = sorted([x for x in recs if x['d'] == tag],
                         key=lambda x: (-x['score'], -x['prob']))[:n]
            sel.extend(top)
        agg(sel, 'top%d by score' % n)

    L.append('')
    L.append('[按当天候选数分组]')
    N = {tag: len(p) for tag, p in days}
    for lo, hi, name in ((1, 5, 'N<=5'), (6, 20, '6-20'), (21, 60, '21-60'), (61, 999, '>60')):
        agg([x for x in recs if lo <= N.get(x['d'], 0) <= hi], name)

    L.append('')
    L.append('[同口径参考：D 开盘→D 收盘]')
    r0 = [x['ret0'] for x in recs if x['ret0'] is not None]
    if r0:
        L.append('same-day avg=%+.2f%% win=%.0f%%' %
                 (sum(r0) / len(r0) * 100, sum(1 for v in r0 if v > 0) / float(len(r0)) * 100))

    io.open(OUT, 'w', encoding='utf-8').write('\n'.join(L))
    print('\n'.join(L))


main()
