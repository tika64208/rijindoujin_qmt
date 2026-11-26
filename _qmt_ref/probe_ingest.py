# -*- coding: utf-8 -*-
"""探测日志服务能接受的最大 POST 体积与单次耗时。"""
import time
import urllib.parse
import urllib.request

URL = 'https://padded-counting-splendor.ngrok-free.dev/api/logs/ingest'
KEY = 'qk-7f3a9d2c5b8e41a6'


def one(kb):
    body = ('x' * (kb * 1024)).encode()
    qs = urllib.parse.urlencode({'source': 'qmt-probe', 'file': 'probe', 'offset': 0})
    req = urllib.request.Request(URL + '?' + qs, data=body,
                                 headers={'X-API-Key': KEY, 'Content-Type': 'text/plain'},
                                 method='POST')
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return kb, r.getcode(), time.time() - t0
    except Exception as e:
        return kb, '%s %s' % (type(e).__name__, str(e)[:40]), time.time() - t0


for kb in (16, 32, 64, 128, 200):
    print(one(kb))
    time.sleep(0.3)
