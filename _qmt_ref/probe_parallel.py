# -*- coding: utf-8 -*-
"""测并发吞吐：N 个线程各发 200KB，看总耗时与失败率。"""
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = 'https://padded-counting-splendor.ngrok-free.dev/api/logs/ingest'
KEY = 'qk-7f3a9d2c5b8e41a6'
KB = 200
N = 12


def one(i):
    body = ('y' * (KB * 1024)).encode()
    qs = urllib.parse.urlencode({'source': 'qmt-probe-par', 'file': 'p%d' % i, 'offset': i})
    req = urllib.request.Request(URL + '?' + qs, data=body,
                                 headers={'X-API-Key': KEY, 'Content-Type': 'text/plain'},
                                 method='POST')
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.getcode(), time.time() - t0
    except Exception as e:
        return type(e).__name__, time.time() - t0


t0 = time.time()
with ThreadPoolExecutor(max_workers=6) as ex:
    res = list(ex.map(one, range(N)))
dt = time.time() - t0
ok = sum(1 for c, _ in res if c == 200)
print('requests=%d ok=%d elapsed=%.1fs throughput=%.2f MB/s' % (N, ok, dt, N * KB / 1024.0 / dt))
print('per-request: %s' % ['%s/%.1fs' % (c, t) for c, t in res])
