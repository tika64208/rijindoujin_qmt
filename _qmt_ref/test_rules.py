# -*- coding: utf-8 -*-
import csv, io, sys
sys.path.insert(0, r'F:\ai\deepseekharness\国金证券模拟账号')
import bid_rules as R
SRC=r'F:\ai\deepseekharness\竞价分析\export\竞价数据_2026-11-05.csv'
OUT=r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\test_rules.out'
rows=[R.build_row(r) for r in csv.DictReader(io.open(SRC,encoding='utf-8-sig',newline=''))]
band=[r for r in rows if 2.0<=r['bid_change']<=4.0]
def rate(rs,f):
    ok=sum(1 for r in rs if f(r))
    return 100.0*ok/max(1,len(rs))
lines=[]
lines.append('total=%d band=%d' % (len(rows),len(band)))
lines.append('band 概率命中 %.1f%%  评分命中 %.1f%%' % (rate(band,lambda r:r['prob']==r['app_prob']),rate(band,lambda r:r['score']==r['app_score'])))
lines.append('all  概率命中 %.1f%%  评分命中 %.1f%%' % (rate(rows,lambda r:r['prob']==r['app_prob']),rate(rows,lambda r:r['score']==r['app_score'])))
sel=R.select(rows,top_n=8)
lines.append('')
lines.append('预设选出 %d 只（展示前8）:' % len(R.select(rows)))
lines.append(R.fmt_table(sel))
for r in R.select(rows)[:8]:
    ok,why=R.matches(r)
    lines.append('  %s %s prob=%d score=%d mx=%.1f' % (r['code'],r['name'],r['prob'],r['score'],r['mv_yi']))
io.open(OUT,'w',encoding='utf-8').write('\n'.join(lines))
