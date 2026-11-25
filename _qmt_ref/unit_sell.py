# -*- coding: utf-8 -*-
"""单元测试 _sell：DRY 与实单分支、部分可用、无持仓。"""
import io
import sys

W = r'F:\ai\deepseekharness\国金证券模拟账号'
sys.path.insert(0, W)
import autobuy_clip as S

buf = io.StringIO()
old = sys.stdout
sys.stdout = buf


class P(object):
    def __init__(self, code, mk, vol, avail):
        self.m_strInstrumentID = code
        self.m_strExchangeID = mk
        self.m_nVolume = vol
        self.m_nCanUseVolume = avail


def make_detail(pos):
    def f(acct, kind, what):
        if what == 'POSITION':
            return pos
        if what == 'ACCOUNT':
            return []
        return []
    return f


calls = []


def fake_passorder(*args):
    calls.append(args)


def run(label, positions, dry):
    global calls
    calls = []
    S.get_trade_detail_data = make_detail(positions)
    S.passorder = fake_passorder
    S.DRY_RUN = dry
    S.A.acct = '63009312'
    buf.write('\n--- %s (dry=%s) ---\n' % (label, dry))
    n = S._sell(None)
    buf.write('sold_count=%d passorder_calls=%d\n' % (n, len(calls)))
    for c in calls:
        buf.write('  call: %s\n' % (c,))


run('two positions, partly available', [P('000001', 'SZ', 1000, 600),
                                        P('600000', 'SH', 500, 0)], True)
run('two positions, real orders', [P('000001', 'SZ', 1000, 600),
                                   P('600000', 'SH', 500, 300)], False)
run('no position', [], False)

sys.stdout = old
io.open(W + r'\_qmt_ref\unit_sell.out', 'w', encoding='utf-8').write(buf.getvalue())
