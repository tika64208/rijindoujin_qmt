# -*- coding: utf-8 -*-
import csv, io, sys
sys.path.insert(0, r'F:\ai\deepseekharness\国金证券模拟账号')
import bid_rules as R
OUT=r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\diag1106.out'
lines=[]
for tag in ['2026-11-05','2026-11-06','2026-11-09','2026-11-10']:
    path=r'F:\ai\deepseekharness\竞价分析\export\竞价数据_%s.csv' % tag
    rows=[R.build_row(r) for r in csv.DictReader(io.open(path,encoding='utf-8-sig',newline=''))]
    band=[r for r in rows if 2.0<=r['bid_change']<=4.0]
    zero=sum(1 for r in rows if r['bid_change']==0)
    probs=[r['app_prob'] for r in rows]
    pick=R.select(rows)
    lines.append('%s: rows=%d bid=0的行=%d 竞价2~4%%=%d 概率max=%d 概率>=60=%d 入选=%d'
                 % (tag,len(rows),zero,len(band),max(probs),sum(1 for p in probs if p>=60),len(pick)))
    # 入选被卡在哪一步
    from collections import Counter
    reasons=Counter()
    for r in rows:
        ok,why=R.matches(r)
        if not ok:
            key=why.split('(')[0].split(' 越界')[0]
            reasons[key]+=1
    top=reasons.most_common(5)
    lines.append('   排除原因Top5: ' + '; '.join('%s=%d'%(k,v) for k,v in top))
io.open(OUT,'w',encoding='utf-8').write('\n'.join(lines))
