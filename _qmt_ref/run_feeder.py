# -*- coding: utf-8 -*-
import sys, io, os
sys.path.insert(0, r'F:\ai\deepseekharness\国金证券模拟账号')
buf = io.StringIO()
old = sys.stdout
sys.stdout = buf
sys.argv = ['push_from_export.py', '--dry', '--top', '5']
try:
    import push_from_export as P
    rc = P.main()
except SystemExit as e:
    rc = e.code
except Exception:
    import traceback; buf.write(traceback.format_exc())
finally:
    sys.stdout = old
io.open(r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\feeder.out','w',encoding='utf-8').write('rc=%s\n' % rc + buf.getvalue())
