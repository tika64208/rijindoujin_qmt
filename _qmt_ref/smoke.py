# -*- coding: utf-8 -*-
import os, sys, time, random, traceback, importlib.util
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'smoke.out')
log = open(OUT, 'w', encoding='utf-8')
import builtins
builtins.print = lambda *a, **k: log.write(' '.join(str(x) for x in a) + '\n')

def load():
    src = os.path.join(HERE, '..', '周线KDJ回测.py')
    txt = open(src, encoding='utf-8').read().replace('#coding:gbk', '#coding:utf-8', 1)
    p = os.path.join(HERE, 'smoke_strategy.py')
    open(p, 'w', encoding='utf-8').write(txt)
    spec = importlib.util.spec_from_file_location('smoke', p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

CODES = ['600000.SH', '600001.SH', '000001.SZ', '000002.SZ']
DATES = [d.strftime('%Y%m%d') for d in pd.date_range('2020-01-03', periods=150, freq='W-FRI')]

rnd = random.Random(7)
W = {}
for c in CODES:
    px, rows = 10.0, []
    for _ in DATES:
        px = max(1.0, px * (1 + rnd.gauss(0.002, 0.06)))
        rows.append((px * 1.01, px * 0.99, px))
    W[c] = pd.DataFrame(rows, columns=['high', 'low', 'close'], index=DATES[:len(rows)])

class Env(object):
    def __init__(s): s.cash=1000000.0; s.pos={}; s.trades=[]; s.rej=[]; s.price={}; s.bar=0
    def passorder(s, op, ot, acc, code, pt, price, vol, C):
        px = s.price.get(code)
        if not px: s.rej.append((code,'noprice')); return
        if op == 23:
            sh = int(float(vol)/px/100)*100
            if sh < 100 or sh*px > s.cash: s.rej.append((code,'cash')); return
            s.cash -= sh*px; s.pos[code] = s.pos.get(code,0)+sh; s.trades.append((s.bar,'B',code,sh))
        elif op == 24:
            sh = min(int(vol), s.pos.get(code,0))
            if sh <= 0: s.rej.append((code,'nopos')); return
            s.cash += sh*px; s.pos[code] -= sh
            if s.pos[code] <= 0: del s.pos[code]
            s.trades.append((s.bar,'S',code,sh))

class Acct(object):
    def __init__(s, tot, av): s.m_dBalance=tot; s.m_dAvailable=av
class Pos(object):
    def __init__(s, code, vol):
        s.m_strInstrumentID, s.m_strExchangeID = code.split('.')
        s.m_nVolume=vol; s.m_nCanUseVolume=vol; s.m_dOpenPrice=10.0

class Ctx(object):
    def __init__(s, env): s.env=env; s.barpos=0; s.stockcode='600000'; s.market='SH'
    def get_bar_timetag(s, i): return int(time.mktime(time.strptime(DATES[i], '%Y%m%d'))*1000)
    def get_stock_list_in_sector(s, name): return list(CODES)
    def set_universe(s, lst): pass
    def get_market_data_ex(s, fields, codes, period='1w', count=-1, **kw):
        return {c: W[c].iloc[:s.barpos+1].tail(count if count and count>0 else None) for c in codes}
    def paint(s, *a, **k): pass

def get_trade_detail_data(acc, typ, kind):
    e = ENV
    if kind == 'ACCOUNT':
        return [Acct(e.cash + sum(v*e.price.get(c,0) for c,v in e.pos.items()), e.cash)]
    return [Pos(c, v) for c, v in e.pos.items()]

try:
    m = load(); ENV = Env()
    m.passorder = ENV.passorder; m.get_trade_detail_data = get_trade_detail_data
    m.timetag_to_datetime = lambda ms, fmt: time.strftime(fmt, time.localtime(ms/1000))
    m.STOCK_POOL = list(CODES); m.MAX_HOLD = 2
    ctx = Ctx(ENV); m.init(ctx)
    for i in range(len(DATES)):
        ctx.barpos = i; ENV.bar = i
        ENV.price = {c: float(W[c]['close'].iloc[i]) for c in CODES}
        m.handlebar(ctx)
    log.write('bars=%d trades=%d rejects=%d cash=%.0f pos=%d\n'
              % (len(DATES), len(ENV.trades), len(ENV.rej), ENV.cash, len(ENV.pos)))
    log.write('rej=%s\n' % ENV.rej[:3])
    log.write('SMOKE OK\n')
except Exception:
    log.write(traceback.format_exc())
finally:
    log.close()

