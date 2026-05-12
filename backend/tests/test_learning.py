"""学习Agent系统测试"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ============================================================
# hot_crawler 测试
# ============================================================


class TestHotCrawler:
    """热门采集测试"""

    def test_parse_fanqie_book(self):
        from app.services.learning.hot_crawler import _parse_fanqie_book

        book = {
            "book_data": {
                "book_name": "测试小说",
                "author": "测试作者",
                "category": "玄幻",
                "tag": "爽文,逆袭",
                "word_number": 500000,
                "score": "8.5",
                "abstract": "一段简介",
                "book_id": "12345",
            }
        }
        result = _parse_fanqie_book(book, "hot_sale", 1)
        assert result is not None
        assert result["title"] == "测试小说"
        assert result["author"] == "测试作者"
        assert result["platform"] == "fanqie"
        assert result["rank_info"] == {"hot_sale": 1}
        assert result["word_count"] == 500000
        assert "玄幻" in result["genre"]

    def test_parse_fanqie_book_empty(self):
        from app.services.learning.hot_crawler import _parse_fanqie_book

        result = _parse_fanqie_book({}, "hot_sale", 1)
        assert result is None

    def test_parse_fanqie_book_flat(self):
        """没有 book_data 包装的扁平格式"""
        from app.services.learning.hot_crawler import _parse_fanqie_book

        book = {
            "book_name": "扁平小说",
            "author": "作者",
            "category": "都市",
            "tag": "",
            "word_number": 200000,
            "score": "7.0",
            "abstract": "简介",
            "book_id": "999",
        }
        result = _parse_fanqie_book(book, "rising", 3)
        assert result is not None
        assert result["title"] == "扁平小说"
        assert result["rank_info"] == {"rising": 3}

    def test_parse_qidian_html(self):
        from app.services.learning.hot_crawler import _parse_qidian_html

        html = """
        <div class="book-list">
          <h2><a href="//book.qidian.com/info/1234">测试起点小说</a></h2>
          <p class="author"><a>起点作者</a></p>
          <a class="go-sub-type">奇幻</a>
        </div>
        """
        result = _parse_qidian_html(html, "yuepiao")
        assert len(result) == 1
        assert result[0]["title"] == "测试起点小说"
        assert result[0]["platform"] == "qidian"
        assert result[0]["author"] == "起点作者"
        assert result[0]["rank_info"] == {"yuepiao": 1}

    def test_parse_qidian_html_empty(self):
        from app.services.learning.hot_crawler import _parse_qidian_html

        result = _parse_qidian_html("<html></html>", "yuepiao")
        assert result == []

    @pytest.mark.asyncio
    async def test_crawl_fanqie_hot_handles_error(self):
        """网络错误不应崩溃"""
        from app.services.learning.hot_crawler import crawl_fanqie_hot

        with patch("app.services.learning.hot_crawler.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("network error")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await crawl_fanqie_hot(["hot_sale"])
            assert result == []

    def test_save_novels_dedup(self):
        """测试去重逻辑"""
        from app.services.learning.hot_crawler import _save_novels

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = None  # 无重复

        novels = [
            {"platform": "fanqie", "title": "小说A", "author": "A", "tags": [], "rank_info": {"hot_sale": 1}},
            {"platform": "fanqie", "title": "小说B", "author": "B", "tags": [], "rank_info": {"hot_sale": 2}},
        ]
        saved = _save_novels(mock_db, novels)
        assert saved == 2
        assert mock_db.add.call_count == 2
        mock_db.commit.assert_called_once()


# ============================================================
# knowledge_extractor 测试
# ============================================================


class TestKnowledgeExtractor:
    """知识提取测试"""

    def test_parse_response_valid_json(self):
        from app.services.learning.knowledge_extractor import _parse_response

        content = '```json\n{"title": "开篇套路分析", "insights": ["悬念开局"], "quality_score": 0.8, "tags": ["玄幻"]}\n```'
        result = _parse_response(content)
        assert result["title"] == "开篇套路分析"
        assert result["quality_score"] == 0.8
        assert "悬念开局" in result["insights"]

    def test_parse_response_plain_json(self):
        from app.services.learning.knowledge_extractor import _parse_response

        content = '{"title": "测试", "insights": [], "quality_score": 0.5}'
        result = _parse_response(content)
        assert result["title"] == "测试"

    def test_parse_response_invalid(self):
        from app.services.learning.knowledge_extractor import _parse_response

        result = _parse_response("这不是JSON")
        assert "title" in result
        assert result["quality_score"] == 0.3

    def test_build_context(self):
        from app.services.learning.knowledge_extractor import _build_context

        mock_job = MagicMock()
        mock_job.novel_title = "测试小说"
        mock_job.chapter_count = 10

        summary = {
            "aggregation": {
                "reverse_outline": [
                    {"chapter": 1, "summary": "主角出场"},
                    {"chapter": 2, "summary": "遇到对手"},
                ],
                "character_profiles": [
                    {"name": "张三", "appearance_count": 50, "primary_role": "主角"}
                ],
            },
            "style_fingerprint": {
                "sentence": {"avg_length": 15},
                "dialogue": {"ratio": 0.3},
                "rhythm": {"pattern": "varied"},
            },
        }

        context = _build_context(mock_job, summary, [])
        assert "逆向大纲" in context
        assert "张三" in context

    def test_extraction_categories_defined(self):
        from app.services.learning.knowledge_extractor import EXTRACTION_CATEGORIES

        assert len(EXTRACTION_CATEGORIES) >= 5
        cats = [c["category"] for c in EXTRACTION_CATEGORIES]
        assert "opening_pattern" in cats
        assert "thrill_distribution" in cats
        assert "character_template" in cats


# ============================================================
# prompt_optimizer 测试
# ============================================================


class TestPromptOptimizer:
    """提示词优化测试"""

    def test_parse_response_valid(self):
        from app.services.learning.prompt_optimizer import _parse_response

        content = '{"analysis": "分析内容", "suggestions": [{"aspect": "x"}], "confidence": 0.7}'
        result = _parse_response(content)
        assert result["analysis"] == "分析内容"
        assert result["confidence"] == 0.7

    def test_parse_response_invalid(self):
        from app.services.learning.prompt_optimizer import _parse_response

        result = _parse_response("不是JSON")
        assert "analysis" in result
        assert result["confidence"] == 0.3

    def test_optimization_targets_defined(self):
        from app.services.learning.prompt_optimizer import OPTIMIZATION_TARGETS

        assert "chapter_writing" in OPTIMIZATION_TARGETS
        assert "outline_planning" in OPTIMIZATION_TARGETS

    def test_load_relevant_knowledge_empty(self):
        from app.services.learning.prompt_optimizer import _load_relevant_knowledge

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        result = _load_relevant_knowledge(mock_db)
        assert "知识库为空" in result

    def test_load_relevant_knowledge_with_entries(self):
        from app.services.learning.prompt_optimizer import _load_relevant_knowledge

        mock_entry = MagicMock()
        mock_entry.category = "opening_pattern"
        mock_entry.title = "悬念开局"
        mock_entry.content = json.dumps({"insights": ["制造悬念"], "pattern": "先打后问"})

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_entry]

        result = _load_relevant_knowledge(mock_db)
        assert "悬念开局" in result
        assert "制造悬念" in result
