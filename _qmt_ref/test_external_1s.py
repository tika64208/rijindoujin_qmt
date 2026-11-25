#encoding:gbk
# ---------------------------------------------------------------
# TEST: can QMT read EXTERNAL data?  prints every 1 second.
#
# How to run
#   1. Model Research -> +New Strategy -> Python Strategy
#   2. Paste this file, Ctrl+S, Compile
#   3. Put it into the Model Trading module with the simulation
#      account 63009312 and START it.  Do NOT use Backtest: in
#      backtest the clock jumps and a 1s timer never fires.
#   4. Watch the log: one line per second.
#
# What each line means
#   A=...   load_stk_list()  -> C++ side file read of lists\today.txt
#   B=...   get_stock_list_in_sector() -> custom sector (see SECTOR)
#   err=... that channel failed
#
# While it runs, change the file  D:\...\lists\today.txt  or edit the
# sector inside QMT, and see whether A / B changes on the next line.
#
# Source is pure ASCII; Chinese names and paths are written as \u
# escapes so this file never hits a GBK/UTF-8 problem inside QMT.
# ---------------------------------------------------------------
import datetime

SECTOR    = '\u7ade\u4ef7\u9009\u80a1'                     # jing jia xuan gu
SECTOR_T  = '\u7ade\u4ef7\u9009\u80a1\u6d4b\u8bd5'         # jing jia xuan gu ce shi
LISTS_DIR = 'D:\\\u56fd\u91d1QMT\u4ea4\u6613\u7aef\u6a21\u62df\\lists'

BIG_REPEAT = 200000        # about 55 hours of 1s ticks


class holder():
    pass


A = holder()


def _stamp():
    return datetime.datetime.now().strftime('%H:%M:%S')


def _probe(ctx):
    """one line of diagnostics"""
    out = ['[TEST %s #%d]' % (_stamp(), A.n)]
    A.n += 1

    # ---- channel A: C++ side file read ----
    try:
        r = ctx.load_stk_list(LISTS_DIR, 'today.txt')
        out.append('A=%s (%s)' % (str(r)[:100], type(r).__name__))
    except Exception as e:
        out.append('A_err=%s' % e)

    # ---- channel B: custom sector ----
    try:
        r = ctx.get_stock_list_in_sector(SECTOR)
        out.append('B=%s (%s)' % (str(r)[:100], type(r).__name__))
    except Exception as e:
        out.append('B_err=%s' % e)

    print(' | '.join(out))


def _tick():
    """callback used by schedule_run (takes no arguments)"""
    try:
        _probe(A.ctx)
    except Exception as e:
        print('[TEST %s] tick error: %s' % (_stamp(), e))


def init(C):
    A.n = 0
    A.ctx = C
    A.timer_ok = False
    print('==============================================')
    print('[TEST] start at %s' % _stamp())
    print('[TEST] file channel  : %s' % LISTS_DIR)
    print('[TEST] sector channel: %s' % SECTOR)
    print('==============================================')

    # one immediate probe so you always get at least one line
    _probe(C)

    # ---- 1 second timer ----
    try:
        key = C.schedule_run(_tick,
                             datetime.datetime.now() + datetime.timedelta(seconds=1),
                             BIG_REPEAT,
                             datetime.timedelta(seconds=1),
                             'probe_1s')
        A.timer_ok = True
        print('[TEST] schedule_run OK, key=%s' % key)
    except Exception as e:
        print('[TEST] schedule_run FAILED: %s' % e)
        print('[TEST] fallback: will print once per bar instead')

    # ---- channel C: build a sector from code, then read it back ----
    try:
        r = C.create_sector(SECTOR_T, ['300209.SZ', '000001.SZ'])
        print('[TEST] create_sector -> %s' % (r,))
        print('[TEST] read back     -> %s' % (C.get_stock_list_in_sector(SECTOR_T),))
    except Exception as e:
        print('[TEST] create_sector FAILED: %s' % e)


def handlebar(C):
    # fallback heartbeat, only if the 1s timer could not be set up
    if not A.timer_ok:
        _probe(C)
