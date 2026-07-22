#!/usr/bin/env python3
"""Bing HTML 搜索—返回 JSON 结果。低依赖，只用标准库。"""
import sys, json, urllib.request, urllib.parse
from html.parser import HTMLParser

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
        return parser.results[:count]
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
