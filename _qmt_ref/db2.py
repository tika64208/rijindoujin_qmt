# -*- coding: utf-8 -*-
"""daily_bars 覆盖范围 + sim_backtest_report 摘要。"""
import io
import json
import sqlite3

DB = r'F:\ai\deepseekharness\国金证券模拟账号\_data_20261124\databases\momentum.db'
OUT = r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\db2.out'
RPT = r'F:\ai\deepseekharness\国金证券模拟账号\_data_20261124\files\sim_backtest_report.json'

out = []
con = sqlite3.connect(DB)
cur = con.cursor()
n, s = cur.execute('select count(*), count(distinct symbol) from daily_bars').fetchone()
rng = cur.execute('select min(date), max(date) from daily_bars').fetchone()
out.append('daily_bars rows=%d symbols=%d range=%s..%s' % (n, s, rng[0], rng[1]))
top = cur.execute('select symbol, count(*) c from daily_bars group by symbol order by c desc limit 3').fetchall()
out.append('most bars: %s' % (top,))
low = cur.execute('select symbol, count(*) c from daily_bars group by symbol order by c asc limit 3').fetchall()
out.append('fewest bars: %s' % (low,))
out.append('sample: %s' % (cur.execute('select * from daily_bars where symbol=? order by date desc limit 2',
                                        (top[0][0],)).fetchall(),))
try:
    j = json.load(io.open(RPT, 'r', encoding='utf-8'))
    if isinstance(j, dict):
        out.append('report keys: %s' % ', '.join(list(j.keys())[:15]))
        for k in list(j.keys())[:6]:
            v = j[k]
            out.append('  %s = %s' % (k, str(v)[:160]))
    else:
        out.append('report type %s len %d' % (type(j).__name__, len(j)))
except Exception as e:
    out.append('report ERR %s' % e)
con.close()
io.open(OUT, 'w', encoding='utf-8').write('\n'.join(out))
