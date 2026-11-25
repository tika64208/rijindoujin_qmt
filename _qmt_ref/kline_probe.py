# -*- coding: utf-8 -*-
"""探针：东财日线 kline（前复权），确认字段与速度。"""
import io
import json
import time
import urllib.parse
import urllib.request

BASE = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'


def secid(code):
    code = str(code).zfill(6)
    return ('1.' if code[0] in '569' else '0.') + code


def kline(code, lmt=120):
    q = {
        'secid': secid(code),
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
        'klt': '101', 'fqt': '1', 'end': '20500101', 'lmt': str(lmt),
    }
    url = BASE + '?' + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/'})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode('utf-8', 'ignore'))


out = []
t0 = time.time()
for code in ('000001', '600000', '300209'):
    try:
        j = kline(code, 10)
        d = j.get('data') or {}
        kl = d.get('klines') or []
        out.append('%s %s bars=%d last=%s' % (code, d.get('name'), len(kl), kl[-1] if kl else '-'))
    except Exception as e:
        out.append('%s ERROR %s' % (code, e))
out.append('elapsed=%.2fs' % (time.time() - t0))
io.open(r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\kline_probe.out', 'w', encoding='utf-8').write('\n'.join(out))
