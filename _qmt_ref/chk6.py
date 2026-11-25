import py_compile, io
res=[]
for p in [r'F:\ai\deepseekharness\国金证券模拟账号\autobuy_from_list.py', r'F:\ai\deepseekharness\国金证券模拟账号\list_server.py']:
    try:
        py_compile.compile(p, doraise=True); res.append('OK   ' + p)
    except Exception as e:
        res.append('FAIL ' + p + ' :: ' + repr(e))
io.open(r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\chk6.out','w',encoding='utf-8').write('\n'.join(res))
