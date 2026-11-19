#encoding:gbk
# ---------------------------------------------------------------
# QMT auto-sell: close out sellable positions before the close.
# Pairs with the "sell at next-day close" rule from the backtest.
#
#   1. Paste into a NEW Python strategy, Compile
#   2. Start it in the Model Trading module, account YOUR_ACCOUNT
#
# Window default 14:50:00 - 14:56:30, each position sells once.
# SELL_ALL = True   sell every sellable position in the account
#                   (fine for a dedicated simulation account)
# SELL_ALL = False  reserved: only sell what this pipeline bought
#
# ASCII only on purpose: QMT saves .py as GBK and Chinese in the
# source breaks the compile.
# ---------------------------------------------------------------
import datetime

WIN_START = '145000'
WIN_END   = '145630'
SELL_ALL  = True
TAG       = 'autosell'
DRY_RUN   = True        # True: log only, no real orders
PRICE_TYPE = 5          # 5 = latest price
SRV        = 'http://127.0.0.1:8765'
BIG_REPEAT = 200000


class holder():
    pass


A = holder()


def _now():
    return datetime.datetime.now()


def _hm():
    return _now().strftime('%H%M%S')


def _log(msg):
    print('[SELL %s] %s' % (_now().strftime('%H:%M:%S'), msg))


def _hb():
    # one heartbeat per second so the board knows the sell strategy is alive
    A.hb_n += 1
    try:
        urllib.request.urlopen('%s/hb?role=sell&n=%d' % (SRV, A.hb_n), timeout=2).read()
    except Exception:
        pass


def _positions():
    out = []
    try:
        ps = get_trade_detail_data(A.acct, 'STOCK', 'POSITION')
    except Exception as e:
        _log('position query failed: %s' % e)
        return out
    for p in ps:
        try:
            code6 = p.m_strInstrumentID
            mk = getattr(p, 'm_strExchangeID', '') or ('SH' if code6[:1] in ('5', '6', '9') else 'SZ')
            avail = int(getattr(p, 'm_nCanUseVolume', 0) or 0)
            vol = int(getattr(p, 'm_nVolume', 0) or 0)
            if avail > 0:
                out.append(('%s.%s' % (code6, mk), avail, vol))
        except Exception:
            continue
    return out


def _sell(code, vol, ctx):
    msg = 'auto sell %s %d' % (code, vol)
    if DRY_RUN:
        _log('[DRY] would sell %s %d shares' % (code, vol))
        return True
    try:
        passorder(24, 1101, A.acct, code, PRICE_TYPE, -1, vol, TAG, 1, msg, ctx)
        _log('ORDER %s' % msg)
        return True
    except TypeError:
        try:
            passorder(24, 1101, A.acct, code, PRICE_TYPE, -1, vol, ctx)
            _log('ORDER %s (legacy)' % msg)
            return True
        except Exception as e:
            _log('ORDER FAILED %s: %s' % (code, e))
            return False
    except Exception as e:
        _log('ORDER FAILED %s: %s' % (code, e))
        return False


def _tick(ctx):
    try:
        _hb()
        hm = _hm()
        if hm < WIN_START or hm > WIN_END:
            return
        today = _now().strftime('%Y%m%d')
        if A.done_date == today:
            return
        A.done_date = today

        pos = _positions()
        if not pos:
            _log('no sellable position')
            return
        _log('sellable: %s' % ', '.join('%s x%d' % (c, v) for c, v, _ in pos))
        for code, avail, total in pos:
            if DRY_RUN:
                _log('[DRY] %s can sell %d, holding %d' % (code, avail, total))
                continue
            _sell(code, avail, ctx)
    except Exception as e:
        import traceback
        _log('tick error: %s' % e)
        print(traceback.format_exc())


def init(C):
    A.ctx = C
    A.done_date = ''
    A.hb_n = 0
    A.acct = 'testS'
    try:
        A.acct = account
    except Exception:
        pass
    _log('init | window %s-%s | sell_all=%s | dry_run=%s | acct=%s'
         % (WIN_START, WIN_END, SELL_ALL, DRY_RUN, A.acct))
    try:
        key = C.schedule_run(_tick,
                             _now() + datetime.timedelta(seconds=1),
                             BIG_REPEAT,
                             datetime.timedelta(seconds=1),
                             'autosell_1s')
        _log('schedule_run OK key=%s' % key)
    except Exception as e:
        _log('schedule_run FAILED: %s' % e)


def handlebar(C):
    pass
