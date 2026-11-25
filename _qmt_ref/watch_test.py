# -*- coding: utf-8 -*-
"""观察 --watch：目录里迟到 3 秒的 CSV 能不能被补上。"""
import datetime
import io
import os
import sys

W = r'F:\ai\deepseekharness\国金证券模拟账号'
sys.path.insert(0, W)
TMP = os.path.join(W, r'_qmt_ref\export_tmp')
if not os.path.isdir(TMP):
    os.makedirs(TMP)

until = (datetime.datetime.now() + datetime.timedelta(seconds=14)).strftime('%H%M%S')
sys.argv = ['clip_push.py', '--watch', '--every', '1', '--until', until,
            '--dry', '--export-dir', TMP, '--top', '3']

buf = io.StringIO()
old = sys.stdout
sys.stdout = buf
rc = 1
try:
    import clip_push as C
    rc = C.main()
except SystemExit as e:
    rc = e.code
except Exception:
    import traceback
    buf.write(traceback.format_exc())
finally:
    sys.stdout = old

io.open(os.path.join(W, r'_qmt_ref\watch_test.out'), 'w', encoding='utf-8').write(
    'rc=%s until=%s\n' % (rc, until) + buf.getvalue())
