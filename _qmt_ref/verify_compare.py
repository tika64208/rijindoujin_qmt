# -*- coding: utf-8 -*-
"""对比：今天买的 8 只 vs 重跑多出来的 11 只，现在各自涨了多少。"""
import io
import urllib.request

W = r'F:\ai\deepseekharness\国金证券模拟账号'
PICKED = ['002298', '002403', '603960', '000017', '001337', '688343', '002077', '000062']
EXTRA = ['300314', '301687', '603373', '603358', '603687', '605058', '300788', '601999',
         '603068', '301363', '300738']
NAMES = {}


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
            out[key] = (f[0], float(f[2] or 0), float(f[3] or 0), float(f[1] or 0))
    return out


q = sina(PICKED + EXTRA)
lines = []


def block(title, codes):
    tot = 0.0
    lines.append(title)
    lines.append('%-8s %-10s %8s %8s %8s' % ('code', 'name', 'prev', 'last', 'chg%'))
    for c in codes:
        if c not in q:
            lines.append('%s missing' % c)
            continue
        name, prev, last, op = q[c]
        chg = (last / prev - 1) * 100 if prev else 0
        tot += chg
        lines.append('%-8s %-10s %8.2f %8.2f %7.2f%%' % (c, name, prev, last, chg))
    lines.append('平均涨幅: %.2f%%' % (tot / len(codes) if codes else 0))
    lines.append('')


block('【今天实际买入的 8 只】', PICKED)
block('【重跑多出来的 11 只（当时没选）】', EXTRA)
io.open(W + r'\out\verify_compare.txt', 'w', encoding='utf-8').write('\n'.join(lines))
