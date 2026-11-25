#encoding:gbk
# ---------------------------------------------------------------
# TEST 2: which stock-code FORMAT does load_stk_list accept,
#         and does it depend on the board?
#
# Run in Model Trading (simulation account), NOT backtest, and
# watch the first few lines.
#
# Files prepared under <QMT>\lists\
#   f1.txt  300209.SZ / 002843.SZ / 000007.SZ   (with .SZ suffix)
#   f2.txt  300209    / 002843    / 000007      (bare 6 digits)
#   f3.txt  300209,SZ / 002843,SZ / 000007,SZ   (code,market)
#   f4.txt  000001.SZ / 300001.SZ / 002001.SZ / 600000.SH  (one per board)
#
# Prints channel A once per second (proof the timer works), and
# prints all four files once at startup.
# ---------------------------------------------------------------
import datetime

LISTS_DIR = 'D:\\\u56fd\u91d1QMT\u4ea4\u6613\u7aef\u6a21\u62df\\lists'
SECTOR    = '\u7ade\u4ef7\u9009\u80a1'
BIG_REPEAT = 200000


class holder():
    pass


A = holder()


def _stamp():
    return datetime.datetime.now().strftime('%H:%M:%S')


def _read(ctx, fname):
    try:
        r = ctx.load_stk_list(LISTS_DIR, fname)
        return '%s -> %s (%s)' % (fname, str(r)[:120], type(r).__name__)
    except Exception as e:
        return '%s -> ERR %s' % (fname, e)


def _tick(ctx):
    """called by schedule_run -- receives ContextInfo"""
    try:
        parts = ['[TEST %s #%d]' % (_stamp(), A.n)]
        A.n += 1
        parts.append(_read(A.ctx, 'f4.txt'))
        parts.append('B=%s' % (str(A.ctx.get_stock_list_in_sector(SECTOR))[:80],))
        print(' | '.join(parts))
    except Exception as e:
        print('[TEST %s] tick error: %s' % (_stamp(), e))


def init(C):
    A.n = 0
    A.ctx = C
    print('==============================================')
    print('[TEST2] start %s' % _stamp())
    print('--- startup: four file formats ---')
    for f in ('f1.txt', 'f2.txt', 'f3.txt', 'f4.txt'):
        print('[TEST2] ' + _read(C, f))
    print('--- end formats ---')
    # does subscribing first make the rejected codes acceptable?
    try:
        C.set_universe(['300209.SZ', '002843.SZ', '000007.SZ'])
        print('[TEST2] after set_universe, f1: ' + _read(C, 'f1.txt'))
    except Exception as e:
        print('[TEST2] set_universe FAILED: %s' % e)
    try:
        key = C.schedule_run(_tick,
                             datetime.datetime.now() + datetime.timedelta(seconds=1),
                             BIG_REPEAT,
                             datetime.timedelta(seconds=1),
                             't2s')
        print('[TEST2] schedule_run OK key=%s' % key)
    except Exception as e:
        print('[TEST2] schedule_run FAILED: %s' % e)
    print('==============================================')


def handlebar(C):
    pass
