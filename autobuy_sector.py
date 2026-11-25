#encoding:gbk
# ---------------------------------------------------------------
# BUY strategy, NO NETWORK version -- reads a custom sector instead.
#
# Why: QMT's live mode has an "anti external connection" guard; a
# strategy that touches the network is killed immediately, so HTTP
# cannot be used inside Model Trading. This version only calls the
# client's own sector API.
#
# Precondition: tools/push_sector.py writes the sector file before
# the open, and QMT must reload it (a client restart is reliable).
#
#   1. Paste into a NEW strategy, Compile
#   2. Start it in Model Trading with your account
#   3. Inside the 09:30 window it reads the sector, filters, buys
#
# Heartbeat: prints "[HB buy HH:MM:SS]" every 30s into the QMT log
# so the dashboard can read liveness from the log (no network).
# ---------------------------------------------------------------
import datetime

SECTOR    = '\u7ade\u4ef7\u9009\u80a1'     # sector name (jing jia xuan gu)
WIN_START = '093000'
WIN_END   = '093130'
AMOUNT    = 100000
MAX_BUY   = 5
TAG       = 'jingjia'
DRY_RUN   = True
HB_EVERY  = 30
BIG_REPEAT = 200000


class holder():
    pass


A = holder()


def _now():
    return datetime.datetime.now()


def _log(msg):
    print('[AUTO %s] %s' % (_now().strftime('%H:%M:%S'), msg))


def _tick(ctx):
    try:
        now = _now()
        if now.timestamp() - A.hb_ts >= HB_EVERY:
            A.hb_ts = now.timestamp()
            A.hb_n += 1
            _log('[HB buy %s #%d]' % (now.strftime('%H:%M:%S'), A.hb_n))

        hm = now.strftime('%H%M%S')
        if hm < WIN_START or hm > WIN_END:
            return
        today = now.strftime('%Y%m%d')
        if A.done_date == today:
            return
        A.done_date = today
        _run(ctx)
    except Exception as e:
        import traceback
        _log('tick error: %s' % e)
        print(traceback.format_exc())


def _pool(ctx):
    codes = []
    try:
        codes = [c for c in ctx.get_stock_list_in_sector(SECTOR) if c]
    except Exception as e:
        _log('read sector failed: %s' % e)
    if not codes:
        try:
            uni = ctx.get_universe() or []
            codes = [c for c in uni if c]
            if codes:
                _log('sector empty, fallback to universe: %d' % len(codes))
        except Exception:
            pass
    return codes


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
            for k in ('UpStopPrice', 'upStopPrice'):
                if det.get(k):
                    up = float(det.get(k))
                    break
    except Exception:
        pass
    return last, volume, up, name


def _run(ctx):
    codes = _pool(ctx)
    _log('sector %s -> %d codes: %s' % (SECTOR, len(codes), ','.join(codes[:10])))
    if not codes:
        _log('nothing to buy (empty sector)')
        return

    ok = []
    for code in codes:
        last, volume, up, name = _snapshot(ctx, code)
        if last <= 0:
            _log('skip %s: no price' % code)
            continue
        if volume <= 0:
            _log('skip %s: suspended' % code)
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
    _log('cash=%.0f, buying %d codes' % (cash, len(ok)))

    for code, last, name in ok:
        if cash > 0 and cash < AMOUNT:
            _log('stop: cash %.0f < %.0f' % (cash, AMOUNT))
            break
        vol = int(AMOUNT / last / 100) * 100
        if vol < 100:
            _log('skip %s: amount too small for %.2f' % (code, last))
            continue
        msg = 'auto buy %s %d@%.2f' % (code, vol, last)
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


def init(C):
    A.hb_n = 0
    A.hb_ts = 0.0
    A.done_date = ''
    A.acct = 'testS'
    try:
        A.acct = account
    except Exception:
        pass
    _log('init | sector=%s | window %s-%s | amount %.0f | max %d | dry_run=%s | acct=%s'
         % (SECTOR, WIN_START, WIN_END, AMOUNT, MAX_BUY, DRY_RUN, A.acct))
    try:
        codes = C.get_stock_list_in_sector(SECTOR)
        _log('sector now has %d codes' % len(codes or []))
    except Exception as e:
        _log('sector read failed: %s' % e)
    try:
        key = C.schedule_run(_tick,
                             _now() + datetime.timedelta(seconds=1),
                             BIG_REPEAT,
                             datetime.timedelta(seconds=1),
                             'autobuy_sector_1s')
        _log('schedule_run OK key=%s' % key)
    except Exception as e:
        _log('schedule_run FAILED: %s' % e)


def handlebar(C):
    pass
