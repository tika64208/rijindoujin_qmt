# -*- coding: utf-8 -*-
"""跑若干 clip_push 场景，把输出和退出码写到文件（pythonw 没控制台）。"""
import io
import os
import sys
import traceback

W = r'F:\ai\deepseekharness\国金证券模拟账号'
sys.path.insert(0, W)
OUT = os.path.join(W, r'_qmt_ref\clip_scenarios.out')

SCEN = [
    ('no-today-file', ['clip_push.py', '--dry']),
    ('old-file-no-flag', ['clip_push.py', '--file',
                          r'F:\ai\deepseekharness\竞价分析\export\竞价数据_2026-11-10.csv',
                          '--dry', '--top', '3']),
    ('old-file-allow-old', ['clip_push.py', '--file',
                            r'F:\ai\deepseekharness\竞价分析\export\竞价数据_2026-11-10.csv',
                            '--dry', '--top', '3', '--allow-old']),
    ('watch-2s', ['clip_push.py', '--watch', '--every', '1', '--until', '000000']),
]

buf = io.StringIO()


def run(name, argv):
    global buf
    buf.write('\n===== %s =====\n' % name)
    old_out = sys.stdout
    sys.stdout = buf
    sys.argv = argv
    rc = None
    try:
        import clip_push as C
        rc = C.main()
    except SystemExit as e:
        rc = e.code
    except Exception:
        buf.write(traceback.format_exc())
        rc = 'EXC'
    finally:
        sys.stdout = old_out
    buf.write('rc=%s\n' % rc)


if __name__ == '__main__':
    for name, argv in SCEN:
        run(name, argv)
    io.open(OUT, 'w', encoding='utf-8').write(buf.getvalue())
