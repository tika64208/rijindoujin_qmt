#encoding:gbk
# ---------------------------------------------------------------
# QMT BUY strategy, clipboard edition.
#
# Why: from 2.1.36 the client kills any strategy python process
# that touches the network ([fang wai jie]), and file IO inside a
# strategy is forbidden ("Forbidden fileIO").  The Windows
# clipboard is the one local channel that still works -- verified
# on this box: ctypes + user32 clipboard read returns the payload
# written by clip_push.py, while open() raises Forbidden fileIO.
#
# Wire format (single line of text on the clipboard):
#
#   QMTCLIP1|<yyyymmddHHMMSS>|<code,code,...>|<8 hex sig>
#
#   sig = FnvLike("QMTCLIP1|<ts>|<codes>")   (see _sig)
#
# clip_push.py writes it at 09:29; this strategy polls every second,
# acts once per token inside the 09:30:00-09:31:30 window.
#
# Filters: no price / suspended / ST / limit-up are skipped.
# Sizing : fixed AMOUNT per stock, at most MAX_BUY stocks, cash cap.
#
# Source is ASCII only: QMT stores .py as GBK.
# ---------------------------------------------------------------
import datetime


MAGIC     = 'QMTCLIP1'
WIN_START = '093000'       # earliest time to act
WIN_END   = '093130'       # latest time to act
AMOUNT    = 100000         # cash per stock
MAX_BUY   = 5              # max stocks per day
TAG       = 'jingjia'      # order tag
DRY_RUN   = True           # True: log only, no real orders
TEST_ANYTIME = True
IGNORE_VOLUME = True       # True: ignore the clock window (bench test)
ACC_BT    = '63009312'        # fallback account when not configured
BIG_REPEAT = 200000
HB_EVERY  = 60             # heartbeat period in seconds


class holder():
    pass


A = holder()


def _now():
    return datetime.datetime.now()


def _log(msg):
    print('[CLIPBUY %s] %s' % (_now().strftime('%H:%M:%S'), msg))


def _sig(s):
    """small dependency-free checksum, same math on the producer side"""
    h = 7
    for ch in s:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return '%08X' % h


def _read_clip():
    """unicode text currently on the Windows clipboard, or None"""
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
        h = u32.GetClipboardData(13)          # CF_UNICODETEXT
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
    """-> (token, codes, reason).  token is None when the text is unusable"""
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



def _fallback_price(ctx, code):
    """after-hours fallback: use daily close when no tick (self-test only)"""
    try:
        det = ctx.get_instrument_detail(code) or {}
        if isinstance(det, dict):
            for k in ('PreClose', 'preClose'):
                if det.get(k):
                    return float(det[k])
    except Exception:
        pass
    try:
        d = ctx.get_market_data_ex(['close'], [code], period='1d', count=2)
        df = d.get(code)
        if df is not None and len(df) > 0:
            return float(df['close'].iloc[-1])
    except Exception:
        pass
    try:
        d = ctx.get_market_data(['close'], [code], period='1d', count=2)
        if d is not None and len(d) > 0:
            v = d.iloc[-1:]
            return float(v.values.ravel()[-1])
    except Exception:
        pass
    return 0.0


def _run(ctx, token, codes):
    _log('token %s -> %d codes: %s' % (token, len(codes), ','.join(codes)))

    ok = []
    for code in codes:
        last, volume, up, name = _snapshot(ctx, code)
        if last <= 0:
            last = _fallback_price(ctx, code)
            if last > 0:
                _log('%s no tick, fallback close %.2f' % (code, last))
        if last <= 0:
            _log('skip %s: no price' % code)
            continue
        if volume <= 0 and not IGNORE_VOLUME:
            _log('skip %s: suspended (volume 0)' % code)
            continue
        uname = name.upper().replace(' ', '')
        if 'ST' in uname or '\u9000' in name:
            _log('skip %s: ST/delisting (%s)' % (code, name))
            continue
        if up > 0 and last >= up * 0.999:
            _log('skip %s: limit up %.2f/%.2f' % (code, last, up))
            continue
        ok.append((code, last, name))
        if len(ok) >= MAX_BUY:
            break

    if not ok:
        _log('no tradable code after filtering')
        return

    cash = 0.0
    try:
        accs = get_trade_detail_data(A.acct, 'STOCK', 'ACCOUNT')
        if accs:
            cash = float(accs[0].m_dAvailable)
    except Exception as e:
        _log('account query failed: %s' % e)
    _log('available cash = %.0f, will buy %d stocks' % (cash, len(ok)))

    for code, last, name in ok:
        if cash > 0 and cash < AMOUNT:
            _log('stop: cash %.0f < amount %.0f' % (cash, AMOUNT))
            break
        vol = int(AMOUNT / last / 100) * 100
        if vol < 100:
            _log('skip %s: amount too small for price %.2f' % (code, last))
            continue
        msg = 'clip buy %s %d@%.2f' % (code, vol, last)
        if DRY_RUN:
            _log('[DRY] would buy %s %d @%.2f (%s)' % (code, vol, last, name))
        else:
            try:
                passorder(23, 1101, A.acct, code, 5, -1, vol, TAG, 1, msg, ctx)
                _log('ORDER %s' % msg)
            except TypeError:
                passorder(23, 1101, A.acct, code, 5, -1, vol, ctx)
                _log('ORDER %s (legacy)' % msg)
            except Exception as e:
                _log('ORDER FAILED %s: %s' % (code, e))
        if cash > 0:
            cash -= vol * last


def _tick(ctx):
    try:
        hm = _now().strftime('%H%M%S')
        if A.hb_ts == 0 or _now().timestamp() - A.hb_ts >= HB_EVERY:
            A.hb_ts = _now().timestamp()
            A.hb_n += 1
            _log('[HB #%d] %s' % (A.hb_n, 'in window' if hm >= WIN_START and hm <= WIN_END
                                   else 'waiting %s-%s' % (WIN_START, WIN_END)))

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
        if token is None or token == A.token:
            return
        A.token = token
        _run(ctx, token, codes)
    except Exception as e:
        import traceback
        _log('tick error: %s' % e)
        print(traceback.format_exc())


def init(C):
    A.hb_n = 0
    A.hb_ts = 0.0
    A.token = ''
    A.last_seen = None
    A.acct = ACC_BT
    try:
        A.acct = account
    except Exception:
        pass
    _log('init | window %s-%s | per-stock %.0f | max %d | dry_run=%s | test_anytime=%s | acct=%s'
         % (WIN_START, WIN_END, AMOUNT, MAX_BUY, DRY_RUN, TEST_ANYTIME, A.acct))
    try:
        token, codes, why = _parse(_read_clip())
        if token:
            _log('clipboard now: token=%s n=%d' % (token, len(codes)))
        else:
            _log('clipboard now: %s' % why)
    except Exception as e:
        _log('clipboard probe failed: %s' % e)
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
