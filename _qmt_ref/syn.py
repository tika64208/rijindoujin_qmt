import io, ast, traceback
p = r'F:\ai\deepseekharness\国金证券模拟账号\周线KDJ回测.py'
try:
    src = io.open(p, encoding='utf-8').read()
    ast.parse(src)
    out = 'SYNTAX OK lines=%d' % len(src.splitlines())
except Exception:
    out = traceback.format_exc()
io.open(r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\syn.out','w',encoding='utf-8').write(out)
