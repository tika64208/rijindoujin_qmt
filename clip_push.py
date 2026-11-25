# -*- coding: utf-8 -*-
"""
clip_push.py -- 把今日名单写进 Windows 剪贴板，交给 QMT 策略读。

背景：国金 QMT 2.1.36 的「防外接」会杀掉任何访问网络的策略进程，
      策略里 open() 也被 Forbidden fileIO 拦掉。剪贴板是唯一还能通
      的本地通道（已在 QMT 里实测：ctypes 读 user32 可以拿到内容）。

安全约束（2026-11-24 加固）：
  1. 只接受「文件名日期 == 今天」的导出文件；没有就报错退出（码 2），
     绝不拿几天前的名单冒充今天。
  2. --watch 每次循环重读 CSV：导出晚到也能补上；名单变了会在 09:30 前
     换新载荷，09:30 之后只重写旧载荷（不追涨杀跌）。
  3. 载荷时间戳即 token，QMT 侧按 token 去重，同一份名单只下一次。

用法：
    python clip_push.py                      # 取今天的导出，写剪贴板
    python clip_push.py --dry                # 只打印载荷，不写剪贴板
    python clip_push.py --top 3              # 最多 3 只
    python clip_push.py --codes 300209,002843   # 手工指定代码（不校验日期）
    python clip_push.py --watch              # 每 2 秒对齐一次，直到 --until（默认 093130）
    python clip_push.py --file xx.csv --allow-old   # 回放/测试用

建议：计划任务 09:29:40 跑 `--watch`。
"""
import argparse
import csv
import datetime
import glob
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bid_rules as R

MAGIC = 'QMTCLIP1'
EXPORT_DIR = r'F:\ai\deepseekharness\竞价分析\export'
AUDIT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
WIN_START = '093000'


# ----------------------------------------------------------------- 载荷

def _sig(s):
    """与 QMT 策略端完全一致的校验和"""
    h = 7
    for ch in s:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return '%08X' % h


def build_payload(codes, ts=None):
    ts = ts or datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    body = '%s|%s|%s' % (MAGIC, ts, ','.join(codes))
    return '%s|%s' % (body, _sig(body))


# ------------------------------------------------------------- 剪贴板

def set_clipboard(text):
    """把文本写进 Windows 剪贴板（ctypes，无需 pywin32）"""
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    GMEM_MOVEABLE = 0x0002
    CF_UNICODETEXT = 13

    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = wintypes.LPVOID
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalUnlock.restype = wintypes.BOOL
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.OpenClipboard.restype = wintypes.BOOL
    u32.EmptyClipboard.restype = wintypes.BOOL
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    u32.SetClipboardData.restype = wintypes.HANDLE
    u32.CloseClipboard.restype = wintypes.BOOL

    data = text.encode('utf-16-le') + b'\x00\x00'
    if not u32.OpenClipboard(None):
        raise RuntimeError('OpenClipboard 失败（别的程序正占用剪贴板？）')
    try:
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            raise MemoryError('GlobalAlloc 失败')
        p = k32.GlobalLock(h)
        if not p:
            raise MemoryError('GlobalLock 失败')
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        if not u32.SetClipboardData(CF_UNICODETEXT, h):
            raise RuntimeError('SetClipboardData 失败')
    finally:
        u32.CloseClipboard()


def get_clipboard():
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.OpenClipboard.restype = wintypes.BOOL
    u32.GetClipboardData.argtypes = [wintypes.UINT]
    u32.GetClipboardData.restype = wintypes.HANDLE
    u32.CloseClipboard.restype = wintypes.BOOL
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = wintypes.LPVOID
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalUnlock.restype = wintypes.BOOL
    if not u32.OpenClipboard(None):
        return None
    try:
        h = u32.GetClipboardData(13)
        if not h:
            return None
        p = k32.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.wstring_at(p)
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


# ------------------------------------------------------------- 数据源

def today_tag():
    return datetime.datetime.now().strftime('%Y%m%d')


def csv_tag(path):
    """竞价数据_2026-11-24.csv -> 20261124"""
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})\.csv$', os.path.basename(path))
    if not m:
        return None
    return m.group(1) + m.group(2) + m.group(3)


def _csvs_by_mtime(export_dir):
    files = glob.glob(os.path.join(export_dir, '竞价数据_*.csv'))
    return sorted(files, key=os.path.getmtime, reverse=True)


def newest_csv(export_dir, date_tag=None):
    if date_tag:
        pat = os.path.join(export_dir, '竞价数据_%s-%s-%s.csv'
                           % (date_tag[:4], date_tag[4:6], date_tag[6:8]))
        return pat if os.path.exists(pat) else None
    files = _csvs_by_mtime(export_dir)
    return files[0] if files else None


def resolve_today(args):
    """-> (path, why)。没有今天的文件时 path=None"""
    if args.file:
        if not os.path.exists(args.file):
            return None, '文件不存在 %s' % args.file
        tag = csv_tag(args.file)
        if tag != today_tag() and not args.allow_old:
            return None, '%s 不是今天的（%s），要回放请加 --allow-old' % (
                os.path.basename(args.file), tag)
        return args.file, 'explicit'

    if args.date:
        p = newest_csv(args.export_dir, args.date)
        if not p:
            return None, '没有 --date %s 的导出' % args.date
        return p, 'explicit date'

    for f in _csvs_by_mtime(args.export_dir):
        if csv_tag(f) == today_tag():
            return f, 'today'
    latest = _csvs_by_mtime(args.export_dir)
    if latest:
        return None, '最新的是 %s（%s），不是今天' % (
            os.path.basename(latest[0]), csv_tag(latest[0]))
    return None, '%s 里没有 竞价数据_*.csv' % args.export_dir


def load_rows(path):
    rows = []
    with io.open(path, 'r', encoding='utf-8-sig', newline='') as fh:
        for raw in csv.DictReader(fh):
            row = R.build_row(raw)
            if row['app_prob'] > 0:
                row['calc_prob'], row['calc_conf'], row['calc_score'] = row['prob'], row['conf'], row['score']
                row['prob'], row['conf'], row['score'] = row['app_prob'], row['app_conf'], row['app_score']
            rows.append(row)
    return rows


def pick_codes(path, top):
    rows = load_rows(path)
    picked_all = R.select(rows)
    picked = picked_all[:top]
    return rows, picked_all, picked


def audit(path, rows, picked_all, picked, payload):
    try:
        if not os.path.isdir(AUDIT_DIR):
            os.makedirs(AUDIT_DIR)
        tag = datetime.datetime.now().strftime('%Y%m%d')
        out = os.path.join(AUDIT_DIR, 'clip_%s.json' % tag)
        payload_obj = {
            'source': path,
            'total_rows': len(rows),
            'selected': len(picked_all),
            'payload': payload,
            'pushed': [{'code': r['code'], 'name': r['name'],
                        'bid_change': r['bid_change'], 'prob': r['prob'],
                        'conf': r['conf'], 'score': r['score'],
                        'mv_yi': round(r['mv_yi'], 1)} for r in picked],
        }
        io.open(out, 'w', encoding='utf-8').write(
            json.dumps(payload_obj, ensure_ascii=False, indent=2))
        return out
    except Exception as e:
        print('[clip] 审计写入失败: %s' % e)
        return None


def _hm_now():
    return datetime.datetime.now().strftime('%H%M%S')


# ------------------------------------------------------------------ main

def _push(payload, path, rows, picked_all, picked, dry=False):
    print('[clip] 载荷: %s' % payload)
    audit(path, rows, picked_all, picked, payload)
    if dry:
        return True
    set_clipboard(payload)
    back = get_clipboard()
    ok = (back == payload)
    print('[clip] 回读: %s%s' % (back, '' if ok else '  <-- 不一致!'))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='')
    ap.add_argument('--date', default='')
    ap.add_argument('--top', type=int, default=5)
    ap.add_argument('--codes', default='')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--watch', action='store_true')
    ap.add_argument('--every', type=float, default=2.0)
    ap.add_argument('--until', default='093130')
    ap.add_argument('--allow-old', action='store_true')
    ap.add_argument('--export-dir', default=EXPORT_DIR)
    args = ap.parse_args()

    # ---- 手工代码：不校验日期，用于测试/补单
    if args.codes:
        codes = [c.strip() for c in args.codes.replace('，', ',').split(',') if c.strip()]
        payload = build_payload(codes)
        print('[clip] 手工代码 %d 只: %s' % (len(codes), ','.join(codes)))
        if args.dry:
            print('[clip] 载荷: %s' % payload)
            return 0
        set_clipboard(payload)
        print('[clip] 已写入剪贴板，回读: %s' % get_clipboard())
        return 0

    pushed_payload = None      # 已写进剪贴板的载荷（token 固定）
    pushed_codes = None
    last_mtime = 0.0
    last_note = ''
    saw_today_file = False

    while True:
        if args.watch and _hm_now() > args.until:
            break

        path, why = resolve_today(args)
        if not path:
            note = '[clip] 等今天的导出：%s' % why
            if note != last_note:
                print(note)
                last_note = note
        else:
            saw_today_file = True
            mtime = os.path.getmtime(path)
            if pushed_payload is None or mtime != last_mtime:
                last_mtime = mtime
                try:
                    rows, picked_all, picked = pick_codes(path, args.top)
                except Exception as e:
                    print('[clip] 解析失败 %s: %s' % (path, e))
                    picked = []

                if not picked:
                    print('[clip] %s：今天没有符合条件的票，不写剪贴板'
                          % os.path.basename(path))
                else:
                    codes = [r['qmt_code'] for r in picked]
                    print('[clip] 源文件 %s：%d 行 -> 入选 %d 只 -> 取前 %d 只'
                          % (os.path.basename(path), len(rows), len(picked_all), len(picked)))
                    print(R.fmt_table(picked))
                    if pushed_payload is None:
                        payload = build_payload(codes)
                        if _push(payload, path, rows, picked_all, picked, args.dry):
                            pushed_payload, pushed_codes = payload, codes
                    elif codes != pushed_codes:
                        if _hm_now() < WIN_START:
                            payload = build_payload(codes)
                            print('[clip] 名单有更新，换新载荷（token 变化，QMT 会重判）')
                            if _push(payload, path, rows, picked_all, picked, args.dry):
                                pushed_payload, pushed_codes = payload, codes
                        else:
                            print('[clip] 09:30 之后名单变了，保持原载荷不追单')

        # 守护：载荷被别的程序覆盖掉就补回去
        if pushed_payload and not args.dry:
            try:
                if get_clipboard() != pushed_payload:
                    set_clipboard(pushed_payload)
            except Exception as e:
                print('[clip] 重写剪贴板失败: %s' % e)

        if not args.watch:
            break
        time.sleep(args.every)

    if pushed_payload is None:
        if saw_today_file:
            print('[clip] 结束：今天没有入选的票，不推（正常空仓日）')
            return 0
        print('[clip] 结束：这次没有任何载荷被推送（没有今天的导出？）')
        return 2
    if args.dry:
        return 0
    print('[clip] 结束：已推送 %s' % pushed_payload)
    return 0


if __name__ == '__main__':
    sys.exit(main())
