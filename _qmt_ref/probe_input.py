#encoding:gbk
# ---------------------------------------------------------------
# Probe: which channel can bring an EXTERNAL stock list into QMT?
#
# Paste into a NEW Python strategy, Compile, click Backtest.
# It prints a few lines in init() and stops. Send the output back.
#
# Channel A: C.load_stk_list(dirfile, namefile)  -> C++ side file read
# Channel B: C.get_stock_list_in_sector(name)    -> custom sector file
# Channel C: C.create_sector(name, codes)        -> build sector in code
#
# NOTE: source is pure ASCII; the Chinese sector name and the QMT
# folder are written as \u escapes so this file never hits an
# encoding problem inside QMT.
# ---------------------------------------------------------------

SECTOR = '\u7ade\u4ef7\u9009\u80a1'          # jing jia xuan gu
SECTOR_T = '\u7ade\u4ef7\u9009\u80a1\u6d4b\u8bd5'
QMT_LISTS = 'D:\\\u56fd\u91d1QMT\u4ea4\u6613\u7aef\u6a21\u62df\\lists'


def init(C):
    print('===== PROBE START =====')
    print('target sector name = %s' % SECTOR)

    # ---- Channel A: load_stk_list ----
    for d, f in ((QMT_LISTS, 'today.txt'),
                 (QMT_LISTS, 'today.csv'),
                 ('D:/guojin_qmt/lists', 'today.txt')):
        try:
            r = C.load_stk_list(d, f)
            print('A load_stk_list(%s, %s) -> %s : %s' % (d, f, type(r), str(r)[:200]))
        except Exception as e:
            print('A load_stk_list(%s, %s) raised: %s' % (d, f, e))

    # ---- Channel B: existing custom sector ----
    try:
        r = C.get_stock_list_in_sector(SECTOR)
        print('B sector -> %s : %s' % (type(r), str(r)[:300]))
    except Exception as e:
        print('B sector raised: %s' % e)

    # ---- Channel C: create then read back ----
    try:
        r = C.create_sector(SECTOR_T, ['300209.SZ', '000001.SZ'])
        print('C create_sector -> %s : %s' % (type(r), str(r)[:200]))
        r2 = C.get_stock_list_in_sector(SECTOR_T)
        print('C read back -> %s : %s' % (type(r2), str(r2)[:200]))
    except Exception as e:
        print('C create_sector raised: %s' % e)

    print('===== PROBE END =====')


def handlebar(C):
    pass
