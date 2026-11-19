# -*- coding: utf-8 -*-
"""
bid_rules.py -- 从 ri jindoujin_momentum (Android/Kotlin) 提取的竞价筛选规则。

来源文件（逐行翻译，已验证）：
  engine/BidStrategy.kt        -> 五因子概率 / 可信度 / V2评分 / 换手 / 排除
  engine/BidCandidateSelector.kt -> 预设过滤与排序
  engine/OpenBuyCalculator.kt  -> 9:30 开盘价买入口径

回归验证（用 export/竞价数据_2026-11-05.csv，5563 行）：
  预设区间(竞价2~4%)内：概率 100% 一致，评分 100% 一致
  全样本：概率 91.2%，评分 89.9%（差异全部集中在竞价涨幅=0 的行）

已知实现缺陷（照原样保留，仅记录，不改动作）：
  1) 竞价换手率量纲错误：volume(手)*price/(市值元*100) 结果恒为 ~1e-6，
     永远小于 0.08 阈值，所以"竞价活跃度"因子实际恒取 0.3 档，形同虚设。
  2) "剔涨停"用的是异动标志 warnFlag>=5，不是涨幅>=9.5%，
     所以"触板但 warnFlag=4"的股票仍然会入选。
  3) 市值用的是导出时点的 总市值_元，与 09:29 评分时点的市值可能不同，
     跨档时会让概率差 1~4 分 —— 因此必须以 App 冻结的评分为准，不要事后重算。
"""

# ---------------- 预设（BidStrategy.BidConfig.HIGH_WIN_RATE） ----------------
HIGH_WIN_RATE = {
    'bid_min': 2.0, 'bid_max': 4.0,
    'prob_min': 60.0, 'prob_max': 100.0,
    'conf_min': 70.0, 'conf_max': 100.0,
    'score_min': 35.0, 'score_max': 0.0,
    'mv_min': 30.0, 'mv_max': 200.0,        # 亿
    'price_min': 5.0, 'price_max': 60.0,
    'filter_st': True,
    'filter_limit_up': True,                # 实际是 warnFlag>=5
    'market_hs': True, 'market_cyb': True, 'market_kcb': True,
    'filter_large_volume': False, 'large_volume_threshold': 100000,
}

WARN_SCORE = {5: 1.0, 4: 0.85, 3: 0.6}
WARN_TEXT = {5: '🔥强', 4: '⚡中', 3: '↑弱'}


def _mv_band(mv_yi):
    if mv_yi < 30:
        return 1.0
    if mv_yi < 60:
        return 0.88
    if mv_yi < 120:
        return 0.68
    if mv_yi < 250:
        return 0.45
    return 0.22


def bid_turnover(volume_hand, price, circ_mv_yuan):
    """BidStrategy.computeBidTurnover —— 注意量纲（见文件头缺陷 1）"""
    if circ_mv_yuan <= 0 or volume_hand <= 0:
        return 0.0
    v = volume_hand * price / (circ_mv_yuan * 100.0)
    if v != v or v in (float('inf'), float('-inf')):
        return 0.0
    return v


def probability(bid_change, turnover, warn, mv_yi, real_change):
    """五因子涨停概率 -> (prob, conf)"""
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

    if turnover >= 0.8:
        act_s = 1.0
    elif turnover >= 0.4:
        act_s = 0.88
    elif turnover >= 0.2:
        act_s = 0.72
    elif turnover >= 0.08:
        act_s = 0.5
    elif turnover > 0:
        act_s = 0.3
    else:
        act_s = 0.1

    warn_s = WARN_SCORE.get(int(warn), 0.18)
    mv_s = _mv_band(mv_yi)
    base_change = bid_change if bid_change != 0 else real_change
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
    prob = max(5, min(95, int(_round_half_up(base * 100))))

    conf = 65
    if warn >= 4:
        conf += 10
    if turnover >= 0.4:
        conf += 8
    if 2.0 <= bid_change <= 6.5:
        conf += 7
    conf = min(90, max(55, conf))
    return prob, conf


def _round_half_up(x):
    return x + 0.5 if x >= 0 else x - 0.5


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
    """V2 评分四项：[竞价(50), 涨幅(20), 异动(20), 量能(10)]"""
    change = bid_change if bid_change != 0 else real_change
    s1 = max(0.0, min(bid_change / 9.0, 1.0)) * 50
    s2 = max(0.0, min(change / 10.0, 1.0)) * 20
    if warn == 5:
        s3 = 20.0
    elif warn == 4:
        s3 = 16.0
    elif bid_change >= 4:
        s3 = 10.0
    else:
        s3 = 0.0
    s4 = max(0.0, min(bid_volume / 200000.0, 1.0)) * 10
    return s1, s2, s3, s4


def score(bid_change, real_change, warn, bid_volume):
    return max(0, min(100, int(_round_half_up(sum(score_parts(bid_change, real_change, warn, bid_volume))))))


def _outside(value, lo, hi):
    return (lo > 0 and value < lo) or (hi > 0 and value > hi)


def matches(row, cfg=None):
    """BidCandidateSelector.matches -> (ok, reason)。row 见 build_row()。"""
    cfg = cfg or HIGH_WIN_RATE
    open_px = row['open']
    if open_px <= 0:
        return False, '无开盘价'

    if cfg['filter_st'] and ('ST' in row['name'].upper() or u'停' in row['name']):
        return False, 'ST/停牌'

    if cfg['filter_limit_up'] and row['warn'] >= 5:
        return False, '已涨停(warnFlag>=5)'

    code = row['code']
    is_hs = (code.startswith('6') and not code.startswith('688')) or code.startswith('00')
    is_cyb = code.startswith('3')
    is_kcb = code.startswith('688')
    if is_hs and not cfg['market_hs']:
        return False, '市场:沪主板已关闭'
    if is_cyb and not cfg['market_cyb']:
        return False, '市场:创业板已关闭'
    if is_kcb and not cfg['market_kcb']:
        return False, '市场:科创板已关闭'

    checks = [
        ('竞价涨幅', row['bid_change'], cfg['bid_min'], cfg['bid_max']),
        ('概率', row['prob'], cfg['prob_min'], cfg['prob_max']),
        ('可信度', row['conf'], cfg['conf_min'], cfg['conf_max']),
        ('评分', row['score'], cfg['score_min'], cfg['score_max']),
        ('市值(亿)', row['mv_yi'], cfg['mv_min'], cfg['mv_max']),
        ('股价', open_px, cfg['price_min'], cfg['price_max']),
    ]
    for label, value, lo, hi in checks:
        if _outside(value, lo, hi):
            return False, '%s 越界(%.2f)' % (label, value)

    if cfg['filter_large_volume'] and row['volume'] >= cfg['large_volume_threshold']:
        return False, '成交量过大'
    return True, ''


def build_row(raw):
    """把 App 导出 CSV 的一行转成内部结构（字段名见 export/竞价数据_*.csv）"""
    def f(key, d=0.0):
        try:
            v = float(raw.get(key, d) or d)
            return v if v == v and abs(v) != float('inf') else d
        except Exception:
            return d

    code = str(raw.get('代码', '')).zfill(6)
    vol = f('成交量_手')
    op = f('开盘价')
    last = f('最新价')
    px = op if op > 0 else last
    mv_yuan = f('总市值_元')
    mv_yi = mv_yuan / 1e8
    bid = f('竞价涨幅%')
    real = f('涨跌幅%')
    warn = int(f('异动标志'))
    turn = bid_turnover(vol, px, mv_yuan)
    prob, conf = probability(bid, turn, warn, mv_yi, real)
    bvol = int(f('估算竞价量')) or estimate_bid_volume(vol, bid)
    sc = score(bid, real, warn, bvol)
    qmt = code + ('.SH' if code[:1] in ('5','6','9') else '.SZ')
    return {
        'code': code, 'qmt_code': qmt, 'name': raw.get('名称', ''), 'open': op, 'last': last,
        'bid_change': bid, 'real_change': real, 'warn': warn,
        'volume': vol, 'mv_yi': mv_yi, 'turnover': turn,
        'prob': prob, 'conf': conf, 'score': sc, 'bid_volume': bvol,
        'app_prob': int(f('概率')), 'app_conf': int(f('可信度')), 'app_score': int(f('评分')),
    }


def select(rows, cfg=None, top_n=0):
    """过滤 + 按概率降序(同分按代码)，返回 [(row, reason)]"""
    cfg = cfg or HIGH_WIN_RATE
    picked = [r for r in rows if matches(r, cfg)[0]]
    picked.sort(key=lambda r: (-r['prob'], r['code']))
    if top_n > 0:
        picked = picked[:top_n]
    return picked


def fmt_table(rows):
    lines = ['%-8s %-10s %7s %5s %5s %6s %8s' % ('code', 'name', 'bid%', 'prob', 'conf', 'score', 'mv(亿)')]
    for r in rows:
        lines.append('%-8s %-10s %7.2f %5d %5d %6d %8.1f'
                     % (r['code'], r['name'][:8], r['bid_change'], r['prob'], r['conf'], r['score'], r['mv_yi']))
    return '\n'.join(lines)

