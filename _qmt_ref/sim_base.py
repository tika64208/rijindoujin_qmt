# -*- coding: utf-8 -*-
"""对照：全市场随机样本 vs 预设入选，同一买入口径的收益差。"""
import csv, io, os, struct, datetime, sys, random
sys.path.insert(0, r'F:\ai\deepseekharness\国金证券模拟账号')
import bid_rules as R

EXPORT=r'F:\ai\deepseekharness\竞价分析\export'
DATA=r'D:\国金QMT交易端模拟\datadir'
OUT=r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\sim_base.out'
DAYS=['2026-11-05','2026-11-06','2026-11-09','2026-11-10']
SAMPLE=400
random.seed(7)

_cache={}
def bars(code):
    if code in _cache: return _cache[code]
    mk='SH' if code[:1] in ('5','6','9') else 'SZ'
    p=os.path.join(DATA,mk,'86400',code+'.DAT')
    d=None
    if os.path.exists(p):
        try:
            b=open(p,'rb').read(); n=(len(b)-8)//64; d={}
            for k in range(n):
                off=8+k*64
                ts=struct.unpack_from('<i',b,off)[0]
                o,h,l,c=struct.unpack_from('<4i',b,off+4)
                dd=datetime.datetime.utcfromtimestamp(ts+8*3600).date()
                d[dd]=(o/1000.0,c/1000.0)
        except Exception: d=None
    _cache[code]=d
    return d

def nxt(d0,keys):
    later=[x for x in keys if x>d0]
    return min(later) if later else None

def stat(v):
    if not v: return None
    s=sorted(v); n=len(s)
    return (n,sum(s)/n,100.0*sum(1 for x in s if x>0)/n)

lines=[]
tot={'mkt_same':[], 'mkt_n1o':[], 'mkt_n1c':[], 'pick_same':[], 'pick_n1o':[], 'pick_n1c':[]}
for tag in DAYS:
    rows=[R.build_row(r) for r in csv.DictReader(io.open(os.path.join(EXPORT,'竞价数据_%s.csv'%tag),encoding='utf-8-sig',newline=''))]
    d0=datetime.date(*[int(x) for x in tag.split('-')])
    valid=[r for r in rows if r['open']>0]
    sample=random.sample(valid,min(SAMPLE,len(valid)))
    picked=R.select(rows)
    def collect(items):
        same=[]; n1o=[]; n1c=[]
        for r in items:
            bs=bars(r['code'])
            if not bs: continue
            if r['last']>0: same.append((r['last']/r['open']-1)*100)
            n_=nxt(d0,list(bs.keys()))
            if n_:
                n1o.append((bs[n_][0]/r['open']-1)*100)
                n1c.append((bs[n_][1]/r['open']-1)*100)
        return same,n1o,n1c
    ms,m1o,m1c=collect(sample)
    ps,p1o,p1c=collect(picked)
    tot['mkt_same']+=ms; tot['mkt_n1o']+=m1o; tot['mkt_n1c']+=m1c
    tot['pick_same']+=ps; tot['pick_n1o']+=p1o; tot['pick_n1c']+=p1c
    lines.append('%s  样本n=%d  入选n=%d' % (tag,len(sample),len(picked)))
    for lbl,a,b in (('当日收盘',ms,ps),('次日开盘',m1o,p1o),('次日收盘',m1c,p1c)):
        sa=stat(a); sb=stat(b)
        fa='%+6.2f%% (%2.0f%%)' % (sa[1],sa[2]) if sa else '   -   '
        fb='%+6.2f%% (%2.0f%%)' % (sb[1],sb[2]) if sb else '   -   '
        lines.append('   %s  全市场 %s   入选 %s   超额 %s' % (lbl,fa,fb,
                     ('%+6.2f%%' % (sb[1]-sa[1])) if (sa and sb) else '  -  '))
lines.append('')
lines.append('=== 4 天合计（均值 / 胜率） ===')
for lbl,k in (('当日收盘','same'),('次日开盘','n1o'),('次日收盘','n1c')):
    sa=stat(tot['mkt_'+k]); sb=stat(tot['pick_'+k])
    if sa and sb:
        lines.append('%-8s 全市场 %+6.2f%% (%5.1f%%, n=%d)   入选 %+6.2f%% (%5.1f%%, n=%d)   超额 %+6.2f%%'
                     % (lbl, sa[1], sa[2], sa[0], sb[1], sb[2], sb[0], sb[1]-sa[1]))
io.open(OUT,'w',encoding='utf-8').write('\n'.join(lines))
