# -*- coding: utf-8 -*-
"""
list_server.py v2 -- 名单服务 + 心跳汇聚 + HTML 看板

接口
    GET  /today.csv                 今日名单（QMT 策略拉这个）
    GET  /set?codes=a,b,c           推送名单（push_from_export.py 调用）
    GET  /hb?role=buy|sell&n=<计数器>  QMT 每秒心跳
    GET  /status                    聚合状态 JSON（看板每秒拉）
    GET  /                           HTML 看板
    GET  /ping                      极简存活探测

启动
    D:\\国金QMT交易端模拟\\bin.x64\\pythonw.exe list_server.py
    或双击 启动.bat
"""
import http.server
import io
import json
import os
import re
import socketserver
import subprocess
import threading
import time

HOST = '127.0.0.1'
PORT = 8765

W = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(W, 'board.html')
OUT_DIR = os.path.join(W, 'out')
EXPORT_DIR = os.environ.get('JJB_EXPORT_DIR') or r'F:\qmt\竞价分析\export'
LOG_DIR = os.environ.get('QMT_LOG_DIR') or r'D:\qmt\userdata\log'
TASK_NAME = 'QMT竞价推送'
CSV_PREFIX = '\u7ade\u4ef7\u6570\u636e'      # 竞价数据

T0 = time.time()

_state = {
    'codes': [],
    'updated': None,
    'last_get': None,
    'gets': 0,
    'heart': {},
    'events': [],
}
_lock = threading.Lock()

_log_cache = {'path': None, 'mtime': 0, 'data': None}
_task_cache = {'ts': 0, 'installed': None}
_csv_cache = {'mtime': 0, 'info': None}
_proc_cache = {'ts': 0, 'alive': None}


def _now_str():
    return time.strftime('%H:%M:%S')


def _event(tag, text):
    with _lock:
        _state['events'].append({'t': _now_str(), 'tag': tag, 'text': text})
        if len(_state['events']) > 40:
            _state['events'] = _state['events'][-40:]


def _parse_log():
    tag = time.strftime('%Y%m%d')
    path = os.path.join(LOG_DIR, 'XtClient_FormulaOutput_%s.log' % tag)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {'file': os.path.basename(path), 'exists': False,
                'auto': [], 'sell': [], 'buy_orders': 0, 'sell_orders': 0}
    if _log_cache['path'] == path and _log_cache['mtime'] == mtime and _log_cache['data']:
        return _log_cache['data']

    data = {'file': os.path.basename(path), 'exists': True,
            'auto': [], 'sell': [], 'buy_orders': 0, 'sell_orders': 0}
    try:
        with io.open(path, 'r', encoding='utf-8', errors='ignore') as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 400000))
            text = fh.read()
        for m in re.finditer(r'\[AUTO (\d{2}:\d{2}:\d{2})\]([^\n]{0,160})', text):
            data['auto'].append([m.group(1), m.group(2).strip()])
        for m in re.finditer(r'\[SELL (\d{2}:\d{2}:\d{2})\]([^\n]{0,160})', text):
            data['sell'].append([m.group(1), m.group(2).strip()])
        data['buy_orders'] = len(re.findall(r'\[AUTO .*?ORDER ', text))
        data['sell_orders'] = len(re.findall(r'\[SELL .*?ORDER ', text))
    except Exception as e:
        data['error'] = str(e)

    _log_cache.update({'path': path, 'mtime': mtime, 'data': data})
    return data


def _csv_info():
    try:
        mtime = os.path.getmtime(EXPORT_DIR)
    except OSError:
        return {'name': None}
    if _csv_cache['info'] and _csv_cache['mtime'] == mtime:
        return _csv_cache['info']
    info = {'name': None}
    try:
        best = None
        for fn in os.listdir(EXPORT_DIR):
            if fn.endswith('.csv') and fn.startswith(CSV_PREFIX):
                p = os.path.join(EXPORT_DIR, fn)
                mt = os.path.getmtime(p)
                if best is None or mt > best[1]:
                    best = (fn, mt)
        if best:
            info = {'name': best[0],
                    'mtime': time.strftime('%Y-%m-%d %H:%M', time.localtime(best[1])),
                    'date': best[0].replace(CSV_PREFIX + '_', '').replace('.csv', '')}
    except Exception:
        pass
    _csv_cache.update({'mtime': mtime, 'info': info})
    return info


def _audit_info():
    try:
        files = sorted([f for f in os.listdir(OUT_DIR) if f.startswith('push_')],
                       key=lambda f: os.path.getmtime(os.path.join(OUT_DIR, f)))
        if not files:
            return {'name': None}
        f = files[-1]
        p = os.path.join(OUT_DIR, f)
        d = {}
        try:
            d = json.load(io.open(p, encoding='utf-8'))
        except Exception:
            pass
        return {'name': f,
                'date': f.replace('push_', '').replace('.json', ''),
                'mtime': time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(p))),
                'selected': d.get('selected'),
                'pushed': len(d.get('pushed', []))}
    except Exception:
        return {'name': None}


def _qmt_alive():
    """真实查一次 QMT 进程，缓存 10 秒"""
    if time.time() - _proc_cache["ts"] < 10 and _proc_cache["alive"] is not None:
        return _proc_cache["alive"]
    alive = None
    try:
        p = subprocess.Popen(["tasklist", "/FI", "IMAGENAME eq XtItClient.exe"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = p.communicate()[0]
        alive = ("XtItClient.exe" in out.decode("gbk", "ignore"))
    except Exception:
        alive = None
    _proc_cache.update({"ts": time.time(), "alive": alive})
    return alive


def _task_installed():

    if time.time() - _task_cache['ts'] < 60 and _task_cache['installed'] is not None:
        return _task_cache['installed']
    ok = None
    try:
        p = subprocess.Popen(['schtasks', '/Query', '/TN', TASK_NAME],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.communicate()
        ok = (p.returncode == 0)
    except Exception:
        ok = None
    _task_cache.update({'ts': time.time(), 'installed': ok})
    return ok


def _phase():
    hm = time.strftime('%H%M%S')
    if hm < '092800':
        return 'before', '开盘前 · 等待导出'
    if hm < '093130':
        return 'buy', '买入窗口 09:30:00-09:31:30'
    if hm < '145000':
        return 'hold', '持仓中'
    if hm < '145700':
        return 'sell', '卖出窗口 14:50:00-14:56:30'
    return 'done', '今日结束'


def _age(ts):
    return None if not ts else round(time.time() - ts, 1)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype='text/plain; charset=utf-8'):
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split('?')[0].rstrip('/') or '/'
        qs = {}
        if '?' in self.path:
            import urllib.parse
            qs = urllib.parse.parse_qs(self.path.split('?', 1)[1])

        if path == '/today.csv':
            with _lock:
                _state['last_get'] = _now_str()
                _state['gets'] += 1
            self._send(200, ','.join(_state['codes']))
            return

        if path == '/set':
            codes = _norm(','.join(qs.get('codes', [])))
            with _lock:
                _state['codes'] = codes
                _state['updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
            _event('push', '推送 %d 只: %s' % (len(codes), ','.join(codes[:8])))
            self._send(200, 'OK %d\n%s' % (len(codes), ','.join(codes)))
            return

        if path == '/hb':
            role = (qs.get('role', [''])[0] or 'unknown').strip()[:12]
            note = (qs.get('note', [''])[0] or '')[:80]
            try:
                n = int(qs.get('n', ['0'])[0])
            except Exception:
                n = 0
            with _lock:
                h = _state['heart'].get(role) or {'count': 0}
                first = role not in _state['heart']
                h['last'] = time.time()
                h['count'] = n or (h.get('count', 0) + 1)
                h['note'] = note
                _state['heart'][role] = h
            if first:
                _event('heart', '%s 策略开始握手' % role)
            self._send(200, 'OK')
            return

        if path == '/status':
            self._send(200, json.dumps(self._status(), ensure_ascii=False),
                       'application/json; charset=utf-8')
            return

        if path == '/ping':
            self._send(200, 'pong')
            return

        if path in ('/', '/board'):
            try:
                html = io.open(BOARD, encoding='utf-8').read()
            except Exception as e:
                html = '<h1>board.html missing</h1><pre>%s</pre>' % e
            self._send(200, html, 'text/html; charset=utf-8')
            return

        self._send(404, 'not found')

    def _status(self):
        log = _parse_log()
        phase, phase_text = _phase()
        hearts = {}
        with _lock:
            for role, h in _state['heart'].items():
                hearts[role] = {'age': _age(h.get('last')), 'count': h.get('count', 0),
                                'note': h.get('note', '')}
            codes = list(_state['codes'])
            updated = _state['updated']
            last_get = _state['last_get']
            gets = _state['gets']
            events = list(_state['events'])[-20:]

        auto_last = log['auto'][-1] if log['auto'] else None
        sell_last = log['sell'][-1] if log['sell'] else None
        return {
            'now': time.strftime('%Y-%m-%d %H:%M:%S'),
            'uptime': int(time.time() - T0),
            'phase': phase,
            'phase_text': phase_text,
            'pool': {'codes': codes, 'count': len(codes),
                     'updated': updated, 'last_get': last_get, 'gets': gets},
            'heart': hearts,
            'qmt': {'log': log.get('file'), 'exists': log.get('exists'),
                    'auto_count': len(log['auto']), 'sell_count': len(log['sell']),
                    'auto_last': auto_last, 'sell_last': sell_last,
                    'buy_orders': log.get('buy_orders', 0),
                    'sell_orders': log.get('sell_orders', 0)},
            'data': {'csv': _csv_info(), 'audit': _audit_info()},
            'task': {'name': TASK_NAME, 'installed': _task_installed()},
            'qmt_proc': _qmt_alive(),
            'events': events,
        }


def _norm(text):
    out = []
    for raw in (text or '').replace('\r', ',').replace('\n', ',').split(','):
        c = raw.strip().upper()
        if not c:
            continue
        for pre in ('SH.', 'SZ.'):
            if c.startswith(pre) and c[len(pre):].isdigit():
                c = '%s.%s' % (c[len(pre):], pre[:2])
                break
        if '.' in c and (c.endswith('.SH') or c.endswith('.SZ')):
            out.append(c)
            continue
        digits = ''.join(ch for ch in c if ch.isdigit())[:6]
        if len(digits) == 6:
            mk = 'SH' if digits[0] in ('5', '6', '9') else 'SZ'
            out.append('%s.%s' % (digits, mk))
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    try:
        srv = Server((HOST, PORT), Handler)
    except OSError as e:
        print('[list_server] cannot bind %s:%s -> %s' % (HOST, PORT, e))
        return
    print('[list_server] board  http://%s:%s/' % (HOST, PORT))
    print('[list_server] status http://%s:%s/status' % (HOST, PORT))
    _event('boot', '服务启动')
    srv.serve_forever()


if __name__ == '__main__':
    main()
