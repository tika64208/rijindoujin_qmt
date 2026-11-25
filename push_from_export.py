# -*- coding: utf-8 -*-
"""
push_from_export.py -- 把竞价分析 App 的当日导出，按预设筛完后推给 QMT。

链路：
    竞价分析 App 09:29 快照导出
        -> export/竞价数据_YYYY-MM-DD.csv
        -> 本脚本按 HIGH_WIN_RATE 预设筛选、按概率排序
        -> GET http://127.0.0.1:8765/set?codes=...   (list_server.py)
        -> QMT 策略 autobuy_from_list.py 在 09:30 拉取并买入

用法：
    python push_from_export.py                 # 取最新导出，推送
    python push_from_export.py --dry           # 只打印，不推送
    python push_from_export.py --top 3         # 最多 3 只
    python push_from_export.py --file 竞价数据_2026-11-05.csv
    python push_from_export.py --date 20261105 # 指定日期

建议：Windows 计划任务 09:29:40 执行。
"""
import argparse
import csv
import glob
import io
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bid_rules as R

EXPORT_DIR = r'F:\ai\deepseekharness\竞价分析\export'
SERVER = 'http://127.0.0.1:8765'
AUDIT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')


def newest_csv(export_dir, date_tag=None):
    if date_tag:
        pat = os.path.join(export_dir, '竞价数据_%s-%s-%s.csv'
                           % (date_tag[:4], date_tag[4:6], date_tag[6:8]))
        return pat if os.path.exists(pat) else None
    files = glob.glob(os.path.join(export_dir, '竞价数据_*.csv'))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def load(path):
    """读取导出 CSV。优先采用 App 冻结的评分（app_prob/app_conf/app_score），
    只有缺失时才用重算值 —— 与 App 自己的口径一致：禁止事后重算。"""
    rows = []
    with io.open(path, 'r', encoding='utf-8-sig', newline='') as fh:
        for raw in csv.DictReader(fh):
            row = R.build_row(raw)
            if row['app_prob'] > 0:
                row['calc_prob'], row['calc_conf'], row['calc_score'] = row['prob'], row['conf'], row['score']
                row['prob'], row['conf'], row['score'] = row['app_prob'], row['app_conf'], row['app_score']
            rows.append(row)
    return rows


def push(codes, server=SERVER, timeout=5):
    q = urllib.parse.urlencode({'codes': ','.join(codes)})
    url = '%s/set?%s' % (server.rstrip('/'), q)
    r = urllib.request.urlopen(url, timeout=timeout)
    return r.read().decode('utf-8', 'ignore').strip()


def read_back(server=SERVER, timeout=5):
    r = urllib.request.urlopen('%s/today.csv' % server.rstrip('/'), timeout=timeout)
    return r.read().decode('utf-8', 'ignore').strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='')
    ap.add_argument('--date', default='')
    ap.add_argument('--top', type=int, default=5)
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--export-dir', default=EXPORT_DIR)
    args = ap.parse_args()

    path = args.file or newest_csv(args.export_dir, args.date)
    if not path or not os.path.exists(path):
        print('[push] 找不到导出文件: %s' % (path or '(空)'))
        return 1
    print('[push] 源文件: %s (%s)' % (os.path.basename(path),
                                     __import__('time').strftime('%Y-%m-%d %H:%M',
                                                                 __import__('time').localtime(
                                                                     os.path.getmtime(path)))))

    rows = load(path)
    picked_all = R.select(rows)
    picked = picked_all[:args.top]
    print('[push] 全市场 %d 行 -> 预设入选 %d 只 -> 取前 %d 只'
          % (len(rows), len(picked_all), len(picked)))
    if picked:
        print(R.fmt_table(picked))

    # 落一份审计记录
    try:
        if not os.path.isdir(AUDIT_DIR):
            os.makedirs(AUDIT_DIR)
        tag = os.path.basename(path).replace('竞价数据_', '').replace('.csv', '')
        audit = os.path.join(AUDIT_DIR, 'push_%s.json' % tag)
        payload = {
            'source': path,
            'total_rows': len(rows),
            'selected': len(picked_all),
            'pushed': [{'code': r['code'], 'name': r['name'],
                        'bid_change': r['bid_change'], 'prob': r['prob'],
                        'conf': r['conf'], 'score': r['score'],
                        'mv_yi': round(r['mv_yi'], 1)} for r in picked],
        }
        io.open(audit, 'w', encoding='utf-8').write(
            json.dumps(payload, ensure_ascii=False, indent=2))
        print('[push] 审计记录: %s' % audit)
    except Exception as e:
        print('[push] 审计写入失败: %s' % e)

    if not picked:
        print('[push] 今天没有符合条件的票，跳过推送')
        return 0

    codes = [r['qmt_code'] for r in picked]
    if args.dry:
        print('[push][DRY] 将推送: %s' % ','.join(codes))
        return 0

    try:
        resp = push(codes)
        print('[push] 服务端返回: %s' % resp)
        back = read_back()
        print('[push] QMT 将读到: %s' % back)
        if set(c for c in back.split(',') if c) != set(codes):
            print('[push][WARN] 回读与推送不一致！')
            return 2
    except Exception as e:
        print('[push] 推送失败: %s' % e)
        print('[push] 检查 list_server.py 是否在运行（端口 8765）')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())


