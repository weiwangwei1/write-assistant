# -*- coding: utf-8 -*-
"""合并番茄+起点榜单数据 → 量化分析（关键词/标签分布）"""
import json
import re
import os
import collections

BASE = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw'
CAP = BASE + r'\captures'

CAT_NAME = {
    '1_2_1141': '西方奇幻', '1_2_1140': '东方仙侠', '1_2_261': '都市日常',
    '1_2_1014': '都市高武', '1_2_751': '悬疑灵异', '1_2_27': '战神赘婿',
    '1_2_257': '玄幻脑洞',
}

def load_json(p):
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding='utf-8'))

def main():
    books = []
    ra = load_json(CAP + r'\rank_all.json')
    if ra:
        for b in ra:
            books.append({
                'site': '番茄', 'cat': CAT_NAME.get(b['tag'], b['tag']),
                'rank': b.get('rank'), 'title': b.get('title', ''),
                'desc': b.get('desc', ''), 'read': b.get('read', ''),
                'status': b.get('status', ''),
            })
    for tag in ['1_2_1140', '1_2_1141']:
        d = load_json(CAP + r'\parsed_' + tag + '.json')
        if d:
            for b in d['books']:
                books.append({
                    'site': '番茄', 'cat': CAT_NAME.get(tag, tag),
                    'rank': b.get('rank'), 'title': b.get('title', ''),
                    'desc': b.get('desc', ''), 'read': b.get('read', ''),
                    'status': b.get('status', ''),
                })
    # 起点：解析 markdown 落盘文件
    qp = r'C:\Users\王伟\AppData\Local\Temp\trae\toolcall-output\cf60afac-d29c-4f40-aedf-eec188ccffa5.txt'
    if os.path.exists(qp):
        txt = open(qp, encoding='utf-8').read()
        blocks = re.findall(
            r'\[(\d+)\]\(https://m\.qidian\.com/book/(\d+)/\)\s*\n\s*\n'
            r'## \[([^\]]+)\]\([^)]+\)\s*\n\s*\n'
            r'\[([^\]]+)\]\([^)]+\)\s*\n'
            r'\[([^*]+)\*·\*([^*]+)\*·\*([^\]]+)\]', txt)
        for rank, bid, title, desc, author, cat, words in blocks:
            books.append({
                'site': '起点', 'cat': cat.strip(), 'rank': int(rank),
                'title': title.strip(), 'desc': desc.strip(),
                'read': words.strip(), 'status': '',
            })
    json.dump(books, open(CAP + r'\all_books.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('total books:', len(books))
    print('by site:', collections.Counter(b['site'] for b in books))
    print('by cat:', dict(collections.Counter(b['cat'] for b in books)))

    # 关键词统计（标题 + 简介）
    KEYS = ['重生', '穿越', '穿书', '系统', '开局', '签到', '无敌', '最强', '领主', '修仙', '仙',
            '诡异', '恐怖', '克苏鲁', '灵异', '民俗', '长生', '不死', '词条', '天赋', '面板',
            '反派', '女帝', '病娇', '团宠', '救赎', '赘婿', '战神', '兵王', '神婿', '神医', '医生',
            '官场', '局长', '纪委', '调查', '破案', '刑侦', '推理', '打脸', '逆袭', '复仇',
            '剑与魔法', '魔法', '蒸汽', '学院', '学院', '地下城', '游戏', '玩家', 'NPC', '副本',
            '种田', '经营', '基建', '争霸', '家族', '宗门', '直播', '美食', '荒野求生', '求生',
            '末世', '末日', '丧尸', '天灾', '怪谈', '收容', '御兽', '宠兽', '巨龙', '龙',
            '多女主', '单女主', '无女主', '修罗场', '轻松', '搞笑', '沙雕', '慢热', '爽文',
            '重生流', '重生+', '扶弟魔', '豪门', '总裁', '校花', '青梅', '暗恋', '大学', '校园',
            '重生七零', '年代', '知青', '下乡', '七零', '八零', '历史', '三国', '大明', '秦']
    cnt = collections.Counter()
    title_cnt = collections.Counter()
    for b in books:
        text = b['title'] + ' ' + b['desc']
        for k in KEYS:
            if k in text:
                cnt[k] += 1
                if k in b['title']:
                    title_cnt[k] += 1
    print('\n=== 高频钩子词（标题+简介，共 %d 本）===' % len(books))
    for k, v in cnt.most_common(40):
        print('  %-10s %3d  (标题中 %d)' % (k, v, title_cnt.get(k, 0)))

    # 简介标签统计（【】内）
    tagc = collections.Counter()
    for b in books:
        for m in re.findall(r'【([^】]{1,20})】', b['desc']):
            for part in re.split(r'[+、,，]', m):
                p = part.strip()
                if p and len(p) <= 8:
                    tagc[p] += 1
    print('\n=== 简介标签 TOP40 ===')
    for k, v in tagc.most_common(40):
        print('  %-12s %d' % (k, v))

if __name__ == '__main__':
    main()