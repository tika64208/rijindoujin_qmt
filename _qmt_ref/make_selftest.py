# -*- coding: utf-8 -*-
"""从 autobuy_clip.py 生成自测版：
   TEST_ANYTIME=True（忽略 09:30 窗口）+ 盘后价格回退（日线收盘）+ 硬编码账户。
"""
import io
import re

W = r'F:\ai\deepseekharness\国金证券模拟账号'
src = io.open(W + r'\autobuy_clip.py', 'r', encoding='utf-8').read()

src = src.replace('TEST_ANYTIME = False', 'TEST_ANYTIME = True\nIGNORE_VOLUME = True')
src = src.replace("ACC_BT    = 'testS'", "ACC_BT    = '63009312'")
src = src.replace("        if volume <= 0:", "        if volume <= 0 and not IGNORE_VOLUME:")

fallback = '''

def _fallback_price(ctx, code):
    """after-hours fallback: use daily close when no tick (self-test only)"""
    try:
        det = ctx.get_instrument_detail(code) or {}
        if isinstance(det, dict):
            for k in ('PreClose', 'preClose'):
                if det.get(k):
                    return float(det[k])
    except Exception:
        pass
    try:
        d = ctx.get_market_data_ex(['close'], [code], period='1d', count=2)
        df = d.get(code)
        if df is not None and len(df) > 0:
            return float(df['close'].iloc[-1])
    except Exception:
        pass
    try:
        d = ctx.get_market_data(['close'], [code], period='1d', count=2)
        if d is not None and len(d) > 0:
            v = d.iloc[-1:]
            return float(v.values.ravel()[-1])
    except Exception:
        pass
    return 0.0
'''

src = src.replace('\ndef _run(ctx, token, codes):', fallback + '\n\ndef _run(ctx, token, codes):')
src = src.replace("""        last, volume, up, name = _snapshot(ctx, code)
        if last <= 0:""", """        last, volume, up, name = _snapshot(ctx, code)
        if last <= 0:
            last = _fallback_price(ctx, code)
            if last > 0:
                _log('%s no tick, fallback close %.2f' % (code, last))
        if last <= 0:""")

io.open(W + r'\_qmt_ref\autobuy_clip_selftest.py', 'w', encoding='utf-8', newline='').write(src)
print('written', len(src))
