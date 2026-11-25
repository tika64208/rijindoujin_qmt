# -*- coding: utf-8 -*-
import struct, datetime, io, csv
OUT=r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\calib.out'
CSV=r'F:\ai\deepseekharness\竞价分析\export\竞价数据_2026-11-10.csv'
def load_dat(path):
    b=open(path,'rb').read()
    n=(len(b)-8)//64
    out=[]
    for k in range(n):
        off=8+k*64
        ts=struct.unpack_from('<i',b,off)[0]
        o,h,l,c=struct.unpack_from('<4i',b,off+4)
        d=datetime.datetime.utcfromtimestamp(ts+8*3600).date()
        out.append((d,o,h,l,c))
    return out
want={}
for r in csv.DictReader(io.open(CSV,encoding='utf-8-sig',newline='')):
    want[r['代码']]=(r['名称'],float(r['开盘价'] or 0),float(r['最新价'] or 0))
lines=[]
for code,path in [('300400',r'D:\国金QMT交易端模拟\datadir\SZ\86400\300400.DAT'),
                  ('300626',r'D:\国金QMT交易端模拟\datadir\SZ\86400\300626.DAT'),
                  ('600000',r'D:\国金QMT交易端模拟\datadir\SH\86400\600000.DAT')]:
    try:
        bars=load_dat(path)
    except Exception as e:
        lines.append('%s DAT read fail: %s' % (code,e)); continue
    d0=datetime.date(2026,11,10)
    hit=[b for b in bars if b[0]==d0]
    if not hit:
        lines.append('%s no 2026-11-10, last=%s' % (code,bars[-1][0])); continue
    bar=hit[0]
    name,op,last=want.get(code,('-',0,0))
    lines.append('%s %s | DAT o=%.0f c=%.0f | CSV open=%.2f last=%.2f | ratio_o=%.4f ratio_c=%.4f'
                 % (code,name,bar[1],bar[4],op,last,bar[1]/max(op,1e-9),bar[4]/max(last,1e-9)))
lines.append('SZ last date: %s' % load_dat(r'D:\国金QMT交易端模拟\datadir\SZ\86400\300400.DAT')[-1][0])
lines.append('SH last date: %s' % load_dat(r'D:\国金QMT交易端模拟\datadir\SH\86400\600000.DAT')[-1][0])
io.open(OUT,'w',encoding='utf-8').write('\n'.join(lines))
