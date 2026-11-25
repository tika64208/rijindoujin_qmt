# -*- coding: utf-8 -*-
"""把 App 库里的 37 天 bid_data 导成 CSV（字段名与 App 导出完全一致），
   顺便看一眼 daily_bars 的字段与覆盖范围。"""
import io
import os
import sqlite3
import traceback

DB = r'F:\ai\deepseekharness\国金证券模拟账号\_data_20261124\databases\momentum.db'
OUTDIR = r'F:\ai\deepseekharness\国金证券模拟账号\_data_20261124\export'
REPORT = r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\export_report.out'

HEADERS = {
    "code": "代码", "date": "交易日期", "name": "名称", "latestPrice": "最新价",
    "realChange": "涨跌幅%", "openPrice": "开盘价", "volume": "成交量_手", "amount": "成交额_元",
    "turnover": "换手率%", "circMv": "总市值_元", "bidChange": "竞价涨幅%", "warnFlag": "异动标志",
    "industry": "行业", "conceptQuick": "概念", "probability": "概率", "confidence": "可信度",
    "score": "评分", "bidTurnover": "竞价换手率_内部值", "entityChange": "实体涨幅%",
    "warnText": "异动文本", "reason": "入选理由", "savedAt": "快照时间", "excluded": "是否被排除",
    "excludeReason": "排除原因", "quoteAt": "报价时间_Unix毫秒", "bidVolume": "估算竞价量",
}

lines = []


def log(s):
    lines.append(s)
    io.open(REPORT, 'w', encoding='utf-8').write('\n'.join(lines))


try:
    import csv
    if not os.path.isdir(OUTDIR):
        os.makedirs(OUTDIR)
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # ---- daily_bars 结构
    cols = [r[1] for r in cur.execute('PRAGMA table_info(daily_bars)')]
    log('daily_bars cols: %s' % ', '.join(cols))
    try:
        n, c1 = cur.execute('select count(*), count(distinct code) from daily_bars').fetchone()
        log('daily_bars rows=%d codes=%d' % (n, c1))
        rng = cur.execute('select min(date), max(date) from daily_bars').fetchone()
        log('daily_bars date range: %s .. %s' % rng)
        sample = cur.execute('select * from daily_bars limit 2').fetchall()
        log('daily_bars sample: %s' % (sample,))
    except Exception as e:
        log('daily_bars stats ERR %s' % e)

    # ---- 导出 bid_data
    bcols = [r[1] for r in cur.execute('PRAGMA table_info(bid_data)')]
    dates = [r[0] for r in cur.execute('select distinct date from bid_data order by date')]
    total = 0
    for d in dates:
        rows = cur.execute('select %s from bid_data where date=? order by probability desc, code'
                           % ','.join(bcols), (d,)).fetchall()
        path = os.path.join(OUTDIR, '竞价数据_%s.csv' % d)
        with io.open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow([HEADERS.get(k, k) for k in bcols])
            for r in rows:
                w.writerow(['' if v is None else v for v in r])
        total += len(rows)
        if len(dates) <= 5 or d >= '2026-11-18':
            log('%s -> %d rows' % (d, len(rows)))
    log('exported %d days, %d rows -> %s' % (len(dates), total, OUTDIR))
except Exception:
    log('EXC:\n' + traceback.format_exc())
