# -*- coding: utf-8 -*-
"""探针：用 QMT 自带 python3.6 直接请求东财 push2dycalc，确认可达+字段。"""
import io
import json
import sys
import urllib.parse
import urllib.request

BASE = 'https://push2dycalc.eastmoney.com/api/qt/clist/get'
FIELDS = 'f2,f3,f4,f5,f6,f8,f10,f12,f14,f17,f18,f20,f100,f102,f103,f124,f615,f630'
TOKEN = 'c92c50e6b0fab2c17cd5e276e9a79c42'
FS = 'm:1+t:2,m:0+t:6,m:0+t:80,m:1+t:23'


def fetch():
    q = {
        'pn': '1', 'pz': '6000', 'po': '1', 'np': '1', 'fltt': '2', 'invt': '2',
        'fid': 'f3', 'fs': FS, 'fields': FIELDS, 'ut': TOKEN,
    }
    url = BASE + '?' + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://quote.eastmoney.com/',
        'Cache-Control': 'no-cache',
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode('utf-8', 'ignore')


out = []
try:
    raw = fetch()
    j = json.loads(raw)
    data = j.get('data') or {}
    diff = data.get('diff') or []
    out.append('rc=%s total=%s rows=%s len=%d' % (j.get('rc'), data.get('total'), len(diff), len(raw)))
    if diff:
        r0 = diff[0]
        out.append('sample: ' + json.dumps(r0, ensure_ascii=False)[:400])
        # 统计竞价涨幅非零的数量
        nz = [r for r in diff if isinstance(r.get('f615'), (int, float)) and r.get('f615')]
        out.append('f615 nonzero: %d' % len(nz))
        if nz[:3]:
            out.append('examples: ' + json.dumps(nz[:3], ensure_ascii=False)[:400])
except Exception as e:
    import traceback
    out.append('ERROR %s\n%s' % (e, traceback.format_exc()))

io.open(r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\em_probe.out', 'w', encoding='utf-8').write('\n'.join(out))
