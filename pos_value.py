# -*- coding: utf-8 -*-
"""
pos_value.py -- 用 QMT 策略日志里的持仓快照 + 新浪实时行情，算真实市值/盈亏。

用法：
    python pos_value.py            # 最新一天
    python pos_value.py 20261127   # 指定日期

说明：QMT 持仓页的"最新价"不订阅行情，常年显示昨收；本脚本绕开它，
      直接拿新浪实时价重算，并和昨收对比。
"""
import io
import os
import re
import sys
import urllib.request

LOGDIR = r'D:\国金QMT交易端模拟\userdata\log'
POS_RE = re.compile(r'pos: (\d{6})\.(\w{2}) (\d+) ([\d.]+)')


def latest_log(day=None):
    files = sorted(f for f in os.listdir(LOGDIR)
                   if f.startswith('XtClient_FormulaOutput_') and f.endswith('.log'))
    if not files:
        return None
    if day:
        want = 'XtClient_FormulaOutput_%s.log' % day
        return os.path.join(LOGDIR, want) if want in files else None
    return os.path.join(LOGDIR, files[-1])


def parse_positions(path):
    """取最后一个 snap 块之前的 pos: 行"""
    if not path or not os.path.exists(path):
        return []
    lines = io.open(path, 'r', encoding='utf-8', errors='replace').read().split('\n')
    last = -1
    for i, ln in enumerate(lines):
        if 'snap ' in ln and 'positions' in ln:
            last = i
    if last < 0:
        return []
    out = []
    j = last - 1
    while j >= 0:
        m = POS_RE.search(lines[j])
        if m:
            code, mk, vol, cost = m.groups()
            out.append((code + '.' + mk, int(vol), float(cost)))
        elif 'pos:' in lines[j]:
            pass
        elif out:
            break
        j -= 1
    return list(reversed(out))


def sina_quotes(codes):
    if not codes:
        return {}
    q = ','.join(('sh' if c.endswith('.SH') else 'sz') + c[:6] for c in codes)
    url = 'https://hq.sinajs.cn/list=' + q
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                               'Referer': 'https://finance.sina.com.cn/'})
    text = urllib.request.urlopen(req, timeout=10).read().decode('gbk', 'ignore')
    out = {}
    for line in text.strip().split('\n'):
        if '="' not in line:
            continue
        head, rest = line.split('="', 1)
        key = head.split('_')[-1]
        if key[:2] in ('sh', 'sz'):
            key = key[2:]
        f = rest.split('",')[0].split(',')
        if len(f) < 32:
            continue
        out[key] = {'name': f[0], 'prev': float(f[2] or 0), 'last': float(f[3] or 0)}
    return out


def main():
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass
    day = sys.argv[1] if len(sys.argv) > 1 else None
    path = latest_log(day)
    pos = parse_positions(path)
    if not pos:
        print('没有找到持仓快照：%s' % path)
        print('（策略需要 v2026-11-27d 以上，init 时会打 pos: 行）')
        return 2

    quotes = sina_quotes([p[0] for p in pos])
    print('log: %s' % os.path.basename(path))
    print('%-11s %-9s %6s %8s %8s %10s %9s %7s' %
          ('代码', '名称', '股数', '成本', '现价', '市值', '盈亏', '比例'))
    print('-' * 76)
    tot_cost = tot_val = 0.0
    for code, vol, cost in pos:
        q = quotes.get(code[:6], {})
        last = q.get('last') or 0.0
        name = q.get('name', '')
        val = last * vol
        pnl = (last - cost) * vol if last else 0.0
        tot_cost += cost * vol
        tot_val += val
        print('%-11s %-9s %6d %8.3f %8.2f %10.2f %9.2f %6.2f%%' %
              (code, name, vol, cost, last, val, pnl,
               ((last / cost - 1) * 100) if cost else 0))
    print('-' * 76)
    print('%-11s %-9s %6d %8s %8s %10.2f %9.2f %6.2f%%' %
          ('合计', '', sum(p[1] for p in pos), '', '', tot_val,
           tot_val - tot_cost, ((tot_val / tot_cost - 1) * 100) if tot_cost else 0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
