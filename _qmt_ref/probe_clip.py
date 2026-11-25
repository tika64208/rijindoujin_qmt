#encoding:gbk
# ---------------------------------------------------------------
# PROBE: can a QMT model-trading strategy read the Windows
# clipboard?  (no network access, no Python file IO allowed)
#
# Prints "[CLIP hh:mm:ss] ..." into the QMT formula output log
# once per second while it stays alive.
# ---------------------------------------------------------------
import datetime


class holder():
    pass


A = holder()


def _log(m):
    print('[CLIP %s] %s' % (datetime.datetime.now().strftime('%H:%M:%S'), m))


def _clip_ctypes():
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
        return 'ERR:OpenClipboard'
    try:
        h = u32.GetClipboardData(13)      # CF_UNICODETEXT
        if not h:
            return 'ERR:NoUnicodeText'
        p = k32.GlobalLock(h)
        if not p:
            return 'ERR:GlobalLock'
        try:
            return ctypes.wstring_at(p)
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


def _probe_env():
    import sys
    _log('python %s' % sys.version.replace('\n', ' ')[:60])
    for mod in ('ctypes', 'win32clipboard', 'win32api', 'tkinter', 'PyQt5'):
        try:
            __import__(mod)
            _log('import %-14s OK' % mod)
        except Exception as e:
            _log('import %-14s FAIL %s' % (mod, str(e)[:60]))
    try:
        v = _clip_ctypes()
        _log('clipboard -> %r' % (v,))
    except Exception as e:
        import traceback
        _log('clipboard exception: %s' % e)
        print(traceback.format_exc())
    try:
        f = open('D:\\\u56fd\u91d1QMT\u4ea4\u6613\u7aef\u6a21\u62df\\lists\\today.txt', 'r')
        t = f.read()
        f.close()
        _log('file IO OK len=%d' % len(t))
    except Exception as e:
        _log('file IO block: %s' % str(e)[:80])


def _tick(ctx):
    try:
        v = _clip_ctypes()
        if v != A.last:
            A.last = v
            _log('CHANGED -> %r' % (v,))
        A.n += 1
        if A.n % 10 == 0:
            _log('hb #%d %r' % (A.n, (v or '')[:60]))
    except Exception as e:
        _log('tick err %s' % e)


def init(C):
    A.n = 0
    A.last = None
    _log('init')
    _probe_env()
    try:
        key = C.schedule_run(_tick,
                             datetime.datetime.now() + datetime.timedelta(seconds=1),
                             600,
                             datetime.timedelta(seconds=1),
                             'clip_probe_1s')
        _log('schedule_run OK key=%s' % key)
    except Exception as e:
        _log('schedule_run FAILED: %s' % e)


def handlebar(C):
    pass
