# -*- coding: utf-8 -*-
import csv, io, math
SRC = r'F:\ai\deepseekharness\竞价分析\export\竞价数据_2026-11-05.csv'
OUT = r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\bid_verify2.out'
def f(x,d=0.0):
    try:
        v=float(x); return v if not(math.isnan(v) or math.isinf(v)) else d
    except: return d
def mv_score(mv_yi):
    if mv_yi<30: return 1.0
    if mv_yi<60: return 0.88
    if mv_yi<120: return 0.68
    if mv_yi<250: return 0.45
    return 0.22
def prob_of(bid,turn,warn,mv_yi,base):
    bs = 1.0 if 3.0<=bid<=5.5 else (0.88 if bid>=2 else (0.65 if bid>=1.5 else (0.4 if bid>0 else 0.1)))
    act = 1.0 if turn>=0.8 else (0.88 if turn>=0.4 else (0.72 if turn>=0.2 else (0.5 if turn>=0.08 else (0.3 if turn>0 else 0.1))))
    ws = {5:1.0,4:0.85,3:0.6}.get(int(warn),0.18)
    ms = mv_score(mv_yi)
    mom = 0.9 if 3.0<=base<9.5 else (0.65 if base>=1.0 else (0.4 if base>=0 else (0.25 if base>-3 else 0.15)))
    return max(5,min(95,int(math.floor((bs*0.34+act*0.32+ws*0.17+ms*0.11+mom*0.06)*100+0.5))))
rows=list(csv.DictReader(io.open(SRC,encoding='utf-8-sig',newline='')))
bad=[]
for r in rows:
    bid=f(r['竞价涨幅%']); real=f(r['涨跌幅%']); warn=int(f(r['异动标志'])); mv=f(r['总市值_元'])/1e8
    app=int(f(r['概率']))
    base = bid if bid!=0 else real
    mine=prob_of(bid,0.0,warn,mv,base)
    if mine!=app:
        bad.append((abs(mine-app),r['代码'],r['名称'],bid,warn,mv,mine,app,base))
bad.sort(reverse=True)
out=['mismatch=%d/%d' % (len(bad),len(rows))]
# 分布：市值离阈值多远
near=0
for d,code,name,bid,warn,mv,mine,app,base in bad:
    dist=min(abs(mv-30),abs(mv-60),abs(mv-120),abs(mv-250))
    if dist<3: near+=1
out.append('其中市值距阈值<3亿的: %d (%.0f%%)' % (near, 100.0*near/max(1,len(bad))))
out.append('--- 差异最大的15条 ---')
for d,code,name,bid,warn,mv,mine,app,base in bad[:15]:
    out.append('%s %s bid=%.2f warn=%d mv=%.1f亿 mine=%d app=%d diff=%d' % (code,name,bid,warn,mv,mine,app,mine-app))
# 反推 app 的概率对应哪个市值档
out.append('--- 按 app 概率反推所需市值档 ---')
cnt={}
for d,code,name,bid,warn,mv,mine,app,base in bad:
    for i,thr in enumerate([30,60,120,250,9999]):
        for mvtest in ([15,45,90,180,400][i],):
            if prob_of(bid,0.0,warn,mvtest,base)==app:
                cnt[thr]=cnt.get(thr,0)+1
                break
out.append(str(cnt))
io.open(OUT,'w',encoding='utf-8').write('\n'.join(out))
