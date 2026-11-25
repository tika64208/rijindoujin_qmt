#encoding:gbk
# ---------------------------------------------------------------
# QMT single-stock backtest: MA crossover, last 3 years
#
#   1. Model Research -> +New Strategy -> Python Strategy
#   2. Paste this file, Ctrl+S, click Compile, click Backtest
#
# Why this version is fast: the daily closes are fetched ONCE in
# init() and cached in memory. Each handlebar() call just advances a
# pointer and slices the list, instead of calling get_market_data_ex
# 900+ times (which rebuilds a pandas DataFrame every bar and is very
# slow on QMT's pandas 0.22).
#
# This file is pure ASCII on purpose: QMT saves .py as GBK while many
# editors assume UTF-8, so Chinese comments show up garbled.
# ---------------------------------------------------------------

# ========================== settings ==========================
STOCK  = '000001.SZ'            # stock to backtest
FAST   = 5                      # fast MA period
SLOW   = 20                     # slow MA period
AMOUNT = 100000                 # cash per buy (CNY)
START  = '2023-01-01 00:00:00'  # backtest start (~3 years)
END    = '2026-11-17 15:00:00'  # backtest end
ACC_BT = 'testS'                # backtest account in QMT
TAG    = 'MA_BT'
PRELOAD = 2000                  # bars cached in init (2000 > 3 years)
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
    if A.diag_n < 8:
        A.diag_n += 1
        print('[MA][diag] %s' % msg)


def _load_series(C):
    """Return (dates[int], closes[float]) of daily bars, newest last."""
    # 1) get_history_data: the API QMT's own dual-MA sample uses
    try:
        data = C.get_history_data(PRELOAD, '1d', 'close', dividend_type='front_ratio')
        if isinstance(data, dict):
            seq = data.get(A.stock)
            if seq is None and len(data) == 1:
                seq = list(data.values())[0]
            if seq is not None and len(seq) > 0:
                closes = [float(v) for v in seq]
                _diag('get_history_data ok: %d closes, last %.2f' % (len(closes), closes[-1]))
                return None, closes      # dates unknown here, detected later
    except Exception as e:
        _diag('get_history_data failed: %s' % e)

    # 2) get_market_data_ex gives an indexed DataFrame -> real dates
    for kw in ({'dividend_type': 'front', 'fill_data': False}, {}):
        try:
            data = C.get_market_data_ex(['close'], [A.stock], period='1d', count=PRELOAD, **kw)
        except TypeError:
            continue
        except Exception as e:
            _diag('get_market_data_ex failed: %s' % e)
            continue
        df = (data or {}).get(A.stock)
        if df is not None and len(df) > 0:
            closes = [float(v) for v in df['close'].tolist()]
            dates = []
            for x in list(df.index):
                s = ''.join(ch for ch in str(x) if ch.isdigit())
                dates.append(int(s[:8]) if len(s) >= 8 else 0)
            _diag('get_market_data_ex ok: %d bars, dates %s..%s'
                  % (len(closes), dates[0], dates[-1]))
            return dates, closes
        _diag('get_market_data_ex empty, keys=%s' % (list((data or {}).keys())[:3],))
    return None, []


def _bar_date(C):
    """Current bar date as int YYYYMMDD, or 0 if unknown."""
    try:
        tt = C.get_bar_timetag(C.barpos)
        s = timetag_to_datetime(tt, '%Y%m%d')
        return int(''.join(ch for ch in s if ch.isdigit())[:8])
    except Exception:
        return 0


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
    A.err_shown = False
    A.ptr = 0
    try:
        C.start = START
        C.end = END
    except Exception:
        pass
    try:
        C.set_universe([A.stock])
    except Exception:
        pass

    dates, closes = _load_series(C)
    A.dates = dates
    A.closes = closes
    if A.dates is not None:
        _diag('cached with dates, will slice by bar date')
    elif A.closes:
        _diag('cached without dates, will slice by bar index')

    print('[MA] %s  MA%d/MA%d  %s ~ %s  cash %.0f  cached %d bars  account %s'
          % (A.stock, FAST, SLOW, START[:10], END[:10], AMOUNT, len(A.closes), A.acct))


def _window(C):
    """Closes up to and including the current bar."""
    if not A.closes:
        return []
    if A.dates:
        d = _bar_date(C)
        if d > 0:
            while A.ptr < len(A.dates) and A.dates[A.ptr] <= d:
                A.ptr += 1
            return A.closes[:A.ptr]
    # no dates available: index by barpos (cache is aligned to the end)
    n = min(len(A.closes), C.barpos + 1)
    return A.closes[:n]


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
    closes = _window(C)
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
