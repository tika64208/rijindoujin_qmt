#encoding:gbk
# ---------------------------------------------------------------
# QMT auto-buy from an external pick list (fetch over localhost HTTP)
#
#   1. Run list_server.py on the same machine (publishes today.csv).
#   2. Paste this file into a new Python strategy, Compile.
#   3. Start it in the Model Trading module with the simulation
#      account. Do NOT use Backtest for real timing.
#
# Every second it checks the clock. Inside the window (default
# 09:30:00 - 09:31:30) it fetches the list once, filters, and buys.
#
# Filters: ST / delisting / suspended / limit-up / price sanity.
# Sizing : fixed AMOUNT per stock, at most MAX_BUY stocks, cash cap.
#
# ASCII only: QMT saves .py as GBK and Chinese in source breaks it.
# ---------------------------------------------------------------
import datetime
import urllib.request

SRV       = 'http://127.0.0.1:8765'
URL       = SRV + '/today.csv'
WIN_START = '093000'       # earliest time to act
WIN_END   = '093130'       # latest time to act
AMOUNT    = 100000         # cash per stock
MAX_BUY   = 5              # max stocks per day
TAG       = 'jingjia'      # order tag
DRY_RUN   = True           # True: log only, no real orders
ACC_BT    = 'testS'        # fallback account when not configured

BIG_REPEAT = 200000


class holder():
    pass


A = holder()


def _now():
    return datetime.datetime.now()


def _hm():
    return _now().strftime('%H%M%S')


def _log(msg):
    print('[AUTO %s] %s' % (_now().strftime('%H:%M:%S'), msg))


def _hb():
    # one heartbeat per second so the board knows the buy strategy is alive
    A.hb_n += 1
    try:
        urllib.request.urlopen('%s/hb?role=buy&n=%d' % (SRV, A.hb_n), timeout=2).read()
    except Exception:
        pass

def _fetch(url, timeout=3):
    r = urllib.request.urlopen(url, timeout=timeout)
    body = r.read().decode('utf-8', 'ignore')
    codes = []
    for raw in body.replace('\r', ',').replace('\n', ',').split(','):
        c = raw.strip().upper()
        if not c:
            continue
        if '.' in c and (c.endswith('.SH') or c.endswith('.SZ')):
            codes.append(c)
            continue
        digits = ''.join(ch for ch in c if ch.isdigit())[:6]
        if len(digits) == 6:
            mk = 'SH' if digits[0] in ('5', '6', '9') else 'SZ'
            codes.append('%s.%s' % (digits, mk))
    seen, uniq = set(), []
    for c in codes:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


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
        _run(ctx)
    except Exception as e:
        import traceback
        _log('tick error: %s' % e)
        print(traceback.format_exc())


def _snapshot(ctx, code):
    """last price, volume, up-limit, name"""
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
                    up = float(det.get(k))
                    break
    except Exception:
        pass
    return last, volume, up, name


def _run(ctx):
    _log('window hit, fetching %s' % URL)
    try:
        codes = _fetch(URL)
    except Exception as e:
        _log('FETCH FAILED: %s' % e)
        return
    if not codes:
        _log('list is empty, nothing to do')
        return
    _log('got %d codes: %s' % (len(codes), ','.join(codes)))

    ok = []
    for code in codes:
        last, volume, up, name = _snapshot(ctx, code)
        if last <= 0:
            _log('skip %s: no price' % code)
            continue
        if volume <= 0:
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
        msg = 'auto buy %s %d@%.2f' % (code, vol, last)
        if DRY_RUN:
            _log('[DRY] would buy %s %d shares @%.2f (%s)' % (code, vol, last, name))
        else:
            try:
                passorder(23, 1101, A.acct, code, 5, -1, vol, TAG, 1, msg, ctx)
                _log('ORDER %s' % msg)
            except TypeError:
                passorder(23, 1101, A.acct, code, 5, -1, vol, ctx)
                _log('ORDER %s' % msg)
            except Exception as e:
                _log('ORDER FAILED %s: %s' % (code, e))
        if cash > 0:
            cash -= vol * last


def init(C):
    A.done_date = ''
    A.hb_n = 0
    A.ctx = C
    A.acct = ACC_BT
    try:
        A.acct = account                     # provided by model trading
    except Exception:
        pass
    _log('init | url=%s | window %s-%s | per-stock %.0f | max %d | dry_run=%s | acct=%s'
         % (URL, WIN_START, WIN_END, AMOUNT, MAX_BUY, DRY_RUN, A.acct))
    _log('connectivity test: %s' % _probe(URL))
    try:
        key = C.schedule_run(_tick,
                             _now() + datetime.timedelta(seconds=1),
                             BIG_REPEAT,
                             datetime.timedelta(seconds=1),
                             'autobuy_1s')
        _log('schedule_run OK key=%s' % key)
    except Exception as e:
        _log('schedule_run FAILED: %s (will use per-bar)' % e)


def _probe(url):
    try:
        codes = _fetch(url)
        return 'OK, %d codes now: %s' % (len(codes), ','.join(codes[:6]))
    except Exception as e:
        return 'FAILED: %s (is list_server.py running?)' % e


def handlebar(C):
    pass
