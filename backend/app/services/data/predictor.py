"""阅读量预测服务 (LLM 冷启动)"""
import json
import logging


from app.db.connection import SessionLocal
from app.models.publishing import PlatformStats

logger = logging.getLogger(__name__)


class ReadPredictor:
    """基于历史数据 + LLM 进行阅读量预测（冷启动阶段用 LLM 推理）"""

    def __init__(self):
        self._llm_client = None

    def _get_llm_client(self):
        """懒加载 LLM 客户端"""
        if self._llm_client is None:
            from app.llm.resolver import StageModelResolver
            db = SessionLocal()
            try:
                resolver = StageModelResolver(db)
                self._llm_client = resolver.get_llm_for_stage("prediction")
            except Exception:
                self._llm_client = None
            finally:
                db.close()
        return self._llm_client

    def predict(
        self,
        novel_id: str,
        platform: str,
        days_ahead: int = 7,
        novel_info: dict | None = None,
    ) -> dict:
        """预测未来 N 天的阅读量趋势

        Args:
            novel_id: 小说ID
            platform: 平台
            days_ahead: 预测天数
            novel_info: 小说元信息 (title, genre, word_count, chapter_count 等)

        Returns:
            预测结果 dict
        """
        history = self._load_history(novel_id, platform)

        if len(history) >= 7:
            # 有足够历史数据，用统计方法 + LLM 辅助
            return self._predict_with_history(history, days_ahead, novel_info)
        else:
            # 冷启动：完全依赖 LLM 推理
            return self._predict_cold_start(novel_id, platform, days_ahead, novel_info, history)

    def _load_history(self, novel_id: str, platform: str, limit: int = 30) -> list[dict]:
        """加载历史数据"""
        db = SessionLocal()
        try:
            records = db.query(PlatformStats).filter(
                PlatformStats.novel_id == novel_id,
                PlatformStats.platform == platform,
            ).order_by(PlatformStats.stat_date.asc()).limit(limit).all()
            return [
                {
                    "date": r.stat_date.isoformat(),
                    "reads": r.reads,
                    "favorites": r.favorites,
                    "recommends": r.recommends,
                    "comments": r.comments,
                }
                for r in records
            ]
        finally:
            db.close()

    def _predict_with_history(
        self, history: list[dict], days_ahead: int, novel_info: dict | None
    ) -> dict:
        """基于历史数据的统计预测 + LLM 修正"""
        # 简单线性趋势
        reads_series = [h["reads"] for h in history]
        n = len(reads_series)

        if n < 2:
            _avg = reads_series[0] if reads_series else 0  # noqa: F841
            trend = 0
        else:
            avg = sum(reads_series) / n  # noqa: F841
            # 最近7天 vs 之前的增长率
            recent = reads_series[-7:] if n >= 7 else reads_series
            older = reads_series[:-7] if n > 7 else reads_series[:1]
            recent_avg = sum(recent) / len(recent) if recent else 0
            older_avg = sum(older) / len(older) if older else 0
            trend = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0

        # 基础预测：最近均值 + 趋势延伸
        recent_avg = sum(reads_series[-7:]) / min(7, n)
        predictions = []
        for i in range(1, days_ahead + 1):
            predicted = int(recent_avg * (1 + trend * i / 7))
            predictions.append({
                "day": i,
                "predicted_reads": max(0, predicted),
                "confidence": max(0.3, 0.9 - i * 0.05),
            })

        result = {
            "method": "statistical",
            "data_points": n,
            "recent_avg": int(recent_avg),
            "trend_pct": round(trend * 100, 1),
            "predictions": predictions,
        }

        # 尝试用 LLM 补充洞察
        llm = self._get_llm_client()
        if llm:
            try:
                insight = self._llm_insight(history, novel_info, predictions)
                result["llm_insight"] = insight
            except Exception as e:
                logger.warning(f"LLM 洞察生成失败: {e}")

        return result

    def _predict_cold_start(
        self,
        novel_id: str,
        platform: str,
        days_ahead: int,
        novel_info: dict | None,
        sparse_history: list[dict],
    ) -> dict:
        """冷启动预测：完全依赖 LLM"""
        llm = self._get_llm_client()

        # 优先从 DB 加载预测提示词
        _db_system = None
        try:
            from app.services.prompt_loader import PromptLoader
            _pdb = SessionLocal()
            _db_system = PromptLoader(_pdb).get_prompt("prediction")
            _pdb.close()
        except Exception:
            pass

        # 构建 prompt
        info_str = ""
        if novel_info:
            info_str = f"""
小说信息:
- 标题: {novel_info.get('title', '未知')}
- 类型: {novel_info.get('genre', '未知')}
- 字数: {novel_info.get('word_count', '未知')}
- 章节数: {novel_info.get('chapter_count', '未知')}
"""

        history_str = ""
        if sparse_history:
            history_str = "已有数据:\n"
            for h in sparse_history:
                history_str += f"  {h['date']}: 阅读={h['reads']}, 收藏={h['favorites']}\n"

        prompt = f"""你是一个网文数据分析师。请根据以下信息预测未来 {days_ahead} 天的阅读量趋势。

平台: {platform}
{info_str}
{history_str}

请以 JSON 格式返回预测结果，格式如下:
{{
  "predictions": [
    {{"day": 1, "predicted_reads": <数字>, "confidence": <0-1>}},
    ...
  ],
  "reasoning": "简短分析",
  "suggestions": ["建议1", "建议2"]
}}

注意:
1. 如果数据不足，给出保守估计
2. confidence 应反映预测的不确定性
3. suggestions 给出提升数据的具体建议
"""

        if llm:
            try:
                import asyncio
                from app.llm.client import GenerationConfig as _GC
                _cfg = _GC(system=_db_system) if _db_system else None
                result = asyncio.get_event_loop().run_until_complete(llm.generate(prompt, _cfg))
                parsed = self._parse_llm_response(result.content)
                parsed["method"] = "llm_cold_start"
                parsed["data_points"] = len(sparse_history)
                return parsed
            except Exception as e:
                logger.warning(f"LLM 冷启动预测失败: {e}")

        # LLM 不可用时的兜底：基于平台基线给出保守估计
        return self._fallback_prediction(platform, days_ahead, sparse_history)

    def _fallback_prediction(
        self, platform: str, days_ahead: int, history: list[dict]
    ) -> dict:
        """兜底预测（无 LLM 可用时）"""
        # 平台基线日均阅读量（新书保守估计）
        baselines = {
            "fanqie": 200,
            "qidian": 100,
        }
        baseline = baselines.get(platform, 50)

        if history:
            last_reads = history[-1].get("reads", 0)
            baseline = max(baseline, last_reads)

        predictions = []
        for i in range(1, days_ahead + 1):
            predictions.append({
                "day": i,
                "predicted_reads": baseline,
                "confidence": 0.2,
            })

        return {
            "method": "fallback_baseline",
            "data_points": len(history),
            "predictions": predictions,
            "reasoning": "数据不足且 LLM 不可用，使用平台基线保守估计",
            "suggestions": [
                "保持日更以获取平台推荐",
                "优化标题和简介提升点击率",
                "积累更多数据后预测会更准确",
            ],
        }

    def _llm_insight(
        self, history: list[dict], novel_info: dict | None, predictions: list[dict]
    ) -> str:
        """用 LLM 生成数据洞察"""
        llm = self._get_llm_client()
        if not llm:
            return ""

        history_summary = f"最近 {len(history)} 天数据，最新阅读量 {history[-1]['reads']}"
        prompt = f"""简要分析这个网文的数据趋势（50字以内）:
{history_summary}
预测趋势: {'上升' if predictions[-1]['predicted_reads'] > predictions[0]['predicted_reads'] else '平稳或下降'}
"""
        try:
            import asyncio
            result = asyncio.get_event_loop().run_until_complete(llm.generate(prompt))
            return result.content.strip()
        except Exception:
            return ""

    def _parse_llm_response(self, response: str) -> dict:
        """解析 LLM 返回的 JSON"""
        # 尝试提取 JSON 块
        response = response.strip()
        if "```json" in response:
            start = response.index("```json") + 7
            end = response.index("```", start)
            response = response[start:end].strip()
        elif "```" in response:
            start = response.index("```") + 3
            end = response.index("```", start)
            response = response[start:end].strip()

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"无法解析 LLM 响应为 JSON: {response[:200]}")
            return {
                "predictions": [],
                "reasoning": response[:200],
                "suggestions": [],
            }
