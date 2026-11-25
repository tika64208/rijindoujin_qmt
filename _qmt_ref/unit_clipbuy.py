# -*- coding: utf-8 -*-
"""单元测试 autobuy_clip 的 _tick/_run 逻辑（不依赖 QMT 引擎）。
   - 第一次没有行情：不应消费 token，应打 skip 日志
   - 第二次有行情：应产生 3 张 DRY 单，并消费 token
   - 第三次：token 已消费，直接返回
"""
import io
import sys

W = r'F:\ai\deepseekharness\国金证券模拟账号'
sys.path.insert(0, W)
import autobuy_clip as S

buf = io.StringIO()
old = sys.stdout
sys.stdout = buf


class Ctx(object):
    def __init__(self, with_price):
        self.with_price = with_price

    def get_full_tick(self, codes):
        if not self.with_price:
            return {c: {} for c in codes}
        return {c: {'lastPrice': p, 'volume': 10000}
                for c, p in zip(codes, (12.34, 10.75, 21.70))}

    def get_stock_name(self, code):
        return {'000001.SZ': '平安银行', '600000.SH': '浦发银行',
                '300209.SZ': '行云科技'}.get(code, '')

    def get_instrument_detail(self, code):
        return {'UpStopPrice': 99.0}

    def schedule_run(self, *a, **k):
        return 1


class Acc(object):
    def __init__(self):
        self.m_dAvailable = 10000000.0


def fake_trade_detail(acct, kind, what):
    if what == 'ACCOUNT':
        return [Acc()]
    if what == 'POSITION':
        return []
    return []


def run_once(ctx, label):
    buf.write('\n--- %s ---\n' % label)
    S._tick(ctx)
    buf.write('token_after=%r tries=%d\n' % (S.A.token, S.A.tries))


def main():
    S.get_trade_detail_data = fake_trade_detail
    S.A.acct = '63009312'
    S.A.hb_n = 0
    S.A.hb_ts = 0.0
    S.A.token = ''
    S.A.last_seen = None
    S.A.last_try = 0.0
    S.A.tries = 0
    S.DRY_RUN = True
    S.TEST_ANYTIME = True
    S.RETRY_EVERY = 0.0          # 测试里不等待

    payload = S.build_payload_if_missing() if hasattr(S, 'build_payload_if_missing') else None
    body = '%s|%s|%s' % (S.MAGIC, S._now().strftime('%Y%m%d%H%M%S'),
                         '000001.SZ,600000.SH,300209.SZ')
    payload = '%s|%s' % (body, S._sig(body))

    S._read_clip = lambda: payload

    run_once(Ctx(with_price=False), '1st tick, no quotes')
    run_once(Ctx(with_price=True), '2nd tick, quotes ready')
    run_once(Ctx(with_price=True), '3rd tick, token already used')

    # 持仓去重：把 3 只都当已持有
    S.A.token = ''
    S.A.last_seen = None
    S.A.tries = 0
    S._held_codes = lambda: set(['000001.SZ', '600000.SH', '300209.SZ'])
    run_once(Ctx(with_price=True), '4th tick, already held -> done')
    sys.stdout = old
    io.open(W + r'\_qmt_ref\unit_clipbuy.out', 'w', encoding='utf-8').write(buf.getvalue())


main()
