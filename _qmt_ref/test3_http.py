#encoding:gbk
# ---------------------------------------------------------------
# TEST 3: can a QMT strategy do an HTTP request to localhost?
#
# If this prints HTTP 200 and the file body, then the whole
# "third-party data -> QMT auto buy" chain is solved:
#   your Python tool writes the list and serves it on 127.0.0.1,
#   the QMT strategy just GETs it every morning at 09:30.
# No MiniQMT, no sector files, no client restart.
#
# Run in Model Trading (simulation account), NOT backtest.
# Prints once at startup, then once per second.
# ---------------------------------------------------------------
import datetime

URL = 'http://127.0.0.1:8765/today.csv'
HOST, PORT = '127.0.0.1', 8765
BIG_REPEAT = 200000


class holder():
    pass


A = holder()


def _stamp():
    return datetime.datetime.now().strftime('%H:%M:%S')


def _http_get(url, timeout=3):
    """try urllib first, then raw socket"""
    try:
        import urllib.request as ureq
        r = ureq.urlopen(url, timeout=timeout)
        body = r.read().decode('utf-8', 'ignore')
        return 'HTTP %s body=%r' % (r.getcode(), body[:200])
    except Exception as e1:
        err1 = '%s: %s' % (type(e1).__name__, e1)

    try:
        import socket
        s = socket.create_connection((HOST, PORT), timeout=timeout)
        req = ('GET /today.csv HTTP/1.0\r\nHost: %s\r\n\r\n' % HOST).encode()
        s.sendall(req)
        data = s.recv(4096).decode('utf-8', 'ignore')
        s.close()
        return 'SOCKET ok, %d bytes: %r' % (len(data), data[:160])
    except Exception as e2:
        return 'BOTH FAILED | urllib=%s | socket=%s' % (err1, e2)


def _tick(ctx):
    try:
        print('[T3 %s #%d] %s' % (_stamp(), A.n, _http_get(URL)))
        A.n += 1
    except Exception as e:
        print('[T3 %s] tick error: %s' % (_stamp(), e))


def init(C):
    A.n = 0
    A.ctx = C
    print('==============================================')
    print('[T3] start %s  url=%s' % (_stamp(), URL))
    print('[T3] first probe: %s' % _http_get(URL))
    print('==============================================')
    try:
        key = C.schedule_run(_tick,
                             datetime.datetime.now() + datetime.timedelta(seconds=1),
                             BIG_REPEAT,
                             datetime.timedelta(seconds=1),
                             't3s')
        print('[T3] schedule_run OK key=%s' % key)
    except Exception as e:
        print('[T3] schedule_run FAILED: %s' % e)


def handlebar(C):
    pass
