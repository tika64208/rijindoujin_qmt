import py_compile, io
res=[]
for p in [r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\probe_input.py']:
    try:
        py_compile.compile(p, doraise=True); res.append('OK ' + p)
    except Exception as e:
        res.append('FAIL ' + repr(e))
io.open(r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\chk2.out','w',encoding='utf-8').write('\n'.join(res))
