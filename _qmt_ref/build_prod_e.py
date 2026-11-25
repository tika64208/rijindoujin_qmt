# -*- coding: utf-8 -*-
"""生成生产版 v2026-11-25e：档1(接口兜底) + 档2(09:25:05 挂限价排队)。"""
import io
import os
import re

W = r'F:\ai\deepseekharness\国金证券模拟账号'
SRC = os.path.join(W, r'_qmt_ref\autobuy_clip_test1125.py')
DST = os.path.join(W, r'autobuy_clip.py')

src = io.open(SRC, 'r', encoding='utf-8').read()

# 1) constants back to production + new knobs
src = src.replace("STRAT_VERSION = 'TEST-2026-11-25c'", "STRAT_VERSION = '2026-11-25e'")
src = src.replace("T1_GATE   = False", "T1_GATE   = True")
src = src.replace("DRY_RUN   = False", "DRY_RUN   = True")
src = src.replace("FIXED_VOL = 100", "FIXED_VOL = 0")
src = src.replace("SELL_START = '000000'", "SELL_START = '145000'")
src = src.replace("SELL_END   = '000001'", "SELL_END   = '145630'")
src = src.replace("WIN_START = '093000'", "WIN_START = '092505'")
src = src.replace("WIN_END   = '145500'", "WIN_END   = '093130'")

if 'GAP_MAX' not in src:
    src = src.replace("FIXED_VOL = 0",
                      "FIXED_VOL = 0\nGAP_MAX   = 0.05           # buy limit = prev_close*(1+GAP_MAX), capped by up-limit")

# 2) helper: prev close + up limit
helpers = '''

def _prev_close(ctx, code):
    """last completed daily bar close (today's bar is dropped by _load_bars)"""
    bars = _load_bars(ctx, [code], 40)
    b = bars.get(code)
    if not b or len(b[0]) < 2:
        return 0.0
    return float(b[0][-1])


def _limit_up(code, prev):
    if code[:2] in ('83', '87', '43', '92'):
        r = 0.30
    elif code[:2] in ('30', '68'):
        r = 0.20
    else:
        r = 0.10
    return round(prev * (1.0 + r) + 1e-6, 2)


def _buy_price(code, prev):
    """限价：昨收*(1+GAP_MAX)，但不高于涨停价；跳空过大的票买不到（相当于过滤）"""
    up = _limit_up(code, prev)
    px = round(prev * (1.0 + GAP_MAX) + 1e-6, 2)
    if px > up:
        px = up
    floor = round(prev * 1.001 + 1e-6, 2)
    if px < floor:
        px = floor
    return px, up

'''

src = src.replace("\ndef _snapshot(ctx, code):", helpers + "\ndef _snapshot(ctx, code):")

# 3) replace whole _buy function
start = src.index('def _buy(')
end = src.index('# ----------------------------------------------------------------- sell')
head, tail = src[:start], src[end:]

new_buy = '''def _buy(ctx, token, codes, verbose=True):
    if T1_GATE:
        t1, bars = _t1_filter(ctx, codes, verbose)
        if not bars:
            _log('T1 gate: no daily data, fall back to payload (fail-open)')
        elif not t1:
            _log('T1 gate: no match today -> skip buying')
            return 0, True, 'no_T1'
        else:
            codes = t1

    held = _held_codes()
    plan = []
    for code in codes:
        if code in held:
            if verbose:
                _log('skip %s: already held' % code)
            continue
        prev = _prev_close(ctx, code)
        if prev <= 0:
            _log('skip %s: no prev close' % code)
            continue
        px, up = _buy_price(code, prev)
        vol = FIXED_VOL if FIXED_VOL > 0 else int(AMOUNT / px / 100) * 100
        if vol < 100:
            _log('skip %s: amount too small for %.2f' % (code, px))
            continue
        if code.startswith('688') and vol < 200:
            _log('skip %s: STAR board needs >=200 shares' % code)
            continue
        plan.append((code, px, vol, prev, up))
        if len(plan) >= MAX_BUY:
            break

    all_held = bool(codes) and not plan
    if not plan:
        _log('no tradable code (held=%d, tries=%d)' % (len(held), A.tries))
        return 0, all_held, ''

    cash = _cash()
    need = sum(p[1] * p[2] for p in plan)
    if cash > 0 and cash < need:
        _log('stop: cash %.0f < need %.0f' % (cash, need))
        return 0, False, ''

    ordered = 0
    for code, px, vol, prev, up in plan:
        msg = 'clip buy %s %d@%.2f prev=%.2f up=%.2f' % (code, vol, px, prev, up)
        if DRY_RUN:
            _log('[DRY] would %s (%.0f yuan)' % (msg, px * vol))
            ordered += 1
            continue
        try:
            passorder(23, 1101, A.acct, code, 11, px, vol, TAG, 1, msg, ctx)
            _log('ORDER BUY %s' % msg)
            ordered += 1
        except TypeError:
            try:
                passorder(23, 1101, A.acct, code, 11, px, vol, TAG, 0, msg, ctx)
                _log('ORDER BUY %s (legacy1)' % msg)
                ordered += 1
            except TypeError:
                passorder(23, 1101, A.acct, code, 11, px, vol, ctx)
                _log('ORDER BUY %s (legacy2)' % msg)
                ordered += 1
        except Exception as e:
            _log('ORDER BUY FAILED %s: %s' % (code, e))
    return ordered, all_held, ''


'''
src = head + new_buy + tail

io.open(DST, 'w', encoding='utf-8', newline='\n').write(src)
print('written', DST, len(src))

bad = [c for c in src if ord(c) > 127]
print('non-ascii chars:', len(bad))
