# -*- coding: utf-8 -*-
import csv, io, math
SRC=r'F:\ai\deepseekharness\竞价分析\export\竞价数据_2026-11-05.csv'
OUT=r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\bid_verify3.out'
def f(x,d=0.0):
    try:
        v=float(x); return v if not(math.isnan(v) or math.isinf(v)) else d
    except: return d
def mv_band(mv):
    return 0 if mv<30 else (1 if mv<60 else (2 if mv<120 else (3 if mv<250 else 4)))
MV=[1.0,0.88,0.68,0.45,0.22]
def prob_of(bid,turn,warn,mv,base):
    bs=1.0 if 3.0<=bid<=5.5 else (0.88 if bid>=2 else (0.65 if bid>=1.5 else (0.4 if bid>0 else 0.1)))
    act=1.0 if turn>=0.8 else (0.88 if turn>=0.4 else (0.72 if turn>=0.2 else (0.5 if turn>=0.08 else (0.3 if turn>0 else 0.1))))
    ws={5:1.0,4:0.85,3:0.6}.get(int(warn),0.18)
    mom=0.9 if 3.0<=base<9.5 else (0.65 if base>=1.0 else (0.4 if base>=0 else (0.25 if base>-3 else 0.15)))
    ms=MV[mv_band(mv)]
    return max(5,min(95,int(math.floor((bs*0.34+act*0.32+ws*0.17+ms*0.11+mom*0.06)*100+0.5))))
rows=list(csv.DictReader(io.open(SRC,encoding='utf-8-sig',newline='')))
ok=0; bad=[]; near_thr=0
for r in rows:
    bid=f(r['竞价涨幅%']); real=f(r['涨跌幅%']); warn=int(f(r['异动标志']))
    mv=f(r['总市值_元'])/1e8; vol=f(r['成交量_手']); op=f(r['开盘价']); last=f(r['最新价'])
    px=op if op>0 else last
    turn = (vol*px/(mv*1e8*100.0)) if (mv>0 and vol>0) else 0.0
    base = bid if bid!=0 else real
    app=int(f(r['概率'])); mine=prob_of(bid,turn,warn,mv,base)
    if mine==app:
        ok+=1
    else:
        dist=min(abs(mv-30),abs(mv-60),abs(mv-120),abs(mv-250))
        rel=dist/max(mv,1e-9)
        if rel<0.06: near_thr+=1
        bad.append([r['代码'],r['名称'],bid,warn,round(mv,1),mine,app,mine-app,round(rel*100,1)])
out=['total=%d ok=%d (%.1f%%) mismatch=%d' % (len(rows),ok,100.0*ok/len(rows),len(bad))]
out.append('其中市值距阈值<6%%的: %d / %d = %.0f%%' % (near_thr,len(bad),100.0*near_thr/max(1,len(bad))))
out.append('--- 差异与市值档位无关的样本 10 条 ---')
shown=0
for b in bad:
    if b[8]>=6.0 and shown<10:
        out.append('%s %s bid=%.2f warn=%d mv=%.1f mine=%d app=%d diff=%d (距阈值%.1f%%)' % (b[0],b[1],b[2],b[3],b[4],b[5],b[6],b[7],b[8]))
        shown+=1
io.open(OUT,'w',encoding='utf-8').write('\n'.join(out))
