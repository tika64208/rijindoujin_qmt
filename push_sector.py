# -*- coding: utf-8 -*-
# ---------------------------------------------------------------
# push_sector.py  --  run by YOUR third-party Python tool
#
# Writes today's picks into QMT's custom sector so a QMT strategy
# can read them with C.get_stock_list_in_sector('竞价选股').
#
# Also drops plain text copies under <QMT>\lists\ for the
# load_stk_list channel.
#
# Usage:
#     from push_sector import push
#     push(['300209.SZ', '002843.SZ', '300949.SZ'])
#
# QMT must be restarted (or the sector list refreshed) before a
# running strategy can see a newly created sector -- see notes in
# the chat. Updating an existing sector's members is picked up
# more often, so keep the name stable.
# ---------------------------------------------------------------
import os
import shutil
import xml.etree.ElementTree as ET

QMT_DIR = r'D:\国金QMT交易端模拟'
SECTOR_NAME = '竞价选股'
SECTOR_DIR = os.path.join(QMT_DIR, 'datadir', 'Sector', '我的')
CONFIG = os.path.join(SECTOR_DIR, 'sectorConfig.xml')
LIST_DIR = os.path.join(QMT_DIR, 'lists')


def _norm(codes):
    """accept 300209 / 300209.SZ / sz300209 -> 300209.SZ"""
    out = []
    for c in codes:
        c = str(c).strip().upper().replace('SH.', 'SH').replace('SZ.', 'SZ')
        if not c:
            continue
        if '.' in c and (c.endswith('.SH') or c.endswith('.SZ')):
            out.append(c)
            continue
        digits = ''.join(ch for ch in c if ch.isdigit())[:6]
        if len(digits) != 6:
            continue
        mk = 'SH' if digits[0] in ('5', '6', '9') else 'SZ'
        out.append('%s.%s' % (digits, mk))
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def _ensure_sector_in_config(name):
    """make sure sectorConfig.xml lists the sector under 我的"""
    if not os.path.exists(CONFIG):
        return False
    try:
        tree = ET.parse(CONFIG)
        root = tree.getroot()
        parent = None
        for item in root.findall('Item'):
            if item.get('type') == '0':
                parent = item
                break
        if parent is None:
            parent = root
        for item in parent.findall('Item'):
            if item.get('name') == name:
                return True
        el = ET.SubElement(parent, 'Item')
        el.set('type', '2')
        el.set('name', name)
        el.set('visible', '1')
        el.set('authority', '2')
        backup = CONFIG + '.bak'
        if not os.path.exists(backup):
            shutil.copy2(CONFIG, backup)
        tree.write(CONFIG, encoding='utf-8', xml_declaration=True)
        return True
    except Exception as e:
        print('[push_sector] config edit failed: %s' % e)
        return False


def push(codes, name=SECTOR_NAME, write_lists=True):
    codes = _norm(codes)
    if not codes:
        print('[push_sector] no valid codes')
        return []

    if not os.path.isdir(SECTOR_DIR):
        os.makedirs(SECTOR_DIR)

    # 1) sector member file: plain CSV, same format QMT uses
    path = os.path.join(SECTOR_DIR, name)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='ascii', newline='') as f:
        f.write(','.join(codes))
    os.replace(tmp, path)

    # 2) make sure the sector is declared in sectorConfig.xml
    _ensure_sector_in_config(name)

    # 3) plain-text copies for the load_stk_list channel
    if write_lists:
        if not os.path.isdir(LIST_DIR):
            os.makedirs(LIST_DIR)
        with open(os.path.join(LIST_DIR, 'today.txt'), 'w', encoding='ascii') as f:
            f.write('\n'.join(codes))
        with open(os.path.join(LIST_DIR, 'today.csv'), 'w', encoding='ascii') as f:
            f.write(','.join(codes))

    print('[push_sector] %d codes -> %s' % (len(codes), path))
    print('[push_sector] %s' % ','.join(codes))
    return codes


if __name__ == '__main__':
    # quick self test
    push(['300209', '002843.SZ', 'sz000007'])
