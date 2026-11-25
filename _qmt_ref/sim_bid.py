# -*- coding: utf-8 -*-
"""推演：4 天真实竞价快照 -> 预设筛选 -> 买入 -> 三种卖出口径的收益分布。"""
import csv, io, os, struct, datetime, sys, random
sys.path.insert(0, r'F:\ai\deepseekharness\国金证券模拟账号')
import bid_rules as R

EXPORT = r'F:\ai\deepseekharness\竞价分析\export'
DATA = r'D:\国金QMT交易端模拟\datadir'
OUT = r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\sim_bid.out'

DAYS = ['2026-11-05', '2026-11-06', '2026-11-09', '2026-11-10']

_cache = {}
def bars(code):
    """{date: (open, close)} 价格=原值/1000"""
    if code in _cache:
        return _cache[code]
    mk = 'SH' if code[:1] in ('5', '6', '9') else 'SZ'
    path = os.path.join(DATA, mk, '86400', code + '.DAT')
    if not os.path.exists(path):
        _cache[code] = None
        return None
    try:
        b = open(path, 'rb').read()
        n = (len(b) - 8) // 64
        d = {}
        for k in range(n):
            off = 8 + k * 64
            ts = struct.unpack_from('<i', b, off)[0]
            o, h, l, c = struct.unpack_from('<4i', b, off + 4)
            dd = datetime.datetime.utcfromtimestamp(ts + 8*3600).date()
            d[dd] = (o / 1000.0, c / 1000.0)
    except Exception:
        d = None
    _cache[code] = d
    return d

def next_trading(d, all_dates):
    later = [x for x in all_dates if x > d]
    return min(later) if later else None

def load_day(tag):
    path = os.path.join(EXPORT, '竞价数据_%s.csv' % tag)
    if not os.path.exists(path):
        return None
    rows = []
    for raw in csv.DictReader(io.open(path, encoding='utf-8-sig', newline='')):
        r = R.build_row(raw)
        if r['app_prob'] > 0:
            r['prob'], r['conf'], r['score'] = r['app_prob'], r['app_conf'], r['app_score']
        rows.append(r)
    return rows

def stats(vals):
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    mean = sum(s) / n
    med = s[n//2] if n % 2 else (s[n//2-1] + s[n//2]) / 2.0
    win = sum(1 for x in s if x > 0)
    return dict(n=n, mean=mean, med=med, win=100.0*win/n, best=s[-1], worst=s[0])

lines = []
overall = {'same': [], 'n1o': [], 'n1c': []}
mkt = {'same': [], 'n1o': [], 'n1c': []}

for tag in DAYS:
    rows = load_day(tag)
    if rows is None:
        lines.append('%s: 无导出文件' % tag); continue
    d0 = datetime.date(*[int(x) for x in tag.split('-')])
    picked = R.select(rows)
    lines.append('')
    lines.append('=== %s  全市场 %d 行，预设入选 %d 只 ===' % (tag, len(rows), len(picked)))
    if not picked:
        continue

    res = {'same': [], 'n1o': [], 'n1c': []}
    detail = []
    for r in picked:
        op = r['open']
        if op <= 0:
            continue
        bs = bars(r['code'])
        # 当日收盘
        same = (r['last'] / op - 1) * 100 if r['last'] > 0 else None
        n1o = n1c = None
        if bs:
            nxt = next_trading(d0, list(bs.keys()))
            if nxt:
                no, nc = bs[nxt]
                n1o = (no / op - 1) * 100
                n1c = (nc / op - 1) * 100
        if same is not None: res['same'].append(same)
        if n1o is not None: res['n1o'].append(n1o)
        if n1c is not None: res['n1c'].append(n1c)
        detail.append((r, same, n1o, n1c))

    for k, label in (('same', '当日收盘卖(纸面)'), ('n1o', '次日开盘卖(T+1)'), ('n1c', '次日收盘卖(T+1)')):
        st = stats(res[k])
        if st:
            lines.append('  %-16s n=%-3d 均值%+6.2f%% 中位%+6.2f%% 胜率%5.1f%% 最好%+6.1f%% 最差%+6.1f%%'
                         % (label, st['n'], st['mean'], st['med'], st['win'], st['best'], st['worst']))
            overall[k].extend(res[k])

    # top-N
    for n in (3, 5, 10):
        top = sorted(picked, key=lambda r: (-r['prob'], -r['score'], r['code']))[:n]
        v = []
        for r in top:
            bs = bars(r['code'])
            if not bs or r['open'] <= 0: continue
            nxt = next_trading(d0, list(bs.keys()))
            if nxt:
                v.append((bs[nxt][0] / r['open'] - 1) * 100)
        st = stats(v)
        if st:
            lines.append('  top%-2d(概率→评分) 次日开盘: n=%d 均值%+6.2f%% 胜率%5.1f%%'
                         % (n, st['n'], st['mean'], st['win']))

    # 明细前 5
    detail.sort(key=lambda x: -(x[2] if x[2] is not None else -999))
    lines.append('  -- 次日开盘收益前5 / 后3 --')
    for r, s, o, c in detail[:5]:
        lines.append('     %s %-8s 竞价%+5.2f%% prob=%d score=%d 当日%+6.2f%% 次开%+6.2f%%'
                     % (r['code'], r['name'][:8], r['bid_change'], r['prob'], r['score'],
                        s if s is not None else 0, o if o is not None else 0))
    for r, s, o, c in detail[-3:]:
        lines.append('     %s %-8s 竞价%+5.2f%% prob=%d score=%d 当日%+6.2f%% 次开%+6.2f%%'
                     % (r['code'], r['name'][:8], r['bid_change'], r['prob'], r['score'],
                        s if s is not None else 0, o if o is not None else 0))

lines.append('')
lines.append('########## 汇总（4 天合计，等权、不含费用滑点） ##########')
for k, label in (('same', '当日收盘卖(纸面)'), ('n1o', '次日开盘卖(T+1)'), ('n1c', '次日收盘卖(T+1)')):
    st = stats(overall[k])
    if st:
        lines.append('%-16s n=%-4d 均值%+6.2f%% 中位%+6.2f%% 胜率%5.1f%% 最好%+6.1f%% 最差%+6.1f%%'
                     % (label, st['n'], st['mean'], st['med'], st['win'], st['best'], st['worst']))
        # 复利估算：每天等权全仓
io.open(OUT, 'w', encoding='utf-8').write('\n'.join(lines))
