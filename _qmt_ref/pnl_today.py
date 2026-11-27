# -*- coding: utf-8 -*-
"""收盘核算：8 只持仓的真实市值/盈亏 + 今天卖掉的两只的已实现盈亏。"""
import io
import urllib.request

HOLD = [('603960', 400, 21.174), ('688343', 200, 45.579), ('000017', 1800, 5.222),
        ('000062', 500, 17.191), ('001337', 200, 33.062), ('002077', 700, 13.182),
        ('002298', 1300, 7.333), ('002403', 1000, 9.360)]
SOLD = [('300434', 100, 11.011), ('301569', 100, 16.373)]


def sina(codes):
    q = ','.join(('sh' if c[0] in '56' else 'sz') + c for c in codes)
    req = urllib.request.Request('https://hq.sinajs.cn/list=' + q,
                                 headers={'User-Agent': 'Mozilla/5.0',
                                          'Referer': 'https://finance.sina.com.cn/'})
    t = urllib.request.urlopen(req, timeout=10).read().decode('gbk', 'ignore')
    out = {}
    for line in t.strip().split('\n'):
        if '="' not in line:
            continue
        head, rest = line.split('="', 1)
        key = head.split('_')[-1][2:]
        f = rest.split('",')[0].split(',')
        if len(f) >= 32:
            out[key] = (f[0], float(f[2] or 0), float(f[3] or 0))
    return out


q = sina([c for c, _, _ in HOLD] + [c for c, _, _ in SOLD])
L = []
L.append('%-8s %-10s %6s %8s %8s %10s %9s %8s' %
         ('code', 'name', 'qty', 'cost', 'close', 'value', 'pnl', 'pct'))
L.append('-' * 78)
tc = tv = 0.0
for c, n, cost in HOLD:
    name, prev, last = q.get(c, ('?', 0, 0))
    px = last or prev
    v = px * n
    tc += cost * n
    tv += v
    L.append('%-8s %-10s %6d %8.3f %8.2f %10.2f %9.2f %7.2f%%' %
             (c, name, n, cost, px, v, v - cost * n, (px / cost - 1) * 100))
L.append('-' * 78)
L.append('%-8s %-10s %6d %8s %8s %10.2f %9.2f %7.2f%%' %
         ('合计', '', sum(n for _, n, _ in HOLD), '', '', tv, tv - tc,
          (tv / tc - 1) * 100))
L.append('')
L.append('今日卖出（已实现）:')
real = 0.0
for c, n, cost in SOLD:
    name, prev, last = q.get(c, ('?', 0, 0))
    px = last or prev
    pnl = (px - cost) * n
    real += pnl
    L.append('  %-8s %-10s %d 股  成本 %.3f  收盘 %.2f  盈亏 %+.2f' % (c, name, n, cost, px, pnl))
L.append('  已实现合计 %+.2f' % real)
L.append('')
L.append('持仓浮动 %+.2f + 已实现 %+.2f = 今日总盈亏 %+.2f' % (tv - tc, real, tv - tc + real))
io.open(r'F:\ai\deepseekharness\国金证券模拟账号\out\today_pnl.txt', 'w',
        encoding='utf-8').write('\n'.join(L))
