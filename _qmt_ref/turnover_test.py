# -*- coding: utf-8 -*-
"""验证：概率是否依赖成交量（把 turnover 置 0 后还能过线几只）"""
import io
import sys

W = r'F:\ai\deepseekharness\国金证券模拟账号'
sys.path.insert(0, W)
import bid_fetch as F
import bid_rules as R

text = F.fetch_json()
rows, total = F.to_rows(text)

cfg = R.HIGH_WIN_RATE
out = []
n_real = n_zero = 0
zero_drops = []

for r in rows:
    ok_real = R.passes(r, cfg) if hasattr(R, 'passes') else None
    # 手工复算：真实 turnover vs 置零
    p_real, c_real = R.probability(r['bid_change'], r['turnover'], r['warn'], r['mv_yi'], r['real_change'])
    p_zero, c_zero = R.probability(r['bid_change'], 0.0, r['warn'], r['mv_yi'], r['real_change'])
    if ok_real is None:
        # 用 select 的等价条件手判
        def ok(p, c, sc, mv, px, bid):
            return (cfg['bid_min'] <= bid <= cfg['bid_max'] and p >= cfg['prob_min']
                    and c >= cfg['conf_min'] and sc >= cfg['score_min']
                    and cfg['mv_min'] <= mv <= cfg['mv_max']
                    and cfg['price_min'] <= px <= cfg['price_max'] and r['warn'] < 5)
        ok_real = ok(p_real, c_real, r['score'], r['mv_yi'], r['open'], r['bid_change'])
        ok_zero = ok(p_zero, c_zero, r['score'], r['mv_yi'], r['open'], r['bid_change'])
    else:
        ok_zero = False
    if ok_real:
        n_real += 1
    if ok_zero:
        n_zero += 1
    if ok_real and not ok_zero:
        zero_drops.append((r['code'], r['name'], r['turnover'], p_real, p_zero))

out.append('rows=%d' % total)
out.append('真实 turnover 过线: %d 只' % n_real)
out.append('turnover 置 0 过线: %d 只' % n_zero)
out.append('')
out.append('%-8s %-10s %10s %8s %8s' % ('code', 'name', 'turnover', 'prob_real', 'prob_zero'))
for c, n, t, pr, pz in zero_drops[:15]:
    out.append('%-8s %-10s %10.4f %8.1f %8.1f' % (c, n, t, pr, pz))
io.open(W + r'\out\turnover_test.txt', 'w', encoding='utf-8').write('\n'.join(out))
