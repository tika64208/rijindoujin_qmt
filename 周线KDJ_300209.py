#encoding:gbk
# ---------------------------------------------------------------
# QMT weekly-KDJ backtest for a single stock (300209.SZ)
#
#   1. Model Research -> +New Strategy -> Python Strategy
#   2. Paste this file, Ctrl+S, click Compile, click Backtest
#
# How it works
#   - init(): daily OHLC fetched ONCE (PRELOAD bars) and cached.
#   - handlebar(): slices the cache up to the current bar, folds the
#     daily bars into ISO weeks, then computes KDJ(9,3,3) on the
#     weekly series. Weekly bars are rebuilt from daily data, so the
#     strategy does NOT depend on QMT's '1w' period being available.
#   - Buy : weekly KDJ golden cross AND K < BUY_K, flat position.
#   - Sell: weekly KDJ death cross, holding position.
#
# ASCII only on purpose: QMT saves .py as GBK, most editors assume
# UTF-8, so Chinese comments would show up garbled.
# ---------------------------------------------------------------

# ========================== settings ==========================
STOCK   = '300209.SZ'           # stock to backtest
KDJ_N   = 9                     # RSV lookback (weeks)
BUY_K   = 35.0                  # only buy when K is below this
AMOUNT  = 100000                # cash per buy (CNY)
START   = '2023-01-01 00:00:00' # backtest start (data starts 2025-01)
END     = '2026-11-17 15:00:00' # backtest end
ACC_BT  = 'testS'               # backtest account in QMT
TAG     = 'WKDJ'
PRELOAD = 2000                  # daily bars cached in init
MIN_WEEKS = KDJ_N + 5           # need this many weeks before trading
# ==============================================================


class holder():
    pass


A = holder()


def _diag(msg):
    if A.diag_n < 10:
        A.diag_n += 1
        print('[WKDJ][diag] %s' % msg)


def _iso_key(d):
    """(year, week) of an int date YYYYMMDD"""
    y, m, dd = d // 10000, (d // 100) % 100, d % 100
    try:
        import datetime
        return datetime.date(y, m, dd).isocalendar()[:2]
    except Exception:
        return (0, 0)


def _load(C):
    """Cache daily ohlc; returns (dates, highs, lows, closes) or (None, [], [], [])."""
    for kw in ({'dividend_type': 'front', 'fill_data': False}, {}):
        try:
            data = C.get_market_data_ex(['high', 'low', 'close'], [A.stock],
                                        period='1d', count=PRELOAD, **kw)
        except TypeError:
            continue
        except Exception as e:
            _diag('get_market_data_ex failed: %s' % e)
            continue
        df = (data or {}).get(A.stock)
        if df is None or len(df) == 0:
            _diag('empty frame, keys=%s' % (list((data or {}).keys())[:3],))
            continue
        cols = list(df.columns)
        if 'high' not in cols or 'low' not in cols or 'close' not in cols:
            _diag('unexpected columns: %s' % (cols,))
            continue
        dates, highs, lows, closes = [], [], [], []
        for x, h, l, c in zip(list(df.index), df['high'].tolist(),
                              df['low'].tolist(), df['close'].tolist()):
            s = ''.join(ch for ch in str(x) if ch.isdigit())
            dates.append(int(s[:8]) if len(s) >= 8 else 0)
            highs.append(float(h))
            lows.append(float(l))
            closes.append(float(c))
        _diag('cached %d daily bars: %s .. %s' % (len(closes), dates[0], dates[-1]))
        return dates, highs, lows, closes
    return None, [], [], []


def _bar_date(C):
    try:
        s = timetag_to_datetime(C.get_bar_timetag(C.barpos), '%Y%m%d')
        return int(''.join(ch for ch in s if ch.isdigit())[:8])
    except Exception:
        return 0


def _ptr_for(C):
    """how many cached daily bars are visible at the current bar"""
    if not A.closes:
        return 0
    d = _bar_date(C)
    if d > 0 and A.dates:
        while A.ptr < len(A.dates) and A.dates[A.ptr] <= d:
            A.ptr += 1
        return A.ptr
    return min(len(A.closes), C.barpos + 1)


def _weekly(upto):
    """fold cached daily bars into ISO weeks: [[key, high, low, close], ...]"""
    rows = []
    for i in range(upto):
        key = _iso_key(A.dates[i])
        if rows and rows[-1][0] == key:
            if A.highs[i] > rows[-1][1]:
                rows[-1][1] = A.highs[i]
            if A.lows[i] < rows[-1][2]:
                rows[-1][2] = A.lows[i]
            rows[-1][3] = A.closes[i]
        else:
            rows.append([key, A.highs[i], A.lows[i], A.closes[i]])
    return rows


def _kdj(weeks):
    """KDJ(9,3,3) on weekly bars -> list of (k, d, j)"""
    out = []
    k = d = 50.0
    for i in range(len(weeks)):
        lo = max(0, i - KDJ_N + 1)
        hh = max(w[1] for w in weeks[lo:i + 1])
        ll = min(w[2] for w in weeks[lo:i + 1])
        c = weeks[i][3]
        rsv = 50.0 if hh == ll else (c - ll) / float(hh - ll) * 100.0
        k = (2.0 * k + rsv) / 3.0
        d = (2.0 * d + k) / 3.0
        out.append((k, d, 3.0 * k - 2.0 * d))
    return out


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


def _order(op, vol, msg, C):
    try:
        passorder(op, 1101, A.acct, A.stock, 5, -1, vol, TAG, 1, msg, C)
    except TypeError:
        passorder(op, 1101, A.acct, A.stock, 5, -1, vol, C)


def init(C):
    A.stock = STOCK
    A.acct = ACC_BT
    A.buy_n = 0
    A.sell_n = 0
    A.diag_n = 0
    A.ptr = 0
    A.err_shown = False
    A.last_week = None
    try:
        C.start = START
        C.end = END
    except Exception:
        pass
    try:
        C.set_universe([A.stock])
    except Exception:
        pass
    A.dates, A.highs, A.lows, A.closes = _load(C)
    print('[WKDJ] %s  KDJ(%d,3,3)  buy K<%.0f  %s ~ %s  cash %.0f  cached %d bars  account %s'
          % (A.stock, KDJ_N, BUY_K, START[:10], END[:10], AMOUNT, len(A.closes), A.acct))


def handlebar(C):
    try:
        _handlebar(C)
    except Exception as e:
        if not A.err_shown:
            A.err_shown = True
            import traceback
            print('[WKDJ][error] %s' % e)
            print(traceback.format_exc())


def _handlebar(C):
    upto = _ptr_for(C)
    if upto < KDJ_N * 7:
        return
    weeks = _weekly(upto)
    if len(weeks) < MIN_WEEKS:
        return
    if A.last_week == weeks[-1][0]:
        return                       # one decision per week
    A.last_week = weeks[-1][0]

    kdj = _kdj(weeks)
    k1, d1, j1 = kdj[-2]
    k2, d2, j2 = kdj[-1]
    hold = _pos_vol(C)
    price = weeks[-1][3]

    golden = k1 <= d1 and k2 > d2
    death = k1 >= d1 and k2 < d2

    if golden and k2 < BUY_K and hold == 0:
        vol = int(AMOUNT / price / 100) * 100
        if vol >= 100:
            _order(23, vol, 'WKDJ golden cross buy', C)
            A.buy_n += 1
            print('[WKDJ] BUY  %s %d @%.2f  K=%.1f D=%.1f  week=%s  (#%d)'
                  % (A.stock, vol, price, k2, d2, weeks[-1][0], A.buy_n))
    elif death and hold > 0:
        _order(24, hold, 'WKDJ death cross sell', C)
        A.sell_n += 1
        print('[WKDJ] SELL %s %d @%.2f  K=%.1f D=%.1f  week=%s  (#%d)'
              % (A.stock, hold, price, k2, d2, weeks[-1][0], A.sell_n))
