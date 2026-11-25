#encoding:gbk
# ---------------------------------------------------------------
# SELL strategy, NO NETWORK version (pairs with autobuy_sector.py)
#
# Closes out sellable positions in the 14:50 window.
# Heartbeat is printed into the QMT log, no network needed.
# ---------------------------------------------------------------
import datetime

WIN_START = '145000'
WIN_END   = '145630'
TAG       = 'autosell'
DRY_RUN   = True
PRICE_TYPE = 5
HB_EVERY  = 30
BIG_REPEAT = 200000


class holder():
    pass


A = holder()


def _now():
    return datetime.datetime.now()


def _log(msg):
    print('[SELL %s] %s' % (_now().strftime('%H:%M:%S'), msg))


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
        now = _now()
        if now.timestamp() - A.hb_ts >= HB_EVERY:
            A.hb_ts = now.timestamp()
            A.hb_n += 1
            _log('[HB sell %s #%d]' % (now.strftime('%H:%M:%S'), A.hb_n))

        hm = now.strftime('%H%M%S')
        if hm < WIN_START or hm > WIN_END:
            return
        today = now.strftime('%Y%m%d')
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
    A.hb_n = 0
    A.hb_ts = 0.0
    A.done_date = ''
    A.acct = 'testS'
    try:
        A.acct = account
    except Exception:
        pass
    _log('init | window %s-%s | dry_run=%s | acct=%s' % (WIN_START, WIN_END, DRY_RUN, A.acct))
    try:
        key = C.schedule_run(_tick,
                             _now() + datetime.timedelta(seconds=1),
                             BIG_REPEAT,
                             datetime.timedelta(seconds=1),
                             'autosell_sector_1s')
        _log('schedule_run OK key=%s' % key)
    except Exception as e:
        _log('schedule_run FAILED: %s' % e)


def handlebar(C):
    pass