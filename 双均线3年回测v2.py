#encoding:gbk
# ---------------------------------------------------------------
# QMT single-stock backtest: MA crossover, last 3 years
#
#   1. Model Research -> +New Strategy -> Python Strategy
#   2. Paste this file, Ctrl+S, click Compile
#   3. Click Backtest, read the "Backtest Return" panel
#
# Data call tries get_history_data() first (the API QMT's own dual-MA
# sample uses) and falls back to get_market_data_ex(). A one-time
# diagnostic line shows whether data actually arrived.
# ---------------------------------------------------------------
import numpy as np

# ========================== settings ==========================
STOCK  = '000001.SZ'            # stock to backtest
FAST   = 5                      # fast MA period
SLOW   = 20                     # slow MA period
AMOUNT = 100000                 # cash per buy (CNY)
START  = '2023-01-01 00:00:00'  # backtest start (~3 years)
END    = '2026-11-17 15:00:00'  # backtest end
ACC_BT = 'testS'                # backtest account in QMT
TAG    = 'MA_BT'
# ==============================================================


class holder():
    pass


A = holder()


def _ma(arr, n):
    if len(arr) < n:
        return None
    return sum(arr[-n:]) / float(n)


def _order(op, vol, msg, C):
    try:
        passorder(op, 1101, A.acct, A.stock, 5, -1, vol, TAG, 1, msg, C)
    except TypeError:
        passorder(op, 1101, A.acct, A.stock, 5, -1, vol, C)


def _diag(msg):
    if A.diag_n < 6:
        A.diag_n += 1
        print('[MA][diag] %s' % msg)


def _closes_hist(C, n):
    # QMT's own dual-MA sample uses this API, so try it first
    try:
        data = C.get_history_data(n, '1d', 'close', dividend_type='front_ratio')
    except Exception as e:
        _diag('get_history_data failed: %s' % e)
        return []
    if not isinstance(data, dict):
        _diag('get_history_data returned %s' % type(data))
        return []
    seq = data.get(A.stock)
    if seq is None and len(data) == 1:
        seq = list(data.values())[0]
    if seq is None:
        _diag('get_history_data keys=%s' % (list(data.keys())[:3],))
        return []
    return [float(v) for v in seq]


def _closes_mde(C, n):
    data = None
    try:
        data = C.get_market_data_ex(['close'], [A.stock], period='1d', count=n,
                                    dividend_type='front', fill_data=False)
    except TypeError:
        try:
            data = C.get_market_data_ex(['close'], [A.stock], period='1d', count=n)
        except Exception as e:
            _diag('get_market_data_ex failed: %s' % e)
            return []
    except Exception as e:
        _diag('get_market_data_ex failed: %s' % e)
        return []
    df = (data or {}).get(A.stock)
    if df is None or len(df) == 0:
        _diag('get_market_data_ex empty, keys=%s' % (list((data or {}).keys())[:3],))
        return []
    return [float(v) for v in df['close'].tolist()]


def _get_close(C, n):
    cl = _closes_hist(C, n)
    if len(cl) >= SLOW:
        if not A.src:
            A.src = 'get_history_data'
            _diag('data ok: %d bars, last close %.2f (source=get_history_data)' % (len(cl), cl[-1]))
        return cl
    cl = _closes_mde(C, n)
    if len(cl) >= SLOW and not A.src:
        A.src = 'get_market_data_ex'
        _diag('data ok: %d bars, last close %.2f (source=get_market_data_ex)' % (len(cl), cl[-1]))
    return cl


def _pos_vol(C):
    try:
        ps = get_trade_detail_data(A.acct, 'STOCK', 'POSITION')
    except Exception:
        return 0
    code6 = A.stock.split('.')[0]
    total = 0
    for p in ps:
        if p.m_strInstrumentID == code6:
            total += int(p.m_nCanUseVolume)
    return total


def init(C):
    A.stock = STOCK
    A.acct = ACC_BT
    A.buy_n = 0
    A.sell_n = 0
    A.diag_n = 0
    A.src = ''
    A.err_shown = False
    try:
        C.start = START
        C.end = END
    except Exception:
        pass
    try:
        C.set_universe([A.stock])
    except Exception:
        pass
    print('[MA] %s  MA%d/MA%d  %s ~ %s  cash per buy %.0f  account %s'
          % (A.stock, FAST, SLOW, START[:10], END[:10], AMOUNT, A.acct))


def handlebar(C):
    try:
        _handlebar(C)
    except Exception as e:
        if not A.err_shown:
            A.err_shown = True
            import traceback
            print('[MA][error] %s' % e)
            print(traceback.format_exc())


def _handlebar(C):
    need = SLOW + 2
    closes = _get_close(C, need + 5)
    if len(closes) < need:
        return

    price = closes[-1]
    fast_now = _ma(closes, FAST)
    slow_now = _ma(closes, SLOW)
    fast_pre = sum(closes[-FAST - 1:-1]) / float(FAST)
    slow_pre = sum(closes[-SLOW - 1:-1]) / float(SLOW)
    hold = _pos_vol(C)

    golden = fast_pre <= slow_pre and fast_now > slow_now
    death = fast_pre >= slow_pre and fast_now < slow_now

    if golden and hold == 0:
        vol = int(AMOUNT / price / 100) * 100
        if vol >= 100:
            _order(23, vol, 'MA golden cross buy', C)
            A.buy_n += 1
            print('[MA] BUY  %s %d shares @%.2f  MA%d=%.2f up MA%d=%.2f  (#%d)'
                  % (A.stock, vol, price, FAST, fast_now, SLOW, slow_now, A.buy_n))
    elif death and hold > 0:
        _order(24, hold, 'MA death cross sell', C)
        A.sell_n += 1
        print('[MA] SELL %s %d shares @%.2f  MA%d=%.2f down MA%d=%.2f  (#%d)'
              % (A.stock, hold, price, FAST, fast_now, SLOW, slow_now, A.sell_n))
