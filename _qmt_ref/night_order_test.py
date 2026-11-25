#encoding:gbk
# one-shot test: place a non-marketable limit buy at night (limit-down price)
# and see whether the client/counter accepts it. ASCII only on purpose.
import datetime

CODE = '300209.SZ'
PRICE = 17.36
VOL = 100
TAG = 'nighttest'


class holder():
    pass


A = holder()


def _log(m):
    print('[NIGHT %s] %s' % (datetime.datetime.now().strftime('%H:%M:%S'), m))


def init(C):
    A.acct = 'testS'
    try:
        A.acct = account
    except Exception:
        pass
    _log('init acct=%s code=%s vol=%d price=%.2f' % (A.acct, CODE, VOL, PRICE))
    try:
        passorder(23, 1101, A.acct, CODE, 11, PRICE, VOL, TAG, 1, 'night limit test', C)
        _log('passorder(6-arg) sent')
    except TypeError as e:
        _log('TypeError: %s, try legacy' % e)
        try:
            passorder(23, 1101, A.acct, CODE, 11, PRICE, VOL, C)
            _log('passorder(legacy) sent')
        except Exception as e2:
            _log('legacy failed: %s' % e2)
    except Exception as e:
        _log('passorder failed: %s' % e)
    _log('done')


def handlebar(C):
    pass
