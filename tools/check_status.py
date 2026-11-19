# -*- coding: utf-8 -*-
"""
check_status.py -- 一条命令确认整条链路是否在运行。

检查四件事：
  1. list_server 是否活着（端口 8765）+ 当前名单 + 最后一次被 QMT 拉取的时间
  2. 今天有没有推送过（out/push_*.json）+ export 目录里最新 CSV 是哪天
  3. QMT 客户端是否在跑 + 今天的策略日志里有没有 [AUTO]/[SELL] 记录
  4. Windows 计划任务里有没有那条 09:29 推送

用法：
    python check_status.py
退出码：0 = 全部正常；1 = 有异常（方便挂到监控里）
"""
import glob
import io
import json
import os
import re
import subprocess
import sys
import urllib.request

W = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.environ.get('JJB_EXPORT_DIR') or r'F:\qmt\竞价分析\export'
QMT_LOG_DIR = os.environ.get('QMT_LOG_DIR') or r'D:\qmt\userdata\log'
SERVER = 'http://127.0.0.1:8765'
TASK_KEYWORD = 'push_from_export'

OK, WARN, BAD = '[ OK ]', '[WARN]', '[BAD ]'


def http_get(path, timeout=3):
    r = urllib.request.urlopen(SERVER + path, timeout=timeout)
    return r.read().decode('utf-8', 'ignore')


def check_server():
    print('--- 1. 名单服务 (list_server) ---')
    try:
        page = http_get('/')
    except Exception as e:
        print(BAD, '127.0.0.1:8765 连不上:', e)
        print('      → 启动: D:\\国金QMT交易端模拟\\bin.x64\\pythonw.exe "%s"' % os.path.join(W, 'list_server.py'))
        return False
    info = {}
    for line in page.splitlines():
        if ':' in line:
            k, v = line.split(':', 1)
            info[k.strip()] = v.strip()
    codes = [c for c in info.get('codes', '').split(',') if c and c != '(empty)']
    print(OK, '服务在跑')
    print('      名单:', ('%d 只 -> %s' % (len(codes), ','.join(codes[:6]))) if codes else '空（今天还没推送）')
    print('      最后推送:', info.get('updated', '-'))
    print('      最后被拉取:', info.get('last get', '-'), '（QMT 每次轮询都会刷新）')
    return True


def check_push():
    print('--- 2. 推送与数据源 ---')
    csvs = sorted(glob.glob(os.path.join(EXPORT, '竞价数据_*.csv')), key=os.path.getmtime)
    if not csvs:
        print(BAD, 'export 目录里没有任何 竞价数据_*.csv')
        return False
    newest = csvs[-1]
    print(OK, '最新导出:', os.path.basename(newest),
          '(%s)' % __import__('time').strftime('%Y-%m-%d %H:%M', __import__('time').localtime(os.path.getmtime(newest))))

    audits = sorted(glob.glob(os.path.join(W, 'out', 'push_*.json')), key=os.path.getmtime)
    if not audits:
        print(WARN, '还没有任何推送审计文件（今天没推过）')
        print('      → 手动试: pythonw "%s" --dry' % os.path.join(W, 'push_from_export.py'))
        return True
    a = audits[-1]
    try:
        data = json.load(io.open(a, encoding='utf-8'))
    except Exception:
        data = {}
    print(OK, '最近推送:', os.path.basename(a),
          '| 入选 %s 只 | 推送 %d 只' % (data.get('selected', '?'), len(data.get('pushed', []))))
    return True


def check_qmt():
    print('--- 3. QMT 客户端与策略日志 ---')
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq XtItClient.exe'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        txt = out.stdout.decode('gbk', 'ignore')
        running = 'XtItClient.exe' in txt
    except Exception as e:
        print(WARN, '查询进程失败:', e)
        running = None
    if running is False:
        print(BAD, 'QMT 客户端没在运行')
    elif running:
        print(OK, 'QMT 客户端在运行')

    logs = sorted(glob.glob(os.path.join(QMT_LOG_DIR, 'XtClient_FormulaOutput_*.log')))
    if not logs:
        print(WARN, '找不到策略日志')
        return False
    log = logs[-1]
    print('      最新日志:', os.path.basename(log))
    try:
        text = io.open(log, encoding='utf-8', errors='ignore').read()
    except Exception:
        text = ''
    auto = len(re.findall(r'\[AUTO ', text))
    sell = len(re.findall(r'\[SELL ', text))
    buy_order = len(re.findall(r'\[AUTO .*?ORDER ', text))
    sell_order = len(re.findall(r'\[SELL .*?ORDER ', text))
    print('      [AUTO] 记录 %d 条（真实下单 %d）| [SELL] 记录 %d 条（真实下单 %d）'
          % (auto, buy_order, sell, sell_order))
    if auto == 0 and sell == 0:
        print(WARN, '日志里还没有策略输出 —— 两个策略都启动了吗？')
    else:
        # 最后几条
        tails = [l for l in text.splitlines() if '[AUTO ' in l or '[SELL ' in l][-3:]
        for t in tails:
            print('      >', t.strip()[:120])
    return True


def check_task():
    print('--- 4. Windows 计划任务 ---')
    try:
        out = subprocess.run(['schtasks', '/Query', '/FO', 'LIST'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        txt = out.stdout.decode('gbk', 'ignore')
        if TASK_KEYWORD in txt:
            print(OK, '已找到计划任务（包含 push_from_export）')
            return True
        print(WARN, '没找到包含 "%s" 的计划任务' % TASK_KEYWORD)
        print('      → 每天 09:29:40 需要它自动推送，否则只能手动跑')
        return True
    except Exception as e:
        print(WARN, '查询计划任务失败:', e)
        return True


def main():
    print('=' * 60)
    print('链路体检', __import__('time').strftime('%Y-%m-%d %H:%M:%S'))
    print('=' * 60)
    r1 = check_server()
    print()
    r2 = check_push()
    print()
    r3 = check_qmt()
    print()
    check_task()
    print()
    check_window()
    print()
    print('=' * 60)
    if r1 and r2:
        print('结论: 核心链路（服务+数据）正常')
    else:
        print('结论: 有环节异常，见上面 [BAD] 项')
    print('=' * 60)
    return 0 if (r1 and r2) else 1


if __name__ == '__main__':
    sys.exit(main())

def check_window():
    """距离下一个动作还有多久"""
    print('--- 5. 时间窗 ---')
    import time as _t
    now = _t.localtime()
    hm = _t.strftime('%H%M%S', now)
    print('      现在:', _t.strftime('%Y-%m-%d %H:%M:%S', now))
    if hm < '092800':
        print('      下一动作: 09:28 导出CSV -> 09:29:40 推送 -> 09:30:05 买入')
    elif hm < '093130':
        print('      正在买入窗口内（09:30:00-09:31:30）')
    elif hm < '145000':
        print('      已过买入窗口；下一动作: 14:50 卖出')
    elif hm < '145700':
        print('      正在卖出窗口内（14:50:00-14:56:30）')
    else:
        print('      今日动作已结束；明日 09:28 再开始')
    print('      注意: 周末/节假日不会自动空转，策略仍会尝试，但没有新导出会推送失败')
