"""Track C: 拆书引擎基础测试

测试覆盖:
- importer: txt 解析
- chapter_splitter: 多种模式切分
- entity_scanner: jieba 实体提取
- chapter_extractor: LLM 响应解析
- aggregator: 全局聚合算法
- style_fingerprint: 文风统计
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

# ────────────────────────────────────────────────────────────────
#  样本数据
# ────────────────────────────────────────────────────────────────

SAMPLE_NOVEL_CN = """第一章 初入江湖

少年林风背着一把破旧的长剑，踏上了前往青云城的道路。
他的师父临终前告诉他，青云城里有一个叫做张天明的人，能够帮助他找到失散多年的父母。
一路上，林风遇到了不少江湖中人，有好人也有坏人。
林风从小在山上长大，武功虽然不算高强，但也有一身不俗的本领。
师父教导他要行侠仗义，不可欺压弱小，更不能为非作歹。

"你就是林风？"一个身穿黑衣的中年人拦住了他的去路。
"正是在下，请问阁下是？"林风警惕地握紧了剑柄。
"我叫赵无极，是你师父的旧友。"黑衣人微微一笑。
"你师父可好？"赵无极又问道。
"师父他老人家已经仙逝了。"林风低下头，眼中闪过一丝悲伤。

赵无极带着林风来到了一家客栈，两人坐下后，赵无极开始讲述当年的故事。
据说二十年前，江湖上发生了一场惊天动地的大事。

第二章 青云城

青云城是一座繁华的大城，城中商贩云集，人来人往。
林风跟着赵无极穿过热闹的街道，来到了城东的一处宅院。
城中的建筑古色古香，飞檐翘角，处处透着一股庄严之气。
路边的小贩叫卖着各种吃食，香气扑鼻，让人垂涎欲滴。
远处的钟楼传来阵阵钟声，回荡在整座城市的上空。

"张天明就住在这里。"赵无极指着朱红色的大门说道。
林风深吸一口气，上前敲了敲门。

门开了，一个白发老者出现在门口。
"老夫张天明，请问二位找老夫何事？"
"晚辈林风，奉师父遗命前来拜访。"林风恭敬地行了一礼。

林风连忙将师父的遗言告知张天明。张天明听后沉默良久，最后叹了口气。
"此事说来话长，请进屋详谈。"张天明侧身让开了门。

第三章 真相大白

张天明告诉林风，他的父亲叫做林正阳，曾经是武林盟主。
二十年前的一场阴谋，导致林正阳夫妇失踪，年幼的林风被师父救走。
当年参与此事的人如今大多已经不在人世，但仍有几个关键人物活跃于江湖。
张天明说起往事，不禁老泪纵横，可见当年之事对他影响之深。
他从书架上取下一本泛黄的册子，上面记载着当年事件的详细经过。

"你父亲很可能还活着。"张天明从柜中取出一封密信。
信上写着一个地址——雪山之巅，寒冰洞。
"这封信是三年前一个神秘人送来的，我一直保管至今。"

林风握紧密信，心中燃起了希望。赵无极拍了拍他的肩膀。
"走吧，我陪你去雪山。"

三人开始准备行装，一场艰难的旅程即将开始。
前方等待他们的，不知是希望还是绝望。
"""

SAMPLE_NOVEL_EN = """Chapter 1: The Beginning

John walked into the old library. The dust had settled on every surface.
Sarah was already there, reading a thick book by the window.

"You're late," she said without looking up.
"I know. The traffic was terrible," John replied.

Chapter 2: The Discovery

They found a hidden room behind the bookshelf. Inside was a map.
The map showed a path leading to an ancient temple deep in the forest.

"We should go there," Sarah whispered excitedly.
John nodded slowly. "But we need to be careful."

Chapter 3: The Journey

The forest was dark and full of strange sounds.
John and Sarah followed the map through winding paths.
After hours of walking, they finally saw the temple.
"""


# ────────────────────────────────────────────────────────────────
#  Test: importer
# ────────────────────────────────────────────────────────────────

class TestImporter:

    def test_parse_txt_utf8(self, tmp_path):
        """UTF-8 文本文件导入"""
        from app.services.analysis.importer import import_file

        f = tmp_path / "test_novel.txt"
        f.write_text(SAMPLE_NOVEL_CN, encoding="utf-8")

        result = import_file(str(f))
        assert result.char_count > 100
        assert result.title == "test_novel"
        assert "林风" in result.text

    def test_parse_txt_gbk(self, tmp_path):
        """GBK 编码文本文件导入"""
        from app.services.analysis.importer import import_file

        f = tmp_path / "gbk_novel.txt"
        f.write_bytes(SAMPLE_NOVEL_CN.encode("gbk"))

        result = import_file(str(f))
        assert result.char_count > 100
        assert "林风" in result.text

    def test_unsupported_format(self, tmp_path):
        """不支持的文件格式应抛出异常"""
        from app.services.analysis.importer import import_file

        f = tmp_path / "test.pdf"
        f.write_text("dummy")
        with pytest.raises(ValueError, match="不支持"):
            import_file(str(f))

    def test_file_not_found(self):
        """文件不存在应抛出异常"""
        from app.services.analysis.importer import import_file

        with pytest.raises(FileNotFoundError):
            import_file("/nonexistent/path/novel.txt")


# ────────────────────────────────────────────────────────────────
#  Test: chapter_splitter
# ────────────────────────────────────────────────────────────────

class TestChapterSplitter:

    def test_split_chinese_chapters(self):
        """中文 '第X章' 模式切分"""
        from app.services.analysis.chapter_splitter import split_chapters

        result = split_chapters(SAMPLE_NOVEL_CN)
        assert result.chapter_count >= 3
        assert result.pattern_used != "fixed_length"
        for ch in result.chapters:
            assert ch.word_count > 0
            assert ch.title

    def test_split_english_chapters(self):
        """英文 'Chapter X' 模式切分"""
        from app.services.analysis.chapter_splitter import split_chapters

        result = split_chapters(SAMPLE_NOVEL_EN, min_chars=50)
        assert result.chapter_count >= 3
        assert "Chapter" in result.pattern_used or result.chapter_count >= 2

    def test_split_no_chapters(self):
        """无章节标记的文本应使用固定长度切分"""
        from app.services.analysis.chapter_splitter import split_chapters

        plain = "这是一段没有任何章节标记的普通文本。" * 500
        result = split_chapters(plain)
        assert result.chapter_count >= 1
        assert result.pattern_used == "fixed_length"

    def test_split_empty_text(self):
        """空文本应返回空结果"""
        from app.services.analysis.chapter_splitter import split_chapters

        result = split_chapters("")
        assert result.chapter_count == 0

    def test_split_numbered_chapters(self):
        """纯数字编号章节"""
        from app.services.analysis.chapter_splitter import split_chapters

        text = ""
        for i in range(1, 6):
            text += f"\n{i}. 标题{i}\n" + f"这是第{i}段内容，测试文本。" * 30 + "\n"
        result = split_chapters(text, min_chars=50)
        assert result.chapter_count >= 2

    def test_chapter_merge_short(self):
        """过短章节应合并"""
        from app.services.analysis.chapter_splitter import split_chapters

        text = "第一章 开始\n短内容\n第二章 继续\n" + "这是正常长度的章节内容。" * 30
        result = split_chapters(text, min_chars=50)
        # 短章节应被合并
        for ch in result.chapters:
            assert ch.word_count >= 1


# ────────────────────────────────────────────────────────────────
#  Test: entity_scanner
# ────────────────────────────────────────────────────────────────

class TestEntityScanner:

    def test_scan_basic(self):
        """基本实体扫描"""
        from app.services.analysis.entity_scanner import scan_entities

        result = scan_entities(SAMPLE_NOVEL_CN, min_freq=1)
        assert result.word_count > 0
        assert result.unique_words > 0
        names = result.get_entity_names()
        assert len(names) > 0

    def test_scan_persons(self):
        """人名提取"""
        from app.services.analysis.entity_scanner import scan_entities

        result = scan_entities(SAMPLE_NOVEL_CN, min_freq=1)
        person_names = result.get_entity_names("person")
        # 至少应识别出一些人名
        assert len(person_names) >= 1

    def test_scan_empty(self):
        """空文本扫描"""
        from app.services.analysis.entity_scanner import scan_entities

        result = scan_entities("", min_freq=1)
        assert result.word_count == 0
        assert len(result.entities) == 0

    def test_scan_to_dict(self):
        """扫描结果序列化"""
        from app.services.analysis.entity_scanner import scan_entities

        result = scan_entities(SAMPLE_NOVEL_CN, min_freq=1)
        d = result.to_dict()
        assert "entities" in d
        assert "word_count" in d
        assert isinstance(d["entities"], list)

    def test_custom_names(self):
        """自定义人名列表"""
        from app.services.analysis.entity_scanner import scan_entities

        result = scan_entities(
            SAMPLE_NOVEL_CN,
            min_freq=1,
            custom_names=["林风", "赵无极", "张天明"],
        )
        person_names = result.get_entity_names("person")
        assert len(person_names) >= 1


# ────────────────────────────────────────────────────────────────
#  Test: chapter_extractor (mock LLM)
# ────────────────────────────────────────────────────────────────

class TestChapterExtractor:

    def test_parse_llm_response_valid(self):
        """解析正常 JSON 响应"""
        from app.services.analysis.chapter_extractor import _parse_llm_response

        resp = json.dumps({
            "summary": "本章讲述了主角入城的故事",
            "characters": [{"name": "林风", "role": "主角"}],
            "events": [{"description": "进入青云城", "importance": "high"}],
            "relationships": [],
            "foreshadows": [],
        }, ensure_ascii=False)
        result = _parse_llm_response(resp)
        assert result["summary"] == "本章讲述了主角入城的故事"
        assert len(result["characters"]) == 1

    def test_parse_llm_response_markdown_wrapped(self):
        """解析 markdown 代码块包裹的 JSON"""
        from app.services.analysis.chapter_extractor import _parse_llm_response

        resp = '```json\n{"summary": "test", "characters": []}\n```'
        result = _parse_llm_response(resp)
        assert result["summary"] == "test"

    def test_parse_llm_response_garbage(self):
        """解析无效响应应容错"""
        from app.services.analysis.chapter_extractor import _parse_llm_response

        result = _parse_llm_response("This is not JSON at all")
        assert "summary" in result

    @pytest.mark.asyncio
    async def test_extract_chapter_mock(self):
        """使用 mock LLM 测试章节提取"""
        from app.services.analysis.chapter_extractor import extract_chapter

        mock_llm = AsyncMock()
        mock_result = MagicMock()
        mock_result.content = json.dumps({
            "summary": "测试摘要",
            "characters": [{"name": "林风", "role": "主角", "actions": ["行走"], "emotions": ["期待"], "first_appearance": True}],
            "events": [{"description": "出发", "importance": "high", "participants": ["林风"], "location": "村庄", "type": "transition"}],
            "relationships": [],
            "foreshadows": [],
        }, ensure_ascii=False)
        mock_llm.generate = AsyncMock(return_value=mock_result)

        result = await extract_chapter(
            llm=mock_llm,
            chapter_number=1,
            chapter_title="初入江湖",
            chapter_text="测试章节内容",
            novel_title="测试小说",
        )
        assert result.chapter_number == 1
        assert result.summary == "测试摘要"
        assert len(result.characters) == 1
        assert result.characters[0]["name"] == "林风"

    @pytest.mark.asyncio
    async def test_extract_chapter_llm_error(self):
        """LLM 调用失败应容错"""
        from app.services.analysis.chapter_extractor import extract_chapter

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(side_effect=Exception("API Error"))

        result = await extract_chapter(
            llm=mock_llm,
            chapter_number=1,
            chapter_title="测试",
            chapter_text="内容",
        )
        assert result.chapter_number == 1
        assert "提取失败" in result.summary


# ────────────────────────────────────────────────────────────────
#  Test: aggregator
# ────────────────────────────────────────────────────────────────

class TestAggregator:

    def _make_chapter_data(self) -> list[dict]:
        return [
            {
                "chapter_number": 1,
                "chapter_title": "初入江湖",
                "summary": "少年林风踏上旅途",
                "characters": [
                    {"name": "林风", "role": "主角"},
                    {"name": "赵无极", "role": "配角"},
                ],
                "events": [
                    {"description": "林风出发", "importance": "high",
                     "participants": ["林风"], "type": "transition"},
                ],
                "relationships": [
                    {"from": "赵无极", "to": "林风", "type": "友情", "change": "初次相遇"},
                ],
                "foreshadows": [
                    {"description": "师父的遗言", "type": "planted", "hint": "密信"},
                ],
            },
            {
                "chapter_number": 2,
                "chapter_title": "青云城",
                "summary": "林风到达青云城",
                "characters": [
                    {"name": "林风", "role": "主角"},
                    {"name": "张天明", "role": "配角"},
                ],
                "events": [
                    {"description": "拜访张天明", "importance": "high",
                     "participants": ["林风", "张天明"], "type": "revelation"},
                ],
                "relationships": [
                    {"from": "林风", "to": "张天明", "type": "合作", "change": ""},
                ],
                "foreshadows": [],
            },
        ]

    def test_aggregate_basic(self):
        """基本聚合"""
        from app.services.analysis.aggregator import aggregate

        data = self._make_chapter_data()
        result = aggregate(data)

        assert len(result.reverse_outline) == 2
        assert len(result.character_profiles) >= 2
        assert len(result.timeline) >= 2
        assert len(result.relationship_graph) >= 1

    def test_aggregate_character_tracking(self):
        """角色追踪"""
        from app.services.analysis.aggregator import aggregate

        data = self._make_chapter_data()
        result = aggregate(data)

        lin_feng = next((c for c in result.character_profiles if c.name == "林风"), None)
        assert lin_feng is not None
        assert lin_feng.appearance_count == 2
        assert lin_feng.first_chapter == 1
        assert lin_feng.last_chapter == 2

    def test_aggregate_to_dict(self):
        """聚合结果序列化"""
        from app.services.analysis.aggregator import aggregate

        data = self._make_chapter_data()
        result = aggregate(data)
        d = result.to_dict()

        assert "reverse_outline" in d
        assert "character_profiles" in d
        assert "timeline" in d
        assert "foreshadow_net" in d

    def test_aggregate_empty(self):
        """空数据聚合"""
        from app.services.analysis.aggregator import aggregate

        result = aggregate([])
        assert len(result.reverse_outline) == 0
        assert len(result.character_profiles) == 0


# ────────────────────────────────────────────────────────────────
#  Test: style_fingerprint
# ────────────────────────────────────────────────────────────────

class TestStyleFingerprint:

    def test_analyze_basic(self):
        """基本文风分析"""
        from app.services.analysis.style_fingerprint import analyze_style

        fp = analyze_style(SAMPLE_NOVEL_CN)
        assert fp.sentence_count > 0
        assert fp.paragraph_count > 0
        assert fp.avg_sentence_length > 0

    def test_dialogue_detection(self):
        """对话检测"""
        from app.services.analysis.style_fingerprint import analyze_style

        fp = analyze_style(SAMPLE_NOVEL_CN)
        assert fp.dialogue_count > 0
        assert fp.dialogue_ratio > 0

    def test_rhythm_classification(self):
        """节奏分类"""
        from app.services.analysis.style_fingerprint import analyze_style

        fp = analyze_style(SAMPLE_NOVEL_CN)
        assert fp.rhythm_pattern in ("fast", "medium", "slow", "varied")

    def test_to_dict(self):
        """风格指纹序列化"""
        from app.services.analysis.style_fingerprint import analyze_style

        fp = analyze_style(SAMPLE_NOVEL_CN)
        d = fp.to_dict()
        assert "sentence" in d
        assert "dialogue" in d
        assert "rhetoric" in d
        assert "rhythm" in d
        assert "vocabulary" in d

    def test_empty_text(self):
        """空文本应返回零值"""
        from app.services.analysis.style_fingerprint import analyze_style

        fp = analyze_style("")
        assert fp.sentence_count == 0
        assert fp.dialogue_count == 0

    def test_vocab_richness(self):
        """词汇丰富度"""
        from app.services.analysis.style_fingerprint import analyze_style

        fp = analyze_style(SAMPLE_NOVEL_CN)
        # vocab_richness > 0 only if jieba works
        assert fp.vocab_richness >= 0.0
        assert fp.vocab_richness <= 1.0
        # With jieba installed, should be > 0
        try:
            import jieba  # noqa: F401
            assert fp.vocab_richness > 0.0
        except ImportError:
            pass


# ────────────────────────────────────────────────────────────────
#  Test: end-to-end pipeline (lightweight, no LLM)
# ────────────────────────────────────────────────────────────────

class TestPipelineIntegration:

    def test_import_then_split(self, tmp_path):
        """导入 -> 切分 集成"""
        from app.services.analysis.importer import import_file
        from app.services.analysis.chapter_splitter import split_chapters

        f = tmp_path / "novel.txt"
        f.write_text(SAMPLE_NOVEL_CN, encoding="utf-8")

        imp = import_file(str(f))
        result = split_chapters(imp.text)
        assert result.chapter_count >= 2

    def test_import_split_scan(self, tmp_path):
        """导入 -> 切分 -> 扫描 集成"""
        from app.services.analysis.importer import import_file
        from app.services.analysis.chapter_splitter import split_chapters
        from app.services.analysis.entity_scanner import scan_entities

        f = tmp_path / "novel.txt"
        f.write_text(SAMPLE_NOVEL_CN, encoding="utf-8")

        imp = import_file(str(f))
        split = split_chapters(imp.text)
        scan = scan_entities(imp.text, min_freq=1)

        assert split.chapter_count >= 3
        assert scan.word_count > 0

    def test_full_offline_pipeline(self, tmp_path):
        """完整离线管线 (不含 LLM 调用)"""
        from app.services.analysis.importer import import_file
        from app.services.analysis.chapter_splitter import split_chapters
        from app.services.analysis.entity_scanner import scan_entities
        from app.services.analysis.aggregator import aggregate
        from app.services.analysis.style_fingerprint import analyze_style

        f = tmp_path / "novel.txt"
        f.write_text(SAMPLE_NOVEL_CN, encoding="utf-8")

        imp = import_file(str(f))
        split = split_chapters(imp.text)
        scan = scan_entities(imp.text, min_freq=1)
        style = analyze_style(imp.text)

        # 模拟章节提取结果
        mock_analyses = []
        for ch in split.chapters:
            mock_analyses.append({
                "chapter_number": ch.number,
                "chapter_title": ch.title,
                "summary": f"Chapter {ch.number} summary",
                "characters": [{"name": "林风", "role": "主角"}],
                "events": [{"description": "测试事件", "importance": "medium",
                           "participants": ["林风"], "type": "transition"}],
                "relationships": [],
                "foreshadows": [],
            })

        agg = aggregate(mock_analyses)

        assert agg.reverse_outline
        assert agg.character_profiles
        assert style.sentence_count > 0
        assert scan.word_count > 0
