from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fanqie_learning_scraper.py"
SPEC = importlib.util.spec_from_file_location("fanqie_learning_scraper", SCRIPT_PATH)
scraper = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = scraper
SPEC.loader.exec_module(scraper)


def test_extract_book_id_from_id_and_page_url():
    assert scraper.extract_book_id("7276384138653862966") == "7276384138653862966"
    assert scraper.extract_book_id("https://fanqienovel.com/page/7276384138653862966") == "7276384138653862966"
    assert scraper.extract_book_id("https://fanqienovel.com/reader/7276663560427471412") is None


def test_parse_book_page_meta_gets_title_author_cover_and_synopsis():
    html = """
    <html><head>
      <title>Sample Book完整版在线免费阅读_Sample Book小说_番茄小说官网</title>
      <meta name="description" content="Sample description">
      <meta name="keywords" content="Sample Book,Sample tag">
      <script type="application/ld+json">
        {"headline":"Sample Book完整版在线免费阅读_Sample Book小说_番茄小说官网",
         "author":[{"name":"Author A"}],
         "image":["https://example.test/cover.jpg"]}
      </script>
    </head>
    <body>
      <script>{"page":{"bookName":"Sample Book","authorName":"Author A","thumbUrl":"https:\\u002F\\u002Fexample.test\\u002Fcover2.jpg"}}</script>
    </body></html>
    """
    meta = scraper.parse_book_page_meta(html, "123456789")
    assert meta["title"] == "Sample Book"
    assert meta["author"] == "Author A"
    assert meta["cover_url"] == "https://example.test/cover2.jpg"
    assert meta["synopsis"] == "Sample description"
    assert meta["tags"] == ["Sample Book", "Sample tag"]


def test_parse_reader_page_extracts_content_title_and_font_url():
    html = r'''
    <style>@font-face{src:url(https://example.test/font.woff2)format("woff2");}</style>
    <script>window.__INITIAL_STATE__={"reader":{"chapterData":{
      "title":"第1章 测试",
      "content":"\u003Cp\u003E\uE521\u2026\u2026\uE41E谁？\u003C/p\u003E"
    }}}</script>
    '''
    parsed = scraper.parse_reader_page(html)
    assert parsed["title"] == "第1章 测试"
    assert parsed["content"] == "\ue521……\ue41e谁？"
    assert parsed["font_urls"] == ["https://example.test/font.woff2"]


def test_pua_ratio_detects_private_use_text():
    assert scraper.pua_ratio("plain text") == 0
    assert scraper.pua_ratio("\ue001\ue002ab") == pytest.approx(0.5)


def test_gb2312_candidates_contain_common_chinese():
    chars = set(scraper.gb2312_chinese_chars())
    assert "我" in chars
    assert "是" in chars
    assert "的" in chars
    assert "神" in chars


def test_decode_js_string_and_strip_html_text():
    raw = r"\u003Cp\u003EHello\u003C/p\u003E\u003Cp\u003EWorld\u003C/p\u003E"
    assert scraper.strip_html_text(scraper.decode_js_string(raw)) == "Hello\nWorld"
