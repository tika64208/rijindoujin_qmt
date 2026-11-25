#coding:gbk
#==============================================================================
#  周线KDJ 股票买卖策略（QMT / 迅投 内置 Python 模型）
#------------------------------------------------------------------------------
#  思路：
#    1. 只用“周线”K 线计算 KDJ(9,3,3)，不受日线噪音干扰；
#    2. 买入：K 上穿 D（金叉）且 K 处于低位（默认 K < 25），说明超卖后转强；
#    3. 卖出：K 下穿 D（死叉）无条件卖出；也可打开止损（STOP_LOSS_PCT）；
#    4. 股票池默认沪深300成分股，最多持有 MAX_HOLD 只，单只占总资产 POSITION_PCT；
#    5. 同一周内只调仓一次：
#         - 回测周期选“周线”时，每周一根K线，每周自然只跑一次；
#         - 若在“日线/分钟线”上跑，则每周第一个交易日计算一次，不会天天重复下单。
#
#  用法：
#    模型研究 -> 策略列表 -> 我的策略 -> 周线KDJ回测 -> 点“回测”
#    回测设置建议：周期=周线(1w)，复权=前复权，初始资金=100万，
#                  区间例如 2020-01-01 ~ 2026-11-17
#
#  注意：
#    * 回测模式下资金账号可以随便填（这里用 testS），实盘/模拟盘要改成真实资金账号；
#    * 本文件为 GBK 编码，请勿用 UTF-8 覆盖保存，否则中文注释会乱码。
#==============================================================================

import datetime
import os
import numpy as np
import pandas as pd

# ------------------------------ 参数设置 --------------------------------------
STOCK_POOL_SECTOR = '沪深300'      # 板块名：沪深300 / 中证500 / 上证50 / 沪深A股 ...
STOCK_POOL = ['300209.SZ']         # 自定义股票池；非空则忽略上面的板块（本次：行云科技）
MAX_HOLD = 5                       # 最多同时持有几只股票
POSITION_PCT = 0.2                 # 单只股票买入金额占总资产的比例（0.2=两成仓）
BUY_K = 35.0                       # 金叉时 K 值的上限，越小越严格（只买超卖后的金叉）；25 太严，行云科技最低金叉 K=28
STOP_LOSS_PCT = 0.0                # 止损比例，如 0.1 表示亏损10%止损；0 表示不启用
ACCOUNT = 'testS'                  # 回测用的虚拟账号（回测模式可任意字符串）
ACC = ACCOUNT                      # 运行时实际使用的账号，init 里按回测/模拟自动切换
LIVE_ACCOUNT = '63009312'          # 模拟交易/实盘用的真实资金账号（非回测模式自动使用）
DIVIDEND_TYPE = 'front'            # 复权方式：front 前复权 / none 不复权
KDJ_N, KDJ_M1, KDJ_M2 = 9, 3, 3    # KDJ 参数

MIN_WEEK_BARS = KDJ_N + 5          # 周线数据少于此数量则跳过该股
MAX_WEEK_BARS = 40                 # 每次取多少根周线（够算指标即可，别取太多影响速度）
MIN_BUY_AMOUNT = 5000              # 单笔最小买入金额（元），太小就不买
MAX_POOL = 300                     # 股票池上限，超过则截断（防止一次性加载过多行情）
CHUNK_SIZE = 50                    # 每次批量取行情的股票数量（分批取，避免客户端卡死）
BACKTEST_START = '2025-01-01 00:00:00'   # 回测开始时间（写进代码，免得界面区间不对）
BACKTEST_END = '2026-11-17 15:00:00'     # 回测结束时间
STALE_DAYS = 20                    # 周线最后一根K线距今天数超过它，视为停牌/退市，跳过该股
# -----------------------------------------------------------------------------


# ------------------------------ 指标计算 --------------------------------------
def kdj(close, high, low, n=KDJ_N, m1=KDJ_M1, m2=KDJ_M2):
    """标准 KDJ：RSV=(C-LLV(L,N))/(HHV(H,N)-LLV(L,N))*100, K=SMA(RSV,M1,1), D=SMA(K,M2,1), J=3K-2D"""
    llv = low.rolling(n, min_periods=n).min()
    hhv = high.rolling(n, min_periods=n).max()
    rng = hhv - llv
    rsv = (close - llv) / rng * 100.0
    rsv = rsv.replace([np.inf, -np.inf], np.nan).fillna(50.0)   # 首段无数据按 50 起步
    k = rsv.ewm(alpha=1.0 / m1, adjust=False).mean()
    d = k.ewm(alpha=1.0 / m2, adjust=False).mean()
    j = 3.0 * k - 2.0 * d
    return k, d, j


def calc_signal(df):
    """由周线 DataFrame 计算最新一根周线的 KDJ 与金叉/死叉状态"""
    if df is None or len(df) < MIN_WEEK_BARS:
        return None
    cols = [c for c in ('close', 'high', 'low', 'volume') if c in df.columns]
    for col in ('close', 'high', 'low'):
        if col not in cols:
            return None
    d = df[cols].astype(float).dropna(subset=['close', 'high', 'low'])
    if len(d) < MIN_WEEK_BARS:
        return None
    k, dd, j = kdj(d['close'], d['high'], d['low'])
    k1, k2 = float(k.iloc[-1]), float(k.iloc[-2])
    d1, d2 = float(dd.iloc[-1]), float(dd.iloc[-2])
    close1 = float(d['close'].iloc[-1])
    if close1 <= 0 or np.isnan(k1) or np.isnan(d1):
        return None
    try:
        last_raw = d.index[-1]
    except Exception:
        last_raw = ''
    try:
        last_vol = float(d['volume'].iloc[-1]) if 'volume' in d.columns else 1.0
    except Exception:
        last_vol = 1.0
    return {
        'k': k1,
        'd': d1,
        'j': float(j.iloc[-1]),
        'close': close1,
        'last_date': last_raw,
        'last_vol': last_vol,
        'golden': (k2 <= d2) and (k1 > d1),   # 金叉
        'death': (k2 >= d2) and (k1 < d1),    # 死叉
    }


# ------------------------------ 交易辅助 --------------------------------------
def get_account():
    """取回测/交易账户对象"""
    try:
        infos = get_trade_detail_data(ACC, 'STOCK', 'ACCOUNT')
    except Exception:
        return None
    if not infos:
        return None
    return infos[0]


def code_id(code):
    """把 000425.SZ / 000425.SH 统一成 6 位代码，避免持仓与行情的代码格式不一致导致匹配失败"""
    return str(code).split('.')[0].strip().upper()


def to_date(s):
    """把 20170103 / 20170103150000 / 1483459200000(毫秒) 统一转成 date"""
    try:
        if isinstance(s, (int, float)) and not isinstance(s, bool):
            v = int(s)
            if v > 100000000000:
                v = v // 1000
            return datetime.date.fromtimestamp(v)
        t = str(s).strip()
        if len(t) >= 8 and t[:8].isdigit():
            return datetime.date(int(t[0:4]), int(t[4:6]), int(t[6:8]))
        v = int(float(t))
        if v > 100000000000:
            v = v // 1000
        return datetime.date.fromtimestamp(v)
    except Exception:
        return None


def get_positions():
    """取持仓：{6位代码: {'code':完整代码, 'vol':总持仓, 'can':可用, 'cost':成本价}}"""
    res = {}
    try:
        objs = get_trade_detail_data(ACC, 'STOCK', 'POSITION')
    except Exception:
        objs = []
    for o in objs:
        try:
            full = '%s.%s' % (o.m_strInstrumentID, o.m_strExchangeID)
            vol = float(o.m_nVolume)
            if vol <= 0:
                continue
            can = float(getattr(o, 'm_nCanUseVolume', vol))
            cost = float(getattr(o, 'm_dOpenPrice', 0.0))
            res[code_id(full)] = {'code': full, 'vol': vol, 'can': can, 'cost': cost}
        except Exception:
            continue
    return res


def daily_to_weekly(df):
    """把日线 DataFrame 按 ISO 周合成周线（QMT 取不到 1w 时兜底）"""
    if df is None or len(df) == 0:
        return None
    cols = [c for c in ('close', 'high', 'low') if c in df.columns]
    if len(cols) < 3:
        return None
    d = df[cols].astype(float)
    keys = []
    for x in d.index:
        dt = to_date(x)
        if dt is None:
            keys.append('')
            continue
        iso = dt.isocalendar()
        keys.append('%04d%02d' % (iso[0], iso[1]))
    d = d.copy()
    d['__k'] = keys
    d = d[d['__k'] != '']
    if len(d) == 0:
        return None
    out_c, out_h, out_l, out_d = [], [], [], []
    for k, grp in d.groupby('__k'):
        out_c.append(float(grp['close'].iloc[-1]))
        out_h.append(float(grp['high'].max()))
        out_l.append(float(grp['low'].min()))
        out_d.append(grp.index[-1])
    return pd.DataFrame({'close': out_c, 'high': out_h, 'low': out_l}, index=out_d)


def get_week_data(ContextInfo, codes):
    """分批取周线数据（每批 CHUNK_SIZE 只），合并成 {代码: DataFrame}"""
    result = {}
    total = len(codes)
    for i in range(0, total, CHUNK_SIZE):
        batch = codes[i:i + CHUNK_SIZE]
        try:
            # fill_data=False：不要用前值填补停牌期间，否则停牌股看起来每周都有行情
            data = ContextInfo.get_market_data_ex(
                ['close', 'high', 'low', 'volume'], batch, period='1w',
                count=MAX_WEEK_BARS, dividend_type=DIVIDEND_TYPE, fill_data=False)
        except TypeError:
            # 老版本接口不支持部分关键字，逐级降级
            try:
                data = ContextInfo.get_market_data_ex(
                    ['close', 'high', 'low', 'volume'], batch, period='1w',
                    count=MAX_WEEK_BARS, fill_data=False)
            except TypeError:
                try:
                    data = ContextInfo.get_market_data_ex(
                        ['close', 'high', 'low', 'volume'], batch, period='1w', count=MAX_WEEK_BARS)
                except Exception as e:
                    _warn_data_error(e)
                    data = {}
            except Exception as e:
                _warn_data_error(e)
                data = {}
        except Exception as e:
            _warn_data_error(e)
            data = {}
        if data:
            result.update(data)
        # 兜底：QMT 没有这只票的周线时，用日线自己合成
        need = [c for c in batch if c not in result or result[c] is None or len(result[c]) < MIN_WEEK_BARS]
        if need:
            _dbg('周线缺失 %d 只，改用日线合成: %s' % (len(need), ','.join(need[:6])))
            for code in need:
                try:
                    d1 = ContextInfo.get_market_data_ex(
                        ['close', 'high', 'low'], [code], period='1d',
                        count=MAX_WEEK_BARS * 7, dividend_type=DIVIDEND_TYPE, fill_data=False)
                except TypeError:
                    d1 = ContextInfo.get_market_data_ex(
                        ['close', 'high', 'low'], [code], period='1d', count=MAX_WEEK_BARS * 7)
                except Exception as e:
                    _warn_data_error(e)
                    d1 = {}
                df = (d1 or {}).get(code)
                w = daily_to_weekly(df)
                if w is not None and len(w) >= MIN_WEEK_BARS:
                    result[code] = w
                    _dbg('%s 日线合成周线 %d 根，最后 %s' % (code, len(w), w.index[-1]))
                else:
                    _dbg('%s 日线也只有 %s 根，无法合成' % (code, 0 if df is None else len(df)))
    return result


_dbg_msgs = set()


def _dbg(msg):
    """调试信息：同类只打印一次，最多 30 条"""
    if msg in _dbg_msgs or len(_dbg_msgs) > 30:
        return
    _dbg_msgs.add(msg)
    print('[周线KDJ][调试] ' + msg)


_warned_msgs = set()


def _warn_once(msg):
    """同类提示只打印一次，避免回测日志刷屏"""
    if msg not in _warned_msgs:
        _warned_msgs.add(msg)
        print('[周线KDJ] ' + msg)


def _warn_data_error(e):
    """取数据失败只提示一次"""
    _warn_once('取周线数据失败：%s（请检查本地周线数据是否已下载完整）' % e)


def bar_date(ContextInfo):
    """当前K线日期，格式 YYYYMMDD"""
    return timetag_to_datetime(ContextInfo.get_bar_timetag(ContextInfo.barpos), '%Y%m%d')


def week_key(date_str):
    """把日期换成 ISO 周标识，用于“一周只调仓一次”"""
    try:
        d = datetime.date(int(date_str[0:4]), int(date_str[4:6]), int(date_str[6:8]))
        iso = d.isocalendar()
        return '%04d-W%02d' % (iso[0], iso[1])
    except Exception:
        return date_str


def is_new_week(ContextInfo, date_str):
    key = week_key(date_str)
    if key == getattr(ContextInfo, 'last_week', ''):
        return False
    ContextInfo.last_week = key
    return True


def resolve_pool(ContextInfo):
    """第一次用到时才解析股票池，避免 init 阶段一次性加载几百只股票的行情导致客户端崩溃"""
    pool = getattr(ContextInfo, 'stock_pool', None)
    if pool:
        return pool
    if STOCK_POOL:
        pool = [s for s in STOCK_POOL if s]
        name = '自定义股票池'
    else:
        try:
            pool = [s for s in ContextInfo.get_stock_list_in_sector(STOCK_POOL_SECTOR) if s]
        except Exception as e:
            _warn_data_error(e)
            pool = []
        name = STOCK_POOL_SECTOR
    if MAX_POOL > 0 and len(pool) > MAX_POOL:
        pool = pool[:MAX_POOL]
    ContextInfo.stock_pool = pool
    ContextInfo.pool_name = name
    print('[周线KDJ] 股票池「%s」共 %d 只：%s' % (name, len(pool), ','.join(pool[:8]) + ('...' if len(pool) > 8 else '')))
    return pool


# ------------------------------ 模型入口 --------------------------------------
def init(ContextInfo):
    # 这里刻意不调用 set_universe / 不设置基准：
    # 主图常常是指数（如 000300），一次把几百只股票塞进股票池会让客户端预加载大量行情，
    # 在回测启动阶段容易直接崩溃。行情改为在 handlebar 里按需分批获取。
    global ACC
    is_bt = True
    try:
        is_bt = bool(ContextInfo.do_back_test)
    except Exception:
        is_bt = True
    ACC = ACCOUNT if is_bt else LIVE_ACCOUNT
    # 回测区间直接写死，避免界面设置残留旧区间（300209 本地数据从 2025-01-08 才有）
    try:
        ContextInfo.start = BACKTEST_START
        ContextInfo.end = BACKTEST_END
    except Exception:
        pass
    ContextInfo.stock_pool = []
    ContextInfo.pool_name = ''
    ContextInfo.last_week = ''
    ContextInfo.buy_count = 0
    ContextInfo.sell_count = 0
    print('[周线KDJ] 初始化：%s，账号=%s；股票池=%s；KDJ(%d,%d,%d)，买入条件 K<%.0f 且金叉，'
          '最多持有 %d 只，单只 %.0f%% 仓位，止损=%s'
          % (('回测模式' if is_bt else '模拟/实盘模式'), ACC,
             (STOCK_POOL_SECTOR if not STOCK_POOL else '自定义'),
             KDJ_N, KDJ_M1, KDJ_M2, BUY_K, MAX_HOLD,
             POSITION_PCT * 100, ('关闭' if STOP_LOSS_PCT <= 0 else '%.0f%%' % (STOP_LOSS_PCT * 100))))


def handlebar(ContextInfo):
    date_str = bar_date(ContextInfo)
    if not is_new_week(ContextInfo, date_str):
        return          # 本周已经处理过，避免周内反复下单

    acc = get_account()
    if acc is None:
        print('[周线KDJ] %s 没有取到资金账号 %s，跳过本周' % (date_str, ACC))
        return
    total_asset = float(getattr(acc, 'm_dBalance', 0.0))
    cash = float(getattr(acc, 'm_dAvailable', 0.0))
    if total_asset <= 0:
        total_asset = cash

    positions = get_positions()
    pool = resolve_pool(ContextInfo)
    codes = list(dict.fromkeys(list(pool) + [p['code'] for p in positions.values()]))
    if not codes:
        return

    data = get_week_data(ContextInfo, codes)
    signals = {}
    max_bars = 0
    for code in codes:
        df = data.get(code)
        try:
            if df is not None and len(df) > max_bars:
                max_bars = len(df)
            sig = calc_signal(df)
        except Exception:
            sig = None
        if sig is not None:
            signals[code] = sig
    if not signals and max_bars >= MIN_WEEK_BARS:
        _warn_once('没有取到任何周线数据/信号：请确认本地已下载周线数据（数据管理->补充数据），'
                   '并检查回测区间是否足够长')

    # 丢掉停牌/退市股：
    #   1) 周线最后一根K线的成交量 <= 0（停牌当周没有成交）
    #   2) 最后一根K线距离当前超过 STALE_DAYS 天
    # 否则这些股票会永远停在某个金叉上，被反复下单却永远不成交
    cur_day = to_date(date_str)
    fresh = {}
    stale_cnt = 0
    for code, sig in signals.items():
        if sig.get('last_vol', 1.0) <= 0:
            stale_cnt += 1
            continue
        ld = to_date(sig.get('last_date', ''))
        if cur_day is not None and ld is not None and (cur_day - ld).days > STALE_DAYS:
            stale_cnt += 1
            continue
        fresh[code] = sig
    signals = fresh
    if stale_cnt and ContextInfo.buy_count + ContextInfo.sell_count == 0:
        print('[周线KDJ] %s 跳过 %d 只停牌/无行情股票（全市场 %d 只有信号）'
              % (date_str, stale_cnt, len(signals)))
    sig_by_id = {}
    for code, sig in signals.items():
        sig_by_id[code_id(code)] = sig

    # 主图品种的 KDJ 画到图上，方便肉眼核对
    main_code = '%s.%s' % (ContextInfo.stockcode, ContextInfo.market)
    if main_code in signals:
        try:
            ContextInfo.paint('KDJ_K', signals[main_code]['k'], -1, 0)
            ContextInfo.paint('KDJ_D', signals[main_code]['d'], -1, 0)
            ContextInfo.paint('KDJ_J', signals[main_code]['j'], -1, 0)
        except Exception:
            pass

    # ---------------- 先卖：死叉 或 触发止损 ----------------
    sell_proceeds = 0.0
    for pid in list(positions.keys()):
        pos = positions[pid]
        sig = sig_by_id.get(pid)
        if sig is None:
            continue
        reason = ''
        if sig['death']:
            reason = '周线KDJ死叉 K=%.1f D=%.1f' % (sig['k'], sig['d'])
        elif STOP_LOSS_PCT > 0 and pos['cost'] > 0 and \
                sig['close'] <= pos['cost'] * (1.0 - STOP_LOSS_PCT):
            reason = '止损 %.1f%%（成本%.2f 现价%.2f）' % (
                (sig['close'] / pos['cost'] - 1.0) * 100.0, pos['cost'], sig['close'])
        if not reason:
            continue
        vol = int(pos['can'] if pos['can'] > 0 else pos['vol'])
        if vol <= 0:
            continue
        passorder(24, 1101, ACC, pos['code'], 5, -1, vol, ContextInfo)
        sell_proceeds += vol * sig['close']
        ContextInfo.sell_count += 1
        print('[周线KDJ] %s 卖出 %s %d股 参考价%.2f（%s）'
              % (date_str, pos['code'], vol, sig['close'], reason))
        del positions[pid]

    # ---------------- 再买：低位金叉，按 K 值从小到大挑 ----------------
    bought = 0
    slots = MAX_HOLD - len(positions)
    candidates = []
    if slots > 0:
        for code, sig in signals.items():
            if code_id(code) in positions:
                continue
            if sig['golden'] and sig['k'] < BUY_K:
                candidates.append((sig['k'], code, sig))
    if candidates:
        candidates.sort(key=lambda x: x[0])
        budget = total_asset * POSITION_PCT
        available = cash + sell_proceeds      # 卖出资金当日可用于买入
        for _, code, sig in candidates:
            if bought >= slots:
                break
            amount = min(budget, available * 0.98)
            if amount < MIN_BUY_AMOUNT:
                break
            passorder(23, 1102, ACC, code, 5, -1, int(amount), ContextInfo)
            available -= amount
            bought += 1
            ContextInfo.buy_count += 1
            print('[周线KDJ] %s 买入 %s 约%d元 参考价%.2f（金叉 K=%.1f D=%.1f J=%.1f）'
                  % (date_str, code, int(amount), sig['close'], sig['k'], sig['d'], sig['j']))

    print('[周线KDJ] %s 本周处理完毕：总资产%.0f 下单前可用%.0f 持仓%d只 累计买入%d次 卖出%d次'
          % (date_str, total_asset, cash, len(positions) + bought,
             ContextInfo.buy_count, ContextInfo.sell_count))







