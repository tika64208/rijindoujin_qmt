# -*- coding: utf-8 -*-
"""
log_sync.py -- 把 QMT 客户端日志增量上传到日志服务。

用法：
    python log_sync.py                 # 只传策略输出日志 FormulaOutput
    python log_sync.py --all           # 传 log 目录下所有 .log
    python log_sync.py --pattern "XtClient_2026*.log"
    python log_sync.py --reset         # 清掉进度，全部重传

进度存在 out/logsync_state.json（按文件记录已发送的字节数），重复运行只发增量。
上传是并发的（默认 6 线程），失败会重试并把进度回退到最后一个完整窗口。
"""
import argparse
import glob
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

LOGDIR = r'D:\国金QMT交易端模拟\userdata\log'
BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, 'out', 'logsync_state.json')
URL = 'https://padded-counting-splendor.ngrok-free.dev/api/logs/ingest'
API_KEY = 'qk-7f3a9d2c5b8e41a6'

CHUNK = 32 * 1024
WINDOW = 16              # 每个窗口的块数（并发送出、整窗成功才前进）
WORKERS = 2
RETRY = 6
TIMEOUT = 30


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(io.open(STATE, 'r', encoding='utf-8'))
        except Exception:
            return {}
    return {}


def save_state(st):
    d = os.path.dirname(STATE)
    if not os.path.isdir(d):
        os.makedirs(d)
    tmp = STATE + '.tmp'
    io.open(tmp, 'w', encoding='utf-8').write(json.dumps(st, ensure_ascii=False, indent=1))
    os.replace(tmp, STATE)


def post(source, name, offset, raw):
    qs = urllib.parse.urlencode({'source': source, 'file': name, 'offset': offset})
    body = raw.decode('utf-8', 'replace').encode('utf-8')
    last = ''
    for i in range(RETRY):
        try:
            req = urllib.request.Request(
                URL + '?' + qs, data=body,
                headers={'X-API-Key': API_KEY, 'Content-Type': 'text/plain; charset=utf-8'},
                method='POST')
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                code = r.getcode()
                if 200 <= code < 300:
                    return True, str(code)
                last = 'http %s' % code
                if code == 413 and len(raw) > 4096:
                    mid = len(raw) // 2
                    ok1, i1 = post(source, name, offset, raw[:mid])
                    if not ok1:
                        return False, i1
                    return post(source, name, offset + mid, raw[mid:])
        except urllib.error.HTTPError as e:
            last = 'http %s' % e.code
            if e.code == 413 and len(raw) > 4096:
                mid = len(raw) // 2
                ok1, i1 = post(source, name, offset, raw[:mid])
                if not ok1:
                    return False, i1
                return post(source, name, offset + mid, raw[mid:])
        except Exception as e:
            last = '%s: %s' % (type(e).__name__, str(e)[:60])
        time.sleep(1.0 + i * 2)
    return False, last


def files_to_send(args):
    pat = os.path.join(LOGDIR, '*.log' if args.all else args.pattern)
    return sorted(glob.glob(pat))


def upload_file(pool, source, name, path, start, st, budget_left):
    size = os.path.getsize(path)
    off = start
    sent = 0
    with open(path, 'rb') as fh:
        while off < size:
            window = []
            pos = off
            while len(window) < WINDOW and pos < size:
                fh.seek(pos)
                raw = fh.read(CHUNK)
                if not raw:
                    break
                window.append((pos, raw))
                pos += len(raw)
            if not window:
                break
            if budget_left is not None and sent >= budget_left:
                return sent, off, 'budget'
            results = list(pool.map(lambda it: (it[0], len(it[1]),
                                                post(source, name, it[0], it[1])), window))
            bad = [(o, n) for o, n, (ok, _) in results if not ok]
            info = ''
            for o, n, (ok, i) in results:
                if not ok:
                    info = i
            if bad:
                return sent, off, 'fail@%d %s' % (bad[0][0], info)
            off = window[-1][0] + len(window[-1][1])
            sent += sum(n for _, n, _ in results)
            st[name] = off
            save_state(st)
            time.sleep(0.3)
            print('[sync] %-42s @%-10d (%.1f MB this run)' % (name, off, sent / 1048576.0), flush=True)
    return sent, off, ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--pattern', default='XtClient_FormulaOutput_*.log')
    ap.add_argument('--source', default='qmt-main')
    ap.add_argument('--reset', action='store_true')
    ap.add_argument('--limit-mb', type=float, default=0)
    args = ap.parse_args()

    st = {} if args.reset else load_state()
    files = files_to_send(args)
    budget = args.limit_mb * 1048576.0 if args.limit_mb > 0 else None
    total = 0
    t0 = time.time()
    failed = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for path in files:
            name = os.path.basename(path)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            off = int(st.get(name, 0))
            if size < off:
                off = 0
            if size == off:
                continue
            left = None if budget is None else max(0, budget - total)
            if left is not None and left <= 0:
                print('[sync] budget reached', flush=True)
                break
            sent, end, err = upload_file(pool, args.source, name, path, off, st, left)
            total += sent
            if err.startswith('fail'):
                failed += 1
                print('[sync] FAIL %s: %s' % (name, err), flush=True)
            elif err == 'budget':
                print('[sync] budget reached mid-file', flush=True)
                break

    save_state(st)
    print('[sync] done: %.1f MB, failed=%d, %.1fs' % (total / 1048576.0, failed, time.time() - t0), flush=True)
    return 0 if failed == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
