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


STRAT_VERSION = '2026-11-27h'
MAGIC     = 'QMTCLIP1'
WIN_START = '092632'
WIN_END   = '093130'
SELL_START = '145000'
SELL_END   = '145630'
AMOUNT    = 10000
FIXED_VOL = 0
GAP_MAX   = 0.05           # buy limit = prev_close*(1+GAP_MAX), capped by up-limit
MAX_BUY   = 10
TAG       = 'jingjia'
TAG_SELL  = 'jingjiasell'
DRY_RUN   = False          # False: real orders
DRY_SELL  = False          # False: sell real positions when the sell window opens
TEST_ANYTIME = False
ACC_BT    = 'testS'
BIG_REPEAT = 2000000
HB_EVERY  = 60
RETRY_EVERY = 2.0
SELL_EVERY  = 15.0          # retry interval inside the sell window
T1_FIRST  = True           # True: sort T1 (limit-up -> pullback -> breakout) to the front, rest still bought
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


def _snap(tag):
    """log one line per held position: pos: CODE qty cost"""
    try:
        ps = get_trade_detail_data(A.acct, 'STOCK', 'POSITION') or []
    except Exception as e:
        _log('snap failed: %s' % e)
        return 0
    n = 0
    for p in ps:
        try:
            code6 = getattr(p, 'm_strInstrumentID', '') or ''
            mk = getattr(p, 'm_strExchangeID', '') or ''
            vol = int(getattr(p, 'm_nVolume', 0) or 0)
            cost = float(getattr(p, 'm_dOpenPrice', 0) or 0)
            if code6 and mk and vol > 0:
                _log('pos: %s.%s %d %.3f' % (code6, mk, vol, cost))
                n += 1
        except Exception:
            continue
    _log('snap %s: %d positions' % (tag, n))
    return n

def _cash():
    try:
        accs = get_trade_detail_data(A.acct, 'STOCK', 'ACCOUNT') or []
        for a in accs:
            v = getattr(a, 'm_dAvailable', None)
            if v is not None:
                return float(v)
    except Exception as e:
        _log('cash query failed: %s' % e)
    return 0.0



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

def _prev_close(ctx, code):
    """last completed daily bar close (today's bar is dropped by _load_bars)"""
    bars = _load_bars(ctx, [code], 80, min_bars=2)
    b = bars.get(code)
    if not b or len(b[0]) < 2:
        return 0.0
    return float(b[0][-1])


def _limit_up(code, prev):
    if code[:2] in ('83', '87', '43', '92'):
        r = 0.30
    elif code[:2] in ('30', '68'):
        r = 0.20
    else:
        r = 0.10
    return round(prev * (1.0 + r) + 1e-6, 2)


def _limit_down(code, prev):
    if code[:2] in ('83', '87', '43', '92'):
        r = 0.30
    elif code[:2] in ('30', '68'):
        r = 0.20
    else:
        r = 0.10
    return round(prev * (1.0 - r) + 1e-6, 2)

def _buy_price(code, prev):
    """limit = prev_close*(1+GAP_MAX), capped by up-limit; big gaps simply do not fill"""
    up = _limit_up(code, prev)
    px = round(prev * (1.0 + GAP_MAX) + 1e-6, 2)
    if px > up:
        px = up
    floor = round(prev * 1.001 + 1e-6, 2)
    if px < floor:
        px = floor
    return px, up


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


def _load_bars(ctx, codes, count=SCAN_COUNT, min_bars=40):
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
        if len(closes) >= min_bars:
            out[c] = (closes, highs, lows)
    return out


def _tier_map(ctx, codes, verbose=True):
    """code -> tier (1=T1 2=T2 3=T3 0=no data)"""
    bars = _load_bars(ctx, codes)
    tiers = {}
    for c in codes:
        b = bars.get(c)
        tiers[c] = _tier(c, b[0], b[1], b[2]) if b else 0
    if verbose:
        n1 = sum(1 for v in tiers.values() if v == 1)
        n2 = sum(1 for v in tiers.values() if v == 2)
        _log('T1 scan: bars %d/%d, T1=%d T2=%d' % (len(bars), len(codes), n1, n2))
    if not bars and codes:
        _log('T1 scan: no daily bars at all (md api?)')
    return tiers, bars

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
    bars = {}
    if T1_FIRST:
        tiers, bars = _tier_map(ctx, codes, verbose)
        if not bars:
            _log('T1 priority: no daily data, keep auction order')
        else:
            t1s = [c for c in codes if tiers.get(c) == 1]
            rest = [c for c in codes if tiers.get(c) != 1]
            codes = t1s + rest
            _log('T1 priority: T1=%d [%s] pool=%d, buy up to %d'
                 % (len(t1s), ','.join(t1s[:6]) or '-', len(codes), MAX_BUY))

    held = _held_codes()
    plan = []
    for code in codes:
        if code in held:
            if verbose:
                _log('skip %s: already held' % code)
            continue
        if code in bars:
            prev = float(bars[code][0][-1])
        else:
            prev = _prev_close(ctx, code)
        if prev <= 0:
            _log('skip %s: no prev close' % code)
            continue
        px, up = _buy_price(code, prev)
        vol = FIXED_VOL if FIXED_VOL > 0 else int(AMOUNT / px / 100) * 100
        if vol < 100:
            _log('skip %s: amount too small for %.2f' % (code, px))
            continue
        if code.startswith('688') and vol < 200:
            _log('skip %s: STAR board needs >=200 shares' % code)
            continue
        plan.append((code, px, vol, prev, up))
        if len(plan) >= MAX_BUY:
            break

    all_held = bool(codes) and not plan
    if not plan:
        _log('no tradable code (held=%d, tries=%d)' % (len(held), A.tries))
        return 0, all_held, ''

    cash = _cash()
    need = sum(p[1] * p[2] for p in plan)
    if cash > 0 and cash < need:
        _log('stop: cash %.0f < need %.0f' % (cash, need))
        return 0, False, ''

    ordered = 0
    for code, px, vol, prev, up in plan:
        msg = 'clip buy %s %d@%.2f prev=%.2f up=%.2f' % (code, vol, px, prev, up)
        if DRY_RUN:
            _log('[DRY] would %s (%.0f yuan)' % (msg, px * vol))
            ordered += 1
            continue
        try:
            passorder(23, 1101, A.acct, code, 11, px, vol, TAG, 1, msg, ctx)
            _log('ORDER BUY %s' % msg)
            ordered += 1
        except TypeError:
            try:
                passorder(23, 1101, A.acct, code, 11, px, vol, TAG, 0, msg, ctx)
                _log('ORDER BUY %s (legacy1)' % msg)
                ordered += 1
            except TypeError:
                passorder(23, 1101, A.acct, code, 11, px, vol, ctx)
                _log('ORDER BUY %s (legacy2)' % msg)
                ordered += 1
        except Exception as e:
            _log('ORDER BUY FAILED %s: %s' % (code, e))
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
        prev = _prev_close(ctx, code)
        if prev > 0:
            mode, price = 11, _limit_down(code, prev)
        else:
            mode, price = 5, -1
        msg = 'clip sell %s %d @%s' % (code, avail, ('%.2f' % price) if mode == 11 else 'last')
        if DRY_SELL:
            _log('[DRY] would sell %s %d shares (holding %d)' % (code, avail, vol))
            n += 1
            continue
        try:
            passorder(24, 1101, A.acct, code, mode, price, avail, TAG_SELL, 1, msg, ctx)
            _log('ORDER SELL %s' % msg)
            n += 1
        except TypeError:
            passorder(24, 1101, A.acct, code, mode, price, avail, ctx)
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

        # ---- afternoon: sell all sellable positions; retry while shares stay unlocked
        if SELL_START <= hm <= SELL_END and A.sold_date != now.strftime('%Y%m%d'):
            if now.timestamp() - A.last_sell_try >= SELL_EVERY:
                A.last_sell_try = now.timestamp()
                avail = sum(p[1] for p in _positions())
                if avail <= 0:
                    A.sold_date = now.strftime('%Y%m%d')
                    _log('sell: nothing sellable, day closed')
                else:
                    n = _sell(ctx)
                    _log('sell pass: submitted=%d, avail_before=%d' % (n, avail))
                    _snap('after-sell')

        # ---- morning: buy from clipboard
        if A.token:
            return
        if now.weekday() >= 5:
            if A.weekend_note != now.strftime('%Y%m%d'):
                A.weekend_note = now.strftime('%Y%m%d')
                _log('weekend: no trading, skip buying')
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
    A.last_sell_try = 0.0
    A.weekend_note = ''
    A.acct = ACC_BT
    try:
        A.acct = account
    except Exception:
        pass
    _log('init v%s | buy %s-%s | sell %s-%s | per-stock %.0f | max %d | t1_first=%s | gap %.1f%% | dry_buy=%s dry_sell=%s | acct=%s'
         % (STRAT_VERSION, WIN_START, WIN_END, SELL_START, SELL_END,
            AMOUNT, MAX_BUY, T1_FIRST, GAP_MAX * 100.0, DRY_RUN, DRY_SELL, A.acct))
    try:
        pos = _positions()
        _log('positions now: %d (%s)' % (len(pos), ','.join(p[0] for p in pos[:5])))
        _snap('init')
        if pos:
            c0 = pos[0][0]
            p0 = _prev_close(C, c0)
            _log('prev-close probe: %s prev=%.2f %s' % (c0, p0, 'OK' if p0 > 0 else 'BROKEN'))
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
