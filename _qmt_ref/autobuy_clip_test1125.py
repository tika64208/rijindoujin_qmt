#encoding:gbk
# ---------------------------------------------------------------
# QMT strategy: clipboard buy at 09:30 + sell-all at 14:50.
# version 2026-11-24c  (merged sell so nothing has to be started by hand)
#
# Why clipboard: from 2.1.36 the client kills any strategy python
# process that touches the network ([fang wai jie]) and file IO in
# a strategy raises Forbidden fileIO.  ctypes + user32 clipboard is
# the one local channel that still works.
#
# Wire format:  QMTCLIP1|<yyyymmddHHMMSS>|<code,code,...>|<8 hex sig>
#
# Morning : 09:30:00-09:31:30 read clipboard, filter, buy
#            (token only consumed after an order was attempted)
# Afternoon: 14:50:00-14:56:30 sell every sellable (T+1) position
#
# ASCII only: QMT stores .py as GBK.
# ---------------------------------------------------------------
import datetime


STRAT_VERSION = 'TEST-2026-11-25c'
MAGIC     = 'QMTCLIP1'
WIN_START = '093000'
WIN_END   = '145500'
SELL_START = '000000'
SELL_END   = '000001'
AMOUNT    = 100000
FIXED_VOL = 100             # >0: buy this many shares regardless of price (feasibility test)
MAX_BUY   = 5
TAG       = 'jingjia'
TAG_SELL  = 'jingjiasell'
DRY_RUN   = False
TEST_ANYTIME = False
ACC_BT    = 'testS'
BIG_REPEAT = 2000000
HB_EVERY  = 60
RETRY_EVERY = 2.0
T1_GATE   = False           # True: only buy the T1 pattern (limit-up -> pullback -> breakout)
SCAN_COUNT = 200          # daily bars used by the T1 scanner


class holder():
    pass


A = holder()


def _now():
    return datetime.datetime.now()


def _log(msg):
    print('[CLIPBUY %s] %s' % (_now().strftime('%H:%M:%S'), msg))


def _sig(s):
    h = 7
    for ch in s:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return '%08X' % h


def _read_clip():
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.OpenClipboard.restype = wintypes.BOOL
    u32.GetClipboardData.argtypes = [wintypes.UINT]
    u32.GetClipboardData.restype = wintypes.HANDLE
    u32.CloseClipboard.restype = wintypes.BOOL
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = wintypes.LPVOID
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalUnlock.restype = wintypes.BOOL
    if not u32.OpenClipboard(None):
        return None
    try:
        h = u32.GetClipboardData(13)
        if not h:
            return None
        p = k32.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.wstring_at(p)
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


def _norm(codes):
    out = []
    for c in codes:
        c = c.strip().upper()
        if not c:
            continue
        if '.' in c and (c.endswith('.SH') or c.endswith('.SZ')):
            out.append(c)
            continue
        digits = ''.join(ch for ch in c if ch.isdigit())[:6]
        if len(digits) == 6:
            mk = 'SH' if digits[0] in ('5', '6', '9') else 'SZ'
            out.append('%s.%s' % (digits, mk))
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def _parse(text):
    if not text:
        return None, [], 'clipboard empty'
    text = text.strip()
    if not text.startswith(MAGIC + '|'):
        return None, [], 'not a QMTCLIP payload (%d chars)' % len(text)
    parts = text.split('|')
    if len(parts) != 4:
        return None, [], 'bad field count %d' % len(parts)
    _, ts, csv_codes, sig = parts
    if len(ts) != 14 or not ts.isdigit():
        return None, [], 'bad timestamp %r' % ts
    if _sig('%s|%s|%s' % (MAGIC, ts, csv_codes)) != sig.upper():
        return None, [], 'checksum mismatch'
    today = _now().strftime('%Y%m%d')
    if ts[:8] != today:
        return None, [], 'stale payload from %s' % ts[:8]
    codes = _norm(csv_codes.split(','))
    if not codes:
        return None, [], 'payload has no usable code'
    return ts, codes, 'ok'


def _positions():
    out = []
    try:
        ps = get_trade_detail_data(A.acct, 'STOCK', 'POSITION') or []
    except Exception as e:
        _log('position query failed: %s' % e)
        return out
    for p in ps:
        try:
            code6 = getattr(p, 'm_strInstrumentID', '') or ''
            mk = getattr(p, 'm_strExchangeID', '') or ''
            avail = int(getattr(p, 'm_nCanUseVolume', 0) or 0)
            vol = int(getattr(p, 'm_nVolume', 0) or 0)
            if code6 and mk and vol > 0:
                out.append(('%s.%s' % (code6, mk), avail, vol))
        except Exception:
            continue
    return out


def _held_codes():
    return set(c for c, a, v in _positions())



def _bar_price(ctx, code, verbose=False):
    """fallback price when tick is empty: last close of 1d / 1m bar"""
    for period in ('1d', '1m'):
        try:
            d = ctx.get_market_data_ex(['close', 'volume'], [code], period=period, count=1)
            df = d.get(code) if isinstance(d, dict) else None
            if df is not None and len(df) > 0:
                p = float(df['close'].iloc[-1])
                try:
                    v = float(df['volume'].iloc[-1])
                except Exception:
                    v = 1.0
                if p > 0:
                    if verbose:
                        _log('%s tick empty -> %s bar %.2f' % (code, period, p))
                    return p, v
        except Exception as e:
            if verbose:
                _log('%s %s bar failed: %s' % (code, period, e))
    return 0.0, 0.0
def _snapshot(ctx, code):
    last = 0.0
    volume = 0.0
    up = 0.0
    name = ''
    try:
        tk = ctx.get_full_tick([code]).get(code) or {}
        last = float(tk.get('lastPrice') or 0)
        volume = float(tk.get('volume') or 0)
    except Exception as e:
        _log('%s tick failed: %s' % (code, e))
    if last <= 0:
        last, volume = _bar_price(ctx, code, True)
    try:
        name = ctx.get_stock_name(code) or ''
    except Exception:
        pass
    try:
        det = ctx.get_instrument_detail(code) or {}
        if isinstance(det, dict):
            for k in ('UpStopPrice', 'upStopPrice', 'UpStopPirce'):
                if det.get(k):
                    up = float(det[k])
                    break
    except Exception:
        pass
    return last, volume, up, name



# --------------------------------------------------------- T1 pattern gate

def _ma(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _tier(code, closes, highs, lows):
    """0=no data 1=T1 2=T2 3=T3 (port of pattern_filter.evaluate)"""
    n = len(closes)
    if n < 40:
        return 0
    mas = [_ma(closes, k) for k in (5, 10, 15, 20, 25, 30)]
    x30 = []
    for i in range(n):
        if any(m[i] is None for m in mas):
            x30.append(None)
        else:
            x30.append(sum(m[i] for m in mas) / 6.0)
    i = n - 1
    if not x30[i] or x30[i] <= 0:
        return 0
    lim = 0.195 if code[:2] in ('30', '68') else 0.095
    lu = None
    for t in range(max(1, i - 9), i + 1):
        if closes[t - 1] > 0 and closes[t] / closes[t - 1] - 1 >= lim:
            lu = t
    start = lu if lu is not None else max(1, i - 20)
    brk = None
    for t in range(start, i + 1):
        if x30[t] and closes[t] > x30[t]:
            brk = t
            break
    pull = False
    if brk is not None:
        for t in range(brk + 1, i + 1):
            if x30[t] and (lows[t] <= x30[t] * 1.01 or closes[t] <= x30[t]):
                pull = True
                break
    above = closes[i] > x30[i] and closes[i] <= x30[i] * 1.08
    ma_ok = x30[i - 5] is not None and x30[i] >= x30[i - 5] * 0.995
    if lu is not None and brk is not None and pull and above and ma_ok:
        return 1
    if brk is not None and above and ma_ok:
        return 2
    return 3


def _load_bars(ctx, codes, count=SCAN_COUNT):
    out = {}
    try:
        d = ctx.get_market_data_ex(['close', 'high', 'low'], list(codes),
                                   period='1d', count=count)
    except Exception as e:
        _log('get_market_data_ex failed: %s' % e)
        return out
    if not isinstance(d, dict):
        _log('get_market_data_ex returned %s' % type(d).__name__)
        return out
    today = _now().strftime('%Y%m%d')
    for c in codes:
        df = d.get(c)
        if df is None:
            continue
        try:
            closes = [float(v) for v in list(df['close'])]
            highs = [float(v) for v in list(df['high'])]
            lows = [float(v) for v in list(df['low'])]
            idx = [str(v) for v in list(df.index)]
        except Exception:
            continue
        if idx and today in idx[-1].replace('-', ''):
            closes, highs, lows = closes[:-1], highs[:-1], lows[:-1]
        if len(closes) >= 40:
            out[c] = (closes, highs, lows)
    return out


def _t1_filter(ctx, codes, verbose=True):
    bars = _load_bars(ctx, codes)
    t1 = []
    tier_of = {}
    for c in codes:
        b = bars.get(c)
        t = _tier(c, b[0], b[1], b[2]) if b else 0
        tier_of[c] = t
        if t == 1:
            t1.append(c)
    if verbose:
        _log('T1 scan: bars %d/%d, T1=%d%s'
             % (len(bars), len(codes), len(t1),
                (' -> ' + ','.join(t1[:5])) if t1 else ''))
    if not bars and codes:
        _log('T1 scan: no daily bars at all (md api?), gate cannot be applied')
    return t1, bars

# ------------------------------------------------------------------ buy

def _buy(ctx, token, codes, verbose=True):
    if T1_GATE:
        t1, bars = _t1_filter(ctx, codes, verbose)
        if not bars:
            _log('T1 gate: no daily data, fall back to auction list (fail-open)')
        elif not t1:
            _log('T1 gate: no match today -> skip buying')
            return 0, True, 'no_T1'
        else:
            codes = t1
    held = _held_codes()
    ok = []
    for code in codes:
        if code in held:
            if verbose:
                _log('skip %s: already held' % code)
            continue
        last, volume, up, name = _snapshot(ctx, code)
        if last <= 0:
            if verbose:
                _log('skip %s: no price' % code)
            continue
        if volume <= 0:
            if verbose:
                _log('skip %s: suspended (volume 0)' % code)
            continue
        uname = name.upper().replace(' ', '')
        if 'ST' in uname or '\u9000' in name:
            if verbose:
                _log('skip %s: ST/delisting (%s)' % (code, name))
            continue
        if up > 0 and last >= up * 0.999:
            if verbose:
                _log('skip %s: limit up %.2f/%.2f' % (code, last, up))
            continue
        ok.append((code, last, name))
        if len(ok) >= MAX_BUY:
            break

    all_held = bool(codes) and all(c in held for c in codes)
    if not ok:
        if verbose:
            _log('no tradable code yet (held=%d, tries=%d)' % (len(held), A.tries))
        return 0, all_held, ''

    cash = 0.0
    try:
        accs = get_trade_detail_data(A.acct, 'STOCK', 'ACCOUNT')
        if accs:
            cash = float(accs[0].m_dAvailable)
    except Exception as e:
        _log('account query failed: %s' % e)
    _log('buy %d/%d codes, cash=%.0f, token=%s' % (len(ok), len(codes), cash, token))

    ordered = 0
    for code, last, name in ok:
        need = FIXED_VOL * last if FIXED_VOL > 0 else AMOUNT
        if cash > 0 and cash < need:
            _log('stop: cash %.0f < need %.0f' % (cash, need))
            break
        vol = FIXED_VOL if FIXED_VOL > 0 else int(AMOUNT / last / 100) * 100
        if vol < 100:
            _log('skip %s: amount too small for price %.2f' % (code, last))
            continue
        if code.startswith('688') and vol < 200:
            _log('skip %s: STAR board needs >=200 shares' % code)
            continue
        msg = 'clip buy %s %d@%.2f' % (code, vol, last)
        if DRY_RUN:
            _log('[DRY] would buy %s %d @%.2f (%s)' % (code, vol, last, name))
            ordered += 1
        else:
            px = round(last * 1.015, 2)
            try:
                passorder(23, 1101, A.acct, code, 11, px, vol, TAG, 1, msg, ctx)
                _log('ORDER BUY %s limit %.2f' % (msg, px))
                ordered += 1
            except TypeError:
                passorder(23, 1101, A.acct, code, 11, px, vol, ctx)
                _log('ORDER BUY %s (legacy) limit %.2f' % (msg, px))
                ordered += 1
            except Exception as e:
                _log('ORDER BUY FAILED %s: %s' % (code, e))
        if cash > 0:
            cash -= vol * last
    return ordered, all_held, ''


# ----------------------------------------------------------------- sell

def _sell(ctx):
    pos = [p for p in _positions() if p[1] > 0]
    if not pos:
        _log('sell: no sellable position')
        return 0
    _log('sell: %d positions, total avail=%d' % (len(pos), sum(p[1] for p in pos)))
    n = 0
    for code, avail, vol in pos:
        msg = 'clip sell %s %d' % (code, avail)
        if DRY_RUN:
            _log('[DRY] would sell %s %d shares (holding %d)' % (code, avail, vol))
            n += 1
        else:
            try:
                passorder(24, 1101, A.acct, code, 5, -1, avail, TAG_SELL, 1, msg, ctx)
                _log('ORDER SELL %s' % msg)
                n += 1
            except TypeError:
                passorder(24, 1101, A.acct, code, 5, -1, avail, ctx)
                _log('ORDER SELL %s (legacy)' % msg)
                n += 1
            except Exception as e:
                _log('ORDER SELL FAILED %s: %s' % (code, e))
    return n


# ----------------------------------------------------------------- tick

def _tick(ctx):
    try:
        now = _now()
        hm = now.strftime('%H%M%S')
        if now.timestamp() - A.hb_ts >= HB_EVERY:
            A.hb_ts = now.timestamp()
            A.hb_n += 1
            _log('[HB #%d] %s (tok=%s sold=%s)'
                 % (A.hb_n, 'buy-window' if (WIN_START <= hm <= WIN_END) else
                    ('sell-window' if (SELL_START <= hm <= SELL_END) else 'idle'),
                    A.token or '-', A.sold_date or '-'))

        # ---- afternoon: sell all sellable positions, once per day
        if SELL_START <= hm <= SELL_END and A.sold_date != now.strftime('%Y%m%d'):
            A.sold_date = now.strftime('%Y%m%d')
            _sell(ctx)

        # ---- morning: buy from clipboard
        if A.token:
            return
        if not TEST_ANYTIME and (hm < WIN_START or hm > WIN_END):
            return

        text = _read_clip()
        token, codes, why = _parse(text)
        if A.last_seen != text:
            A.last_seen = text
            if token is None:
                _log('ignore clipboard: %s' % why)
            else:
                _log('clipboard payload ok: token=%s n=%d' % (token, len(codes)))
        if token is None or token != A.pending:
            A.pending = token
            A.tries = 0
            A.last_try = 0.0
        if token is None:
            return
        if now.timestamp() - A.last_try < RETRY_EVERY:
            return
        A.last_try = now.timestamp()
        A.tries += 1

        ordered, all_held, note = _buy(ctx, token, codes, verbose=(A.tries <= 2))
        if ordered > 0 or all_held:
            A.token = token
            _log('token %s done: orders=%d all_held=%s note=%s tries=%d'
                 % (token, ordered, all_held, note or '-', A.tries))
        elif A.tries % 15 == 0:
            _log('token %s still waiting, tries=%d' % (token, A.tries))
    except Exception as e:
        import traceback
        _log('tick error: %s' % e)
        print(traceback.format_exc())


def init(C):
    A.hb_n = 0
    A.hb_ts = 0.0
    A.token = ''
    A.pending = ''
    A.last_seen = None
    A.last_try = 0.0
    A.tries = 0
    A.sold_date = ''
    A.acct = ACC_BT
    try:
        A.acct = account
    except Exception:
        pass
    _log('init v%s | buy %s-%s | sell %s-%s | per-stock %.0f | max %d | dry_run=%s | acct=%s'
         % (STRAT_VERSION, WIN_START, WIN_END, SELL_START, SELL_END,
            AMOUNT, MAX_BUY, DRY_RUN, A.acct))
    try:
        pos = _positions()
        _log('positions now: %d (%s)' % (len(pos), ','.join(p[0] for p in pos[:5])))
    except Exception as e:
        _log('position probe failed: %s' % e)
    try:
        token, codes, why = _parse(_read_clip())
        if token:
            _log('clipboard now: token=%s n=%d' % (token, len(codes)))
        else:
            _log('clipboard now: %s' % why)
    except Exception as e:
        _log('clipboard probe failed: %s' % e)
    try:
        tk, cd, wy = _parse(_read_clip())
        if cd:
            _t1_filter(C, cd, True)
    except Exception as e:
        _log('T1 probe failed: %s' % e)
    try:
        key = C.schedule_run(_tick,
                             _now() + datetime.timedelta(seconds=1),
                             BIG_REPEAT,
                             datetime.timedelta(seconds=1),
                             'clipbuy_1s')
        _log('schedule_run OK key=%s' % key)
    except Exception as e:
        _log('schedule_run FAILED: %s' % e)


def handlebar(C):
    pass
