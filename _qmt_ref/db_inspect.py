# -*- coding: utf-8 -*-
"""检查 App 数据库：表、bid_data 的日期与行数、字段。"""
import io
import os
import sqlite3
import traceback

DB = r'F:\ai\deepseekharness\国金证券模拟账号\_data_20261124\databases\momentum.db'
OUT = r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\db_inspect.out'

out = []


def log(s):
    out.append(s)
    io.open(OUT, 'w', encoding='utf-8').write('\n'.join(out))


try:
    log('started; db exists=%s size=%d' % (os.path.exists(DB), os.path.getsize(DB)))
    con = sqlite3.connect(DB)
    cur = con.cursor()
    tabs = [r[0] for r in cur.execute("select name from sqlite_master where type='table'")]
    log('tables: ' + ', '.join(tabs))

    cols = [r[1] for r in cur.execute('PRAGMA table_info(bid_data)')]
    log('bid_data cols(%d): %s' % (len(cols), ', '.join(cols)))

    for t in tabs:
        try:
            n = cur.execute('select count(*) from "%s"' % t).fetchone()[0]
            log('  %s rows=%d' % (t, n))
        except Exception as e:
            log('  %s ERR %s' % (t, e))

    rows = cur.execute('select date,count(*) from bid_data group by date order by date').fetchall()
    log('bid_data days(%d):' % len(rows))
    for d, n in rows:
        log('  %s  %d' % (d, n))
    con.close()
except Exception:
    log('EXC:\n' + traceback.format_exc())
