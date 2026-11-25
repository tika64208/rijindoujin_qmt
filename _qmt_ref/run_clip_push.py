# -*- coding: utf-8 -*-
import io
import sys

W = r'F:\ai\deepseekharness\国金证券模拟账号'
sys.path.insert(0, W)
sys.argv = ['clip_push.py', '--codes', '000001,600000,300209']

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

io.open(W + r'\_qmt_ref\clip_push.out', 'w', encoding='utf-8').write(
    'rc=%s\n' % rc + buf.getvalue())
