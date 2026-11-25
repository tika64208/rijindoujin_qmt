import py_compile, io
try:
    py_compile.compile(r'F:\ai\deepseekharness\国金证券模拟账号\push_from_export.py', doraise=True); out='OK push_from_export.py'
except Exception as e:
    out='FAIL push_from_export.py :: %r' % e
io.open(r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\chk_out.txt','a',encoding='utf-8').write(out+'\n')
