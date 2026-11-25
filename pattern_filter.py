# -*- coding: utf-8 -*-
"""
pattern_filter.py -- 「涨停 → 回踩吞金杀牛线 → 刚突破」形态识别 + 历史 A/B 回测。

形态定义（全部只用 D-1 及更早的日线，无未来函数）：
    吞金杀牛线 X30 = (MA5+MA10+MA15+MA20+MA25+MA30)/6
    LU      : 最近 10 个交易日内有过涨停（主板 >=9.5%，创业/科创 >=19.5%）
    BREAK   : 涨停之后至少有一根收盘站上 X30（突破过）
    PULLBACK: 突破之后至少有一根最低价回到 X30 附近（<=X30*1.01 或收盘 <= X30）
    ABOVE   : D-1 收盘在 X30 上方，且不超过 X30*1.08（刚突破、没飞走）
    MA_OK   : X30 走平或向上（>= 5 根前 * 0.995）
    CROSS   : D-1 当天上穿（C(D-1)>X30 且 C(D-2)<=X30）

用法：
    python pattern_filter.py --backtest
    python pattern_filter.py --code 300209
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

W = r'F:\ai\deepseekharness\国金证券模拟账号'
sys.path.insert(0, W)
import bid_rules as R

KLINE = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
EXPORT_DIR = r'F:\ai\deepseekharness\竞价分析\export'
CACHE_DIR = os.path.join(W, '_qmt_ref', 'kline_cache')


# ------------------------------------------------------------------ 数据

def tx_symbol(code):
    code = str(code).zfill(6)
    return ('sh' if code[0] in '569' else 'sz') + code


def fetch_kline(code, lmt=200, retries=2):
    """腾讯日线（前复权）：[date, open, close, high, low, volume(手)]"""
    sym = tx_symbol(code)
    url = '%s?param=%s,day,,,%d,qfq' % (KLINE, sym, lmt)
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA,
                                                       'Referer': 'https://gu.qq.com/'})
            with urllib.request.urlopen(req, timeout=8) as r:
                j = json.loads(r.read().decode('utf-8', 'ignore'))
            node = (j.get('data') or {}).get(sym) or {}
            arr = node.get('qfqday') or node.get('day') or []
            bars = []
            for p in arr:
                if len(p) < 5:
                    continue
                bars.append({'d': p[0], 'o': float(p[1]), 'c': float(p[2]),
                             'h': float(p[3]), 'l': float(p[4]),
                             'v': float(p[5]) if len(p) > 5 else 0.0})
            if bars:
                return bars
        except Exception as e:
            last = e
        time.sleep(0.2)
    raise RuntimeError('kline %s failed: %s' % (code, last))


def cached_kline(code, lmt=200):
    if not os.path.isdir(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    p = os.path.join(CACHE_DIR, '%s.json' % code)
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < 12 * 3600:
        try:
            return json.loads(io.open(p, 'r', encoding='utf-8').read())
        except Exception:
            pass
    bars = fetch_kline(code, lmt)
    io.open(p, 'w', encoding='utf-8').write(json.dumps(bars))
    return bars


# -------------------------------------------------------------- 指标

def ma(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def x30_series(bars):
    c = [b['c'] for b in bars]
    mas = [ma(c, n) for n in (5, 10, 15, 20, 25, 30)]
    out = []
    for i in range(len(c)):
        if any(m[i] is None for m in mas):
            out.append(None)
        else:
            out.append(sum(m[i] for m in mas) / 6.0)
    return out


def limit_pct(code):
    code = str(code).zfill(6)
    if code.startswith('30') or code.startswith('68'):
        return 0.195
    return 0.095


def evaluate(bars, code):
    """返回 D-1 收盘时的形态状态；bars 必须截止到 D-1"""
    n = len(bars)
    if n < 40:
        return None
    X = x30_series(bars)
    c = [b['c'] for b in bars]
    l = [b['l'] for b in bars]
    i = n - 1
    if X[i] is None or X[i] <= 0:
        return None

    lim = limit_pct(code)
    lu_idx = None
    for t in range(max(1, i - 9), i + 1):
        if c[t - 1] > 0 and c[t] / c[t - 1] - 1 >= lim:
            lu_idx = t                      # 取最近一次涨停
    lu = lu_idx is not None

    start = lu_idx if lu else max(1, i - 20)
    brk = None
    for t in range(start, i + 1):
        if X[t] is not None and c[t] > X[t]:
            brk = t
            break
    pull = False
    if brk is not None:
        for t in range(brk + 1, i + 1):
            if X[t] is not None and (l[t] <= X[t] * 1.01 or c[t] <= X[t]):
                pull = True
                break

    above = c[i] > X[i] and c[i] <= X[i] * 1.08
    ma_ok = X[i - 5] is not None and X[i] >= X[i - 5] * 0.995
    cross = (c[i] > X[i]) and (X[i - 1] is not None and c[i - 1] <= X[i - 1])

    tier = 3
    if lu and brk is not None and pull and above and ma_ok:
        tier = 1
    elif brk is not None and above and ma_ok:
        tier = 2

    return {'code': code, 'x30': X[i], 'close': c[i],
            'lu': lu, 'lu_idx': lu_idx, 'brk': brk is not None, 'pull': pull,
            'above': above, 'ma_ok': ma_ok, 'cross': cross,
            'dist': c[i] / X[i] - 1, 'tier': tier}


def eval_at_date(bars, code, date):
    idx = None
    for k, b in enumerate(bars):
        if b['d'] < date:
            idx = k
        else:
            break
    if idx is None or idx + 1 < 40:
        return None
    return evaluate(bars[:idx + 1], code)


def next_day_return(bars, date):
    """D 开盘买 → D+1 收盘卖（复权价，收益口径一致）"""
    o = c1 = None
    for k, b in enumerate(bars):
        if b['d'] == date:
            o = b['o']
            if k + 1 < len(bars):
                c1 = bars[k + 1]['c']
            break
    if not o or not c1:
        return None
    return c1 / o - 1.0


# -------------------------------------------------------------- 回测

def backtest(exclude=()):
    files = sorted([f for f in os.listdir(EXPORT_DIR) if f.startswith('竞价数据_')])
    if not files:
        print('没有导出文件')
        return
    rows_all = []
    for fn in files:
        path = os.path.join(EXPORT_DIR, fn)
        tag = fn.replace('竞价数据_', '').replace('.csv', '')
        if tag in exclude:
            print('[%s] 跳过（快照时点无效）' % tag)
            continue
        rows = []
        import csv
        with io.open(path, 'r', encoding='utf-8-sig', newline='') as fh:
            for raw in csv.DictReader(fh):
                rows.append(R.build_row(raw))
        picked = R.select(rows)
        print('[%s] 候选 %d 只' % (tag, len(picked)))
        rows_all.append((tag, picked))

    # 基准：中证1000（小盘等权近似）
    bench = {}
    try:
        ibars = cached_kline('000852')
        for tag, _ in rows_all:
            bench[tag] = next_day_return(ibars, tag)
        print('基准(中证1000) 各日: %s' % ', '.join('%s=%+.2f%%' % (k, (v or 0) * 100)
                                                for k, v in sorted(bench.items())))
    except Exception as e:
        print('基准获取失败: %s' % e)

    cache = {}
    results = []
    for tag, picked in rows_all:
        for r in picked:
            code = r['code']
            if code not in cache:
                try:
                    cache[code] = cached_kline(code)
                except Exception as e:
                    cache[code] = None
            bars = cache[code]
            if not bars:
                continue
            st = eval_at_date(bars, code, tag)
            ret = next_day_return(bars, tag)
            if st is None or ret is None:
                continue
            b = bench.get(tag)
            st.update({'date': tag, 'ret': ret,
                       'excess': (ret - b) if b is not None else None,
                       'prob': r['prob'], 'score': r['score'],
                       'bid': r['bid_change'], 'name': r['name']})
            results.append(st)

    def agg(sel, label):
        if not sel:
            print('%-20s n=0' % label)
            return
        rets = sorted(x['ret'] for x in sel)
        avg = sum(rets) / len(rets)
        win = sum(1 for x in rets if x > 0) / len(rets)
        ex = [x['excess'] for x in sel if x['excess'] is not None]
        etxt = ''
        if ex:
            eavg = sum(ex) / len(ex)
            ewin = sum(1 for x in ex if x > 0) / len(ex)
            etxt = ' | 超额=%+.3f%% 超额胜率=%.0f%%' % (eavg * 100, ewin * 100)
        print('%-20s n=%-4d avg=%+.3f%% 胜率=%.0f%%%s' %
              (label, len(rets), avg * 100, win * 100, etxt))

    print('\n=== 全部候选 ===')
    agg(results, 'all')
    print('\n=== 按形态分层 ===')
    agg([x for x in results if x['tier'] == 1], 'T1 涨停+回踩+突破')
    agg([x for x in results if x['tier'] == 2], 'T2 突破(无涨停)')
    agg([x for x in results if x['tier'] == 3], 'T3 其他')
    print('\n=== 单条件 ===')
    agg([x for x in results if x['lu']], '近10日有涨停')
    agg([x for x in results if x['pull']], '有回踩')
    agg([x for x in results if x['cross']], 'D-1 刚上穿')
    agg([x for x in results if x['ma_ok']], 'X30 走平/向上')
    agg([x for x in results if x['lu'] and x['cross']], '涨停+刚上穿')

    out = os.path.join(W, '_qmt_ref', 'pattern_backtest.json')
    io.open(out, 'w', encoding='utf-8').write(json.dumps(results, ensure_ascii=False, indent=1))
    print('\n明细: %s (%d 条)' % (out, len(results)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backtest', action='store_true')
    ap.add_argument('--exclude', default='')
    ap.add_argument('--code', default='')
    args = ap.parse_args()
    if args.backtest:
        backtest(exclude=tuple(x.strip() for x in args.exclude.split(',') if x.strip()))
        return
    if args.code:
        bars = fetch_kline(args.code)
        st = evaluate(bars, args.code)
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return
    ap.print_help()


if __name__ == '__main__':
    main()
