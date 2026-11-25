# -*- coding: utf-8 -*-
import csv, io, math
SRC=r'F:\ai\deepseekharness\竞价分析\export\竞价数据_2026-11-05.csv'
OUT=r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\bid_verify4.out'
def f(x,d=0.0):
    try:
        v=float(x); return v if not(math.isnan(v) or math.isinf(v)) else d
    except: return d
MV=[1.0,0.88,0.68,0.45,0.22]
def band(mv): return 0 if mv<30 else (1 if mv<60 else (2 if mv<120 else (3 if mv<250 else 4)))
def prob_of(bid,turn,warn,mv,base):
    bs=1.0 if 3.0<=bid<=5.5 else (0.88 if bid>=2 else (0.65 if bid>=1.5 else (0.4 if bid>0 else 0.1)))
    act=1.0 if turn>=0.8 else (0.88 if turn>=0.4 else (0.72 if turn>=0.2 else (0.5 if turn>=0.08 else (0.3 if turn>0 else 0.1))))
    ws={5:1.0,4:0.85,3:0.6}.get(int(warn),0.18)
    mom=0.9 if 3.0<=base<9.5 else (0.65 if base>=1.0 else (0.4 if base>=0 else (0.25 if base>-3 else 0.15)))
    return max(5,min(95,int(math.floor((bs*0.34+act*0.32+ws*0.17+MV[band(mv)]*0.11+mom*0.06)*100+0.5))))
def score_of(bid,real,warn,bvol):
    ch = bid if bid!=0 else real
    s1=max(0.0,min(bid/9.0,1.0))*50
    s2=max(0.0,min(ch/10.0,1.0))*20
    s3=20.0 if warn==5 else (16.0 if warn==4 else (10.0 if bid>=4 else 0.0))
    s4=max(0.0,min(bvol/200000.0,1.0))*10
    return max(0,min(100,int(math.floor(s1+s2+s3+s4+0.5))))
rows=list(csv.DictReader(io.open(SRC,encoding='utf-8-sig',newline='')))
for lo,hi,label in [(2.0,4.0,'预设区间 2~4%'),(0,-999,'全样本')]:
    tot=okp=oks=0
    for r in rows:
        bid=f(r['竞价涨幅%'])
        if lo!=0 and not (lo<=bid<=hi): continue
        real=f(r['涨跌幅%']); warn=int(f(r['异动标志'])); mv=f(r['总市值_元'])/1e8
        vol=f(r['成交量_手']); op=f(r['开盘价']); last=f(r['最新价']); px=op if op>0 else last
        turn=(vol*px/(mv*1e8*100.0)) if (mv>0 and vol>0) else 0.0
        base=bid if bid!=0 else real
        tot+=1
        if prob_of(bid,turn,warn,mv,base)==int(f(r['概率'])): okp+=1
        if score_of(bid,real,warn,int(f(r['估算竞价量'])))==int(f(r['评分'])): oks+=1
    print_line='%s: n=%d 概率命中 %.1f%% 评分命中 %.1f%%' % (label,tot,100.0*okp/max(1,tot),100.0*oks/max(1,tot))
    io.open(OUT,'a',encoding='utf-8').write(print_line+'\n')
