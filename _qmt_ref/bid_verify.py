# -*- coding: utf-8 -*-
"""复刻 BidStrategy.kt 并和 App 导出的 CSV 逐行回归。"""
import csv
import io
import math
import os

SRC = r'F:\ai\deepseekharness\竞价分析\export\竞价数据_2026-11-05.csv'
OUT = r'F:\ai\deepseekharness\国金证券模拟账号\_qmt_ref\bid_verify.out'


def f(x, d=0.0):
    try:
        v = float(x)
        return v if not (math.isnan(v) or math.isinf(v)) else d
    except Exception:
        return d


def compute_bid_turnover(volume_hand, price, circ_mv):
    """Kotlin: volume * latestPrice / (circMv * 100)"""
    if circ_mv <= 0 or volume_hand <= 0:
        return 0.0
    v = volume_hand * price / (circ_mv * 100.0)
    return 0.0 if (math.isnan(v) or math.isinf(v)) else v


def compute_probability(bid_change, bid_turnover, warn, circ_mv, real_change):
    circ_mv_yi = circ_mv / 1e8
    base_change = bid_change if bid_change != 0 else real_change

    if 3.0 <= bid_change <= 5.5:
        bid_s = 1.0
    elif bid_change >= 2.0:
        bid_s = 0.88
    elif bid_change >= 1.5:
        bid_s = 0.65
    elif bid_change > 0:
        bid_s = 0.4
    else:
        bid_s = 0.1

    if bid_turnover >= 0.8:
        act_s = 1.0
    elif bid_turnover >= 0.4:
        act_s = 0.88
    elif bid_turnover >= 0.2:
        act_s = 0.72
    elif bid_turnover >= 0.08:
        act_s = 0.5
    elif bid_turnover > 0:
        act_s = 0.3
    else:
        act_s = 0.1

    warn_s = {5: 1.0, 4: 0.85, 3: 0.6}.get(int(warn), 0.18)

    if circ_mv_yi < 30:
        mv_s = 1.0
    elif circ_mv_yi < 60:
        mv_s = 0.88
    elif circ_mv_yi < 120:
        mv_s = 0.68
    elif circ_mv_yi < 250:
        mv_s = 0.45
    else:
        mv_s = 0.22

    if 3.0 <= base_change < 9.5:
        mom_s = 0.9
    elif base_change >= 1.0:
        mom_s = 0.65
    elif base_change >= 0:
        mom_s = 0.4
    elif base_change > -3.0:
        mom_s = 0.25
    else:
        mom_s = 0.15

    base = bid_s * 0.34 + act_s * 0.32 + warn_s * 0.17 + mv_s * 0.11 + mom_s * 0.06
    prob = max(5, min(95, int(math.floor(base * 100 + 0.5))))

    conf = 65
    if warn >= 4:
        conf += 10
    if bid_turnover >= 0.4:
        conf += 8
    if 2.0 <= bid_change <= 6.5:
        conf += 7
    conf = min(90, max(55, conf))
    return prob, conf


def estimate_bid_volume(volume, bid_change):
    ratio = 0.035
    if bid_change >= 5:
        ratio = 0.055
    elif bid_change >= 3:
        ratio = 0.045
    elif bid_change <= 0:
        ratio = 0.018
    v = int(volume * ratio)
    return max(min(v, 3000000), 500)


def score_parts(bid_change, real_change, warn, bid_volume):
    change_for_score = bid_change if bid_change != 0 else real_change
    s1 = max(0.0, min(bid_change / 9.0, 1.0)) * 50
    s2 = max(0.0, min(change_for_score / 10.0, 1.0)) * 20
    if warn == 5:
        s3 = 20.0
    elif warn == 4:
        s3 = 16.0
    elif bid_change >= 4:
        s3 = 10.0
    else:
        s3 = 0.0
    vol = bid_volume if bid_volume > 0 else 0
    s4 = max(0.0, min(vol / 200000.0, 1.0)) * 10
    return s1, s2, s3, s4


def main():
    rows = []
    with io.open(SRC, 'r', encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh):
            rows.append(r)

    lines = ['rows=%d' % len(rows)]
    header = list(rows[0].keys())
    lines.append('columns=%s' % ','.join(header))

    n = 0
    hit_prob = hit_conf = hit_score = 0
    err_prob = []
    samples = []

    for r in rows:
        code = r['代码']
        bid_change = f(r['竞价涨幅%'])
        real_change = f(r['涨跌幅%'])
        warn = int(f(r['异动标志']))
        circ_mv = f(r['总市值_元'])
        vol = f(r['成交量_手'])
        open_px = f(r['开盘价'])
        last_px = f(r['最新价'])
        app_prob = int(f(r['概率']))
        app_conf = int(f(r['可信度']))
        app_score = int(f(r['评分']))
        app_vol = int(f(r['估算竞价量']))
        app_turn = f(r['竞价换手率_内部值'])

        # 用 CSV 里记录的开盘价（评分时点的价格）
        px = open_px if open_px > 0 else last_px
        turn = compute_bid_turnover(vol, px, circ_mv)
        prob, conf = compute_probability(bid_change, turn, warn, circ_mv, real_change)

        # 评分用 App 记录的估算竞价量，便于单独验证评分链路
        s1, s2, s3, s4 = score_parts(bid_change, real_change, warn, app_vol)
        score = int(math.floor(s1 + s2 + s3 + s4 + 0.5))
        score = max(0, min(100, score))

        n += 1
        if prob == app_prob:
            hit_prob += 1
        else:
            err_prob.append(abs(prob - app_prob))
        if conf == app_conf:
            hit_conf += 1
        if score == app_score:
            hit_score += 1

        if len(samples) < 8:
            samples.append('%s %s bid=%.2f real=%.2f warn=%d mv=%.1f亿 vol=%.0f px=%.2f | '
                           'turn=%.2e(calc) %.2e(app) | prob %d/%d conf %d/%d score %d/%d(%.1f+%.1f+%.1f+%.1f)'
                           % (code, r['名称'], bid_change, real_change, warn, circ_mv / 1e8, vol, px,
                              turn, app_turn, prob, app_prob, conf, app_conf, score, app_score,
                              s1, s2, s3, s4))

    lines.append('')
    lines.append('=== 概率命中 %d/%d = %.1f%%  平均绝对误差 %.2f' % (
        hit_prob, n, 100.0 * hit_prob / n, (sum(err_prob) / len(err_prob)) if err_prob else 0))
    lines.append('=== 可信度命中 %d/%d = %.1f%%' % (hit_conf, n, 100.0 * hit_conf / n))
    lines.append('=== 评分命中 %d/%d = %.1f%%' % (hit_score, n, 100.0 * hit_score / n))
    lines.append('')
    lines.append('--- 样本 ---')
    lines.extend(samples)

    io.open(OUT, 'w', encoding='utf-8').write('\n'.join(lines))


main()

