# -*- coding: utf-8 -*-
import py_compile, io
try:
    py_compile.compile(r'F:\ai\deepseekharness\国金证券模拟账号\周线KDJ_300209.py', doraise=True); out='SYNTAX OK'
except Exception as e:
    out='SYNTAX FAIL: %r' % e
io.open(r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\chk_ma.out','w',encoding='utf-8').write(out)
