# -*- coding: utf-8 -*-
"""
bid_fetch.py -- 全自动第一棒：直接拉东财竞价快照 -> 套预设 -> 写剪贴板。

这样就彻底不需要「手机 App 导出 CSV」这一步了：
    09:25:20  东财 push2dycalc 全市场快照（5,565 行，字段与 App 完全一致）
              -> bid_rules.build_row / select（和 App 同一套公式）
              -> 写剪贴板 QMTCLIP1|ts|codes|sig
    09:30:00  QMT 策略「竞价剪贴板买入」读到 -> 过滤 -> 下单

为什么用东财：QMT 自己没有 f630「异动」字段（占概率权重 17%、可信度 +10），
东财有这个字段，而且 App 本来就是从这儿取的数（见 EastmoneyBidDataSource.kt）。

用法：
    python bid_fetch.py                 # 抓一次，写剪贴板，守护到 09:31:30
    python bid_fetch.py --dry           # 只打印，不写剪贴板
    python bid_fetch.py --once --top 3  # 单次，取 3 只（测试）
    python bid_fetch.py --watch --until 093130

计划任务：每天 09:25:20 跑 `bid_fetch.py --watch`。
"""
import argparse
import datetime
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bid_rules as R
import clip_push as C
import pattern_filter as P

BASE = 'https://push2dycalc.eastmoney.com/api/qt/clist/get'
FIELDS = 'f2,f3,f4,f5,f6,f8,f10,f12,f14,f17,f18,f20,f100,f102,f103,f124,f615,f630'
TOKEN = 'c92c50e6b0fab2c17cd5e276e9a79c42'
FS = 'm:1+t:2,m:0+t:6,m:0+t:80,m:1+t:23'      # 沪主板 + 深主板 + 创业板 + 科创板
AUDIT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'


def _num(row, key, default=0.0):
    v = row.get(key)
    if v is None or v in ('-', '', '−'):
        return default
    try:
        return float(v)
    except Exception:
        return default


def fetch_json(timeout=12):
    q = {'pn': '1', 'pz': '6000', 'po': '1', 'np': '1', 'fltt': '2', 'invt': '2',
         'fid': 'f3', 'fs': FS, 'fields': FIELDS, 'ut': TOKEN}
    url = BASE + '?' + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Referer': 'https://quote.eastmoney.com/',
        'Cache-Control': 'no-cache',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'ignore')


def to_rows(text):
    j = json.loads(text)
    if j.get('rc') not in (0, None):
        raise RuntimeError('东财返回 rc=%s' % j.get('rc'))
    data = j.get('data') or {}
    diff = data.get('diff') or []
    if not diff:
        raise RuntimeError('东财返回空列表')
    rows = []
    for r in diff:
        raw = {
            '代码': str(r.get('f12', '')).strip().zfill(6),
            '名称': r.get('f14', '') or '',
            '最新价': _num(r, 'f2'),
            '涨跌幅%': _num(r, 'f3'),
            '开盘价': _num(r, 'f17') or _num(r, 'f2'),
            '成交量_手': _num(r, 'f5'),
            '成交额_元': _num(r, 'f6'),
            '换手率%': _num(r, 'f8'),
            '总市值_元': _num(r, 'f20'),
            '竞价涨幅%': _num(r, 'f615'),
            '异动标志': int(_num(r, 'f630')),
        }
        rows.append(R.build_row(raw))
    return rows, data.get('total')


def audit(rows, picked, payload, attempts, total, extra=None):
    try:
        if not os.path.isdir(AUDIT_DIR):
            os.makedirs(AUDIT_DIR)
        tag = datetime.datetime.now().strftime('%Y%m%d')
        out = os.path.join(AUDIT_DIR, 'fetch_%s.json' % tag)
        obj = {
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_rows': total or len(rows),
            'attempts': attempts,
            'payload': payload,
            'picked': [{'code': r['code'], 'name': r['name'],
                        'bid': r['bid_change'], 'real': r['real_change'],
                        'warn': r['warn'], 'prob': r['prob'], 'conf': r['conf'],
                        'score': r['score'], 'mv_yi': round(r['mv_yi'], 1),
                        'open': r['open']} for r in picked],
        }
        if extra:
            obj.update(extra)
        io.open(out, 'w', encoding='utf-8').write(json.dumps(obj, ensure_ascii=False, indent=2))
        return out
    except Exception as e:
        print('[fetch] 审计写入失败: %s' % e)
        return None


def save_snapshot(rows, cands):
    """把当次全量快照落盘，供盘后复盘（选股结果不可精确复现，必须留原始数据）"""
    try:
        if not os.path.isdir(AUDIT_DIR):
            os.makedirs(AUDIT_DIR)
        tag = datetime.datetime.now().strftime('%Y%m%d')
        out = os.path.join(AUDIT_DIR, 'snap_%s.csv' % tag)
        picked = set(c['code'] for c in cands)
        with io.open(out, 'w', encoding='utf-8-sig', newline='') as fh:
            fh.write('code,name,bid_change,real_change,open,prob,conf,score,mv_yi,'
                     'warn,selected\n')
            for r in rows:
                fh.write('%s,%s,%.2f,%.2f,%.2f,%d,%d,%d,%.1f,%s,%d\n'
                         % (r['code'], r['name'], r['bid_change'], r['real_change'],
                            r['open'], r['prob'], r['conf'], r['score'], r['mv_yi'],
                            r['warn'], 1 if r['code'] in picked else 0))
        print('[fetch] 快照已存: %s (%d 行)' % (out, len(rows)))
        return out
    except Exception as e:
        print('[fetch] 快照写入失败: %s' % e)
        return None


def _hm():
    return datetime.datetime.now().strftime('%H%M%S')


def prefetch_klines(codes, workers=6):
    """并发拉日线进缓存，返回 {code: ok}"""
    ok = {}

    def one(c):
        try:
            P.cached_kline(c)
            return c, True
        except Exception:
            return c, False

    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for c, good in ex.map(one, codes):
                ok[c] = good
    except Exception as e:
        print('[fetch] 并发拉日线失败: %s' % e)
        for c in codes:
            ok.setdefault(c, False)
    return ok


def evaluate_pool(pool, today_str):
    st_all, fail = [], 0
    for r in pool:
        st = None
        try:
            bars = P.cached_kline(r['code'])
            st = P.eval_at_date(bars, r['code'], today_str)
        except Exception:
            st = None
        if not st:
            fail += 1
            st = {'tier': 9, 'dist': 0.0, 'lu': False, 'pull': False}
        st_all.append((r, st))
    return {
        'T1': [(r, s) for r, s in st_all if s['tier'] == 1],
        'T2': [(r, s) for r, s in st_all if s['tier'] == 2],
        'T3': [(r, s) for r, s in st_all if s['tier'] not in (1, 2)],
        'fail': fail,
        'coverage': 1.0 - (fail / float(len(pool))) if pool else 0.0,
        'all': st_all,
    }


def _by_quality(pairs):
    return [r for r, s in sorted(pairs, key=lambda x: (-x[0]['score'], -x[0]['prob']))]


def _show(pairs, limit=5):
    for r, s in pairs[:limit]:
        print('  %-8s %-10s score=%-3d prob=%-3d 距线=%+.1f%% 涨停=%s 回踩=%s 上穿=%s'
              % (r['code'], r['name'][:8], r['score'], r['prob'],
                 s.get('dist', 0) * 100, 'Y' if s.get('lu') else 'n',
                 'Y' if s.get('pull') else 'n', 'Y' if s.get('cross') else 'n'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=5)
    ap.add_argument('--no-pattern', action='store_true', help='只用竞价排序，不做形态分层')
    ap.add_argument('--gate', choices=('t1', 'rank'), default='t1', help='t1=只买 T1，没有就空仓；rank=分层排序')
    ap.add_argument('--pool', type=int, default=50, help='推多少只候选给 QMT 做 T1 筛选')
    ap.add_argument('--workers', type=int, default=6, help='并发拉日线的线程数')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--no-snapshot', dest='snapshot', action='store_false', help='不保存全量快照')
    ap.set_defaults(snapshot=True)
    ap.add_argument('--watch', action='store_true')
    ap.add_argument('--until', default='093130')
    ap.add_argument('--retry-until', default='092830')
    ap.add_argument('--settle-until', default='092512', help='这个时间之前即使有结果也重抓一次')
    ap.add_argument('--every', type=float, default=10.0)
    args = ap.parse_args()

    # 提前启动也没关系：等到 09:25:00 再抓，保证拿到最终竞价结果
    if args.watch and _hm() < '092500':
        target = datetime.datetime.now().replace(hour=9, minute=25, second=0, microsecond=0)
        gap = (target - datetime.datetime.now()).total_seconds()
        if gap > 0:
            print('[fetch] %s 启动，等 %.0f 秒到 09:25:00 再抓' % (_hm(), gap))
            time.sleep(gap)

    attempts = 0
    rows, picked, total, stats = [], [], 0, {}
    deadline = args.retry_until
    gate_note = ''
    while True:
        attempts += 1
        try:
            text = fetch_json()
            rows, total = to_rows(text)
            cands = R.select(rows)
            if args.snapshot:
                save_snapshot(rows, cands)
            print('[fetch] 第%d次：%s 行 -> 竞价入选 %d 只'
                  % (attempts, total or len(rows), len(cands)))

            # 形态闸门放在 QMT 策略里（本地日线、不走网络，见 v2026-11-24d）；
            # 这里按竞价评分顺序推前 N 只，策略自己筛 T1，没有 T1 就空仓。
            pool_n = args.pool if args.pool > 0 else len(cands)
            picked = cands[:pool_n]
            gate_note = 'pool-%d' % len(picked)
            print('[fetch] 推 %d 只候选（评分降序），T1 闸门由 QMT 策略判定' % len(picked))
            _show([(r, {}) for r in picked], min(5, len(picked)))

            # 09:25:00 刚过时东财快照往往只落定一部分（我们 11-27 就只拿到 8 只，
            # 10 秒后同一接口能给出 18 只）。这里强制等到 settle_until 再抓一次。
            if picked and _hm() < args.settle_until:
                target = datetime.datetime.now().replace(
                    hour=int(args.settle_until[:2]), minute=int(args.settle_until[2:4]),
                    second=int(args.settle_until[4:6]), microsecond=0)
                gap = (target - datetime.datetime.now()).total_seconds()
                if gap > 0:
                    print('[fetch] 本轮命中 %d 只，但数据可能未落定，等 %.0f 秒重抓' % (len(picked), gap))
                    time.sleep(gap)
                    continue

            if picked:
                print(R.fmt_table(picked))
                break
        except Exception as e:
            print('[fetch] 第%d次失败：%s' % (attempts, e))

        if args.once or not picked and (_hm() > deadline):
            break
        if picked:
            break
        time.sleep(args.every)

    if not picked:
        print('[fetch] 结束：没有可推送的名单（空仓日 / 无 T1 / 数据源异常）')
        if rows:
            audit(rows, [], '', attempts, total,
                  extra={'decision': gate_note or 'none',
                         't1': len(stats.get('T1', [])),
                         't2': len(stats.get('T2', [])),
                         't3': len(stats.get('T3', [])),
                         'coverage': round(stats.get('coverage', 0.0), 3)})
        return 0 if rows else 2

    codes = [r['qmt_code'] for r in picked]
    payload = C.build_payload(codes)
    print('[fetch] 载荷: %s' % payload)
    audit(rows, picked, payload, attempts, total,
          extra={'decision': gate_note,
                 't1': len(stats.get('T1', [])),
                 't2': len(stats.get('T2', [])),
                 't3': len(stats.get('T3', [])),
                 'coverage': round(stats.get('coverage', 0.0), 3)})
    if args.dry:
        return 0

    C.set_clipboard(payload)
    back = C.get_clipboard()
    print('[fetch] 回读: %s%s' % (back, '' if back == payload else '  <-- 不一致!'))

    if args.watch:
        print('[fetch] 守护：每 %.0f 秒对齐一次，直到 %s' % (args.every, args.until))
        try:
            while _hm() <= args.until:
                time.sleep(args.every)
                if C.get_clipboard() != payload:
                    C.set_clipboard(payload)
        except KeyboardInterrupt:
            pass
        print('[fetch] 守护结束')
    return 0


if __name__ == '__main__':
    sys.exit(main())
