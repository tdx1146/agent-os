#!/usr/bin/env python3
"""Bing HTML 搜索—返回 JSON 结果。低依赖，只用标准库。
   内置结果质量过滤：去工具站/聚合站/SEO 污染，优先学术/官方/原文。"""
import sys, json, urllib.request, urllib.parse, re
from html.parser import HTMLParser

# --- 域名黑名单（SEO 工具站 / 聚合站 / 低质量爬站） ---
BLACKLIST_DOMAINS = {
    'ai-bot.cn', 'ai-kit.cn', 'aitoolbot.com', 'aigc.cn', 'aitoolnav.com',
    'tool.ai', 'aitools.com', 'aipure.com', 'aitoolsdaily.com', 'topai.tools',
    'aitoptools.com', 'aitoolsexplorer.com', 'aitoolhunt.com', 'aitoolslist.com',
    'aitrends.com', 'aitoolzone.com', 'aitoolbook.com', 'aitoolbox.com',
    'toolsnav.com', 'aitoolway.com', 'aitoolclub.com', 'aitoolkit.com',
    'aitoolslib.com', 'aitoolscollection.com', 'aitoolsgallery.com',
    'aitoolcenter.com', 'aitoolsrank.com', 'aitoolsfinder.com',
    'aitoolsguide.com', 'aitoolsarchive.com', 'aitoolsempire.com',
    'kzhishi.com', 'juejin.im', 'juejin.cn', 'csdn.net',
    'cnblogs.com', 'sohu.com', 'toutiao.com', '163.com',
    'zhuanlan.zhihu.com',  # 知乎专栏保留，仅去掉首页
}

# --- 域名白名单（原文/学术/官方 — 提高优先级） ---
WHITELIST_DOMAINS = {
    'arxiv.org', 'semanticscholar.org', 'openalex.org', 'acm.org',
    'ieee.org', 'springer.com', 'nature.com', 'science.org', 'cell.com',
    'wiley.com', 'plos.org', 'frontiersin.org', 'mdpi.com',
    'google.com', 'microsoft.com', 'github.com', 'gitlab.com',
    'paperswithcode.com', 'huggingface.co', 'openai.com',
    'baike.baidu.com', 'wikipedia.org', 'wikimedia.org',
    'stackoverflow.com', 'stackexchange.com', 'medium.com', 'dev.to',
    'python.org', 'npmjs.com', 'pypi.org', 'docker.com',
    'readthedocs.io', 'docsify.com', 'learn.microsoft.com',
}

# --- 标题/摘要黑名单关键词（SEO 作弊词） ---
BLACKLIST_TITLE_KEYWORDS = [
    'AI工具集', 'AI网站', '免费AI', '工具导航', 'AI工具箱',
    'AI写作', 'AI绘画', 'AI创作', 'AI助手', 'AI对话',
    '一站式', '导航大全', '在线玩', '免费在线', '无需下载',
    '小游戏', '游戏大全', 'html5游戏', '浏览器游戏',
    '歌曲推荐', '音乐下载', '无损音乐', '免费音乐',
    '电影免费', '视频免费', '独播剧',
]

# --- 优质内容关键词（标题/摘要包含这些词加分） ---
QUALITY_KEYWORDS = [
    '研究', '论文', '学术', 'journal', 'conference', 'proceedings',
    'survey', 'review', 'tutorial', 'documentation', 'guide',
    '官方', 'official', 'documentation', 'specification', 'standard',
    '开源', 'open source', 'github', 'implementation',
    '实验', 'experiment', 'result', 'analysis', 'method',
]

def _domain(url):
    """提取域名（过滤 www.）"""
    m = re.search(r'https?://(?:www\.)?([^/]+)', url)
    return m.group(1) if m else ''

def _score_result(r):
    """给搜索结果打分，返回 (score, reason)"""
    url = r.get('url', '')
    title = r.get('title', '')
    snippet = r.get('snippet', '')
    domain = _domain(url)
    
    score = 0
    reasons = []
    
    # 域名黑名单 → 直接杀
    if domain in BLACKLIST_DOMAINS:
        return (-100, 'blacklisted domain')
    # 子域名黑名单
    for bd in BLACKLIST_DOMAINS:
        if domain.endswith('.' + bd) or domain == bd:
            return (-100, f'blacklisted subdomain: {bd}')
    
    # 标题黑名单关键词
    title_lower = title.lower()
    snippet_lower = snippet.lower()
    for kw in BLACKLIST_TITLE_KEYWORDS:
        if kw.lower() in title_lower:
            return (-50, f'title has blacklist kw: {kw}')
    
    # 域名白名单 → 高分
    if domain in WHITELIST_DOMAINS:
        score += 30
        reasons.append(f'whitelist domain: {domain}')
    for wd in WHITELIST_DOMAINS:
        if domain.endswith('.' + wd):
            score += 20
            reasons.append(f'whitelist subdomain: {wd}')
    
    # 优质内容关键词
    combined = title_lower + ' ' + snippet_lower
    for kw in QUALITY_KEYWORDS:
        if kw.lower() in combined:
            score += 5
            reasons.append(f'quality kw: {kw}')
    
    # .edu / .gov / .ac.* 域名加分
    if domain.endswith('.edu') or domain.endswith('.gov') or re.search(r'\.ac\.', domain):
        score += 15
        reasons.append('edu/gov/ac domain')
    
    # 标题长度适中加分（太短=无意义，太长= SEO 堆砌）
    if 15 <= len(title) <= 100:
        score += 3
    elif len(title) > 120:
        score -= 5
    
    # snippet 有实质性内容加分
    if len(snippet) > 30:
        score += 2
    
    return (score, '; '.join(reasons[:3]))


class BingExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self.in_algo = False
        self.in_h2 = False
        self.in_a = False
        self.in_p = False
        self.current = {}

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if tag == 'li' and 'b_algo' in ad.get('class', '').split():
            self.in_algo = True
            self.current = {}
            return
        if not self.in_algo:
            return
        if tag == 'h2':
            self.in_h2 = True
        if tag == 'a' and self.in_h2:
            self.current['url'] = ad.get('href', '')
            self.in_a = True
        if tag == 'p':
            self.in_p = True

    def handle_data(self, data):
        if self.in_a:
            self.current['title'] = (self.current.get('title', '') + data).strip()
        if self.in_p:
            self.current['snippet'] = (self.current.get('snippet', '') + data).strip()

    def handle_endtag(self, tag):
        if tag == 'h2':
            self.in_h2 = False
        if tag == 'a' and self.in_a:
            self.in_a = False
        if tag == 'p':
            self.in_p = False
        if tag == 'li' and self.in_algo:
            self.in_algo = False
            if 'url' in self.current and 'title' in self.current:
                self.results.append(self.current)


def search(query, count=10):
    url = 'https://cn.bing.com/search?q=' + urllib.parse.quote(query) + '&count=' + str(count)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    try:
        response = urllib.request.urlopen(req, timeout=15)
        html = response.read().decode('utf-8', errors='replace')
        parser = BingExtractor()
        parser.feed(html)
        
        # 过滤 + 评分 + 排序
        scored = []
        for r in parser.results:
            score, reason = _score_result(r)
            scored.append((score, reason, r))
        
        # 去黑名单，按质量排序
        good = [r for s, reason, r in scored if s >= 0]
        bad = [r for s, reason, r in scored if s < 0]
        
        good.sort(key=lambda r: _score_result(r)[0], reverse=True)
        
        # 日志：被过滤的
        if bad and '--debug' in sys.argv:
            for r in bad:
                score, reason = _score_result(r)
                print(f'[filtered - {reason}] {r.get("title","")[:50]}', file=sys.stderr)
        
        return good[:count]
    except Exception as e:
        return {'error': str(e)}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'need query arg'}, ensure_ascii=False))
        sys.exit(1)
    query = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    results = search(query, count)
    print(json.dumps(results, ensure_ascii=False))
