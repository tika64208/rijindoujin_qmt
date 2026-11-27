# -*- coding: utf-8 -*-
"""用新浪行情交叉验证持仓股的最新价。"""
import io
import urllib.request

CODES = ['sz000062', 'sz002077', 'sh603960', 'sh688343', 'sz001337', 'sz000017',
         'sz300434', 'sz301569', 'sz002403', 'sz002298']
URL = 'https://hq.sinajs.cn/list=' + ','.join(CODES)
REQ = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0',
                                           'Referer': 'https://finance.sina.com.cn/'})
text = urllib.request.urlopen(REQ, timeout=10).read().decode('gbk', 'ignore')
out = []
for line in text.strip().split('\n'):
    if '="' not in line:
        continue
    head, rest = line.split('="', 1)
    code = head.split('_')[-1]
    fields = rest.split('",')[0].split(',')
    if len(fields) < 32:
        out.append('%s SHORT %d' % (code, len(fields)))
        continue
    out.append('%s %-10s prev=%s open=%s last=%s high=%s low=%s' %
               (code, fields[0], fields[2], fields[1], fields[3], fields[4], fields[5]))
io.open(r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\quote_sina.out', 'w',
        encoding='utf-8').write('\n'.join(out))
