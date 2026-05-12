"""预测 API 路由 — 写前评估 / 阅读量预测"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.llm.resolver import StageModelResolver
from app.services.data.predictor import ReadPredictor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prediction", tags=["prediction"])


# ── Schemas ─────────────────────────────────────────────────────

class EvaluateRequest(BaseModel):
    genre: str = ""
    synopsis: str = ""
    first_chapters: str = ""
    title: str = ""
    tags: list[str] = []


class ReadPredictRequest(BaseModel):
    novel_id: str
    platform: str = "fanqie"
    days_ahead: int = 7


# ── 写前预评估 (LLM 冷启动) ─────────────────────────────────────

@router.post("/evaluate")
async def evaluate_novel(req: EvaluateRequest, db: Session = Depends(get_db)):
    """
    写前预评估：输入题材+简介+前三章，返回市场表现预测。
    无需历史数据，完全由 LLM 推理。
    """
    if not req.genre and not req.synopsis and not req.first_chapters:
        raise HTTPException(400, "请至少提供题材、简介或前三章内容之一")

    # 尝试获取 LLM
    try:
        resolver = StageModelResolver(db)
        llm = resolver.get_llm_for_stage("prediction")
    except Exception as e:
        logger.warning(f"预测 LLM 未配置: {e}")
        llm = None

    # 构建 prompt
    parts = []
    if req.title:
        parts.append(f"标题: {req.title}")
    if req.genre:
        parts.append(f"题材/赛道: {req.genre}")
    if req.tags:
        parts.append(f"标签: {', '.join(req.tags)}")
    if req.synopsis:
        parts.append(f"简介: {req.synopsis}")
    if req.first_chapters:
        parts.append(f"前三章内容 (截取): {req.first_chapters[:3000]}")

    novel_desc = "\n".join(parts)

    prompt = f"""你是一名资深网文数据分析师。请根据以下小说信息，评估其市场表现潜力。

{novel_desc}

请以严格 JSON 格式返回分析结果:
{{
  "estimated_daily_reads": "预估日均阅读量范围 (如: 5000-20000)",
  "follow_rate": "预估追更率百分比 (如: 35%)",
  "signing_probability": "签约概率百分比 (如: 60%)",
  "genre_heat": "题材热度 (如: 高/中/低，附简要说明)",
  "overall_score": 75,
  "risk_warnings": ["风险1", "风险2"],
  "optimization_suggestions": ["建议1", "建议2", "建议3"],
  "competitive_analysis": "简要竞品分析 (50字以内)",
  "best_publish_time": "建议发布时间段"
}}

注意:
1. estimated_daily_reads 给出区间值
2. overall_score 为0-100的整数
3. risk_warnings 和 optimization_suggestions 各给2-4条
4. 尽量给出具体、可执行的建议"""

    if llm:
        try:
            result = await llm.generate(prompt)
            parsed = _parse_json_response(result.content)
            parsed["method"] = "llm"
            parsed["model_used"] = llm.model
            return parsed
        except Exception as e:
            logger.error(f"LLM 预测失败: {e}")
            # 降级到规则引擎
            return _rule_based_evaluation(req)
    else:
        return _rule_based_evaluation(req)


# ── 阅读量趋势预测 ─────────────────────────────────────────────

@router.post("/read-trend")
async def predict_read_trend(req: ReadPredictRequest, db: Session = Depends(get_db)):
    """基于历史数据预测阅读量趋势（有数据用统计，无数据用LLM冷启动）"""
    from app.models.novel import Novel
    novel = db.query(Novel).filter_by(id=req.novel_id).first()
    novel_info = None
    if novel:
        novel_info = {
            "title": novel.title,
            "genre": novel.genre,
            "word_count": novel.current_word_count,
            "chapter_count": novel.chapter_count,
        }

    predictor = ReadPredictor()
    result = predictor.predict(
        novel_id=req.novel_id,
        platform=req.platform,
        days_ahead=req.days_ahead,
        novel_info=novel_info,
    )
    return result


# ── 辅助函数 ────────────────────────────────────────────────────

def _parse_json_response(text: str) -> dict:
    """从 LLM 响应中提取 JSON"""
    text = text.strip()
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"无法解析 LLM JSON: {text[:200]}")
        return {
            "estimated_daily_reads": "无法解析",
            "follow_rate": "-",
            "signing_probability": "-",
            "genre_heat": "-",
            "overall_score": 0,
            "risk_warnings": ["LLM 返回格式异常"],
            "optimization_suggestions": [],
            "raw_response": text[:500],
        }


def _rule_based_evaluation(req: EvaluateRequest) -> dict:
    """规则引擎兜底评估（LLM 不可用时）"""
    # 题材热度粗略评估
    hot_genres = {"玄幻", "都市", "仙侠", "科幻", "言情", "奇幻"}
    warm_genres = {"悬疑", "历史", "军事", "游戏"}
    genre = req.genre or ""

    if genre in hot_genres:
        heat = "高 — 主流赛道，读者基数大"
        score = 70
        daily_reads = "5,000-30,000"
    elif genre in warm_genres:
        heat = "中 — 有稳定受众群"
        score = 55
        daily_reads = "2,000-10,000"
    else:
        heat = "中低 — 小众赛道，需要差异化"
        score = 40
        daily_reads = "500-5,000"

    has_synopsis = bool(req.synopsis and len(req.synopsis) > 20)
    has_chapters = bool(req.first_chapters and len(req.first_chapters) > 500)

    if has_synopsis:
        score += 5
    if has_chapters:
        score += 10

    warnings = []
    suggestions = []

    if not req.synopsis:
        warnings.append("缺少简介，难以评估吸引力")
        suggestions.append("补充150-300字的简介，突出核心卖点和冲突")
    if not req.first_chapters:
        warnings.append("缺少前三章内容，无法评估文笔和节奏")
        suggestions.append("提供前三章内容以获取更准确的预测")
    if not req.tags:
        suggestions.append("添加3-5个精准标签提升曝光率")

    suggestions.append("开篇前三章务必设置强钩子，第一章结尾留悬念")
    suggestions.append("保持日更节奏，积累平台推荐权重")

    return {
        "method": "rule_based",
        "estimated_daily_reads": daily_reads,
        "follow_rate": f"{max(20, score - 30)}%",
        "signing_probability": f"{min(90, score + 10)}%",
        "genre_heat": heat,
        "overall_score": min(100, score),
        "risk_warnings": warnings or ["基于规则引擎的粗略评估，配置 LLM 后可获得更精准分析"],
        "optimization_suggestions": suggestions,
        "competitive_analysis": f"{genre}赛道竞争{'激烈' if genre in hot_genres else '适中'}，需在前三章建立差异化",
        "best_publish_time": "建议晚上 19:00-21:00 发布",
    }
