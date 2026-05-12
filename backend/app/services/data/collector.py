"""作品数据采集服务 (阅读量/收藏/追更)"""
import asyncio
import logging
from datetime import date, datetime, timezone


from app.db.connection import SessionLocal
from app.models.publishing import PlatformStats
from app.services.publishing.login_manager import LoginStateManager

logger = logging.getLogger(__name__)


class DataCollector:
    """从各平台采集作品运营数据"""

    PLATFORM_CONFIGS = {
        "fanqie": {
            "dashboard_url": "https://fanqienovel.com/main/writer/data-center",
            "book_manage_url": "https://fanqienovel.com/main/writer/book-manage",
        },
        "qidian": {
            "dashboard_url": "https://write.qq.com/portal/dashboard/overview",
            "works_url": "https://write.qq.com/portal/dashboard/books",
        },
    }

    def __init__(self):
        self.state_managers = {
            "fanqie": LoginStateManager("fanqie"),
            "qidian": LoginStateManager("qidian"),
        }

    async def collect(self, novel_id: str, platform: str) -> dict:
        """采集指定平台的作品数据"""
        if platform not in self.PLATFORM_CONFIGS:
            return {"status": "failed", "message": f"不支持的平台: {platform}"}

        sm = self.state_managers[platform]
        if not sm.is_ready():
            return {"status": "failed", "message": f"{platform} 登录态不可用"}

        try:
            if platform == "fanqie":
                stats = await self._collect_fanqie(novel_id)
            elif platform == "qidian":
                stats = await self._collect_qidian(novel_id)
            else:
                return {"status": "failed", "message": f"采集器未实现: {platform}"}

            if stats:
                self._save_stats(novel_id, platform, stats)
                return {"status": "success", "data": stats}
            return {"status": "failed", "message": "未采集到数据"}

        except Exception as e:
            logger.error(f"[{platform}] 数据采集失败: {e}")
            return {"status": "failed", "message": str(e)}

    async def _collect_fanqie(self, novel_id: str) -> dict | None:
        """从番茄 API 直接采集（无需 Playwright）"""
        from app.services.data.fanqie_stats import FanqieStatsCollector

        collector = FanqieStatsCollector()
        result = await collector.fetch_book_list()
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "番茄 API 调用失败"))

        # 在返回的 books 中找到匹配的
        books = result.get("books", [])
        matched = None
        for b in books:
            if b["book_id"] == novel_id or b["title"] == novel_id:
                matched = b
                break

        if not matched and books:
            # 如果无法精确匹配，取第一本
            matched = books[0]

        if matched:
            return {
                "reads": matched.get("read_count", 0),
                "favorites": matched.get("favorite_count", 0),
                "recommends": 0,
                "comments": matched.get("comment_count", 0),
            }
        return None

    async def _collect_qidian(self, novel_id: str) -> dict | None:
        """从起点数据中心采集"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError("请先安装 playwright")

        sm = self.state_managers["qidian"]
        state = sm.load_state()
        if not state or not state.get("cookies"):
            raise RuntimeError("起点登录态不可用")

        stats = {}
        config = self.PLATFORM_CONFIGS["qidian"]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
            )
            await context.add_cookies(state["cookies"])
            page = await context.new_page()

            try:
                await page.goto(config["dashboard_url"], timeout=30000)
                await asyncio.sleep(5)

                if "passport" in page.url or "login" in page.url:
                    raise RuntimeError("起点登录态已过期")

                stats = await page.evaluate("""() => {
                    const result = {};
                    const allText = document.body.innerText;
                    const patterns = {
                        reads: /(?:总点击|总阅读|点击)[：:]\s*([\d,.万亿]+)/,
                        favorites: /(?:总收藏|收藏)[：:]\s*([\d,.万亿]+)/,
                        recommends: /(?:总推荐|推荐票)[：:]\s*([\d,.万亿]+)/,
                        comments: /(?:评论|书评)[：:]\s*([\d,.万亿]+)/,
                    };
                    for (const [key, regex] of Object.entries(patterns)) {
                        const m = allText.match(regex);
                        if (m) result[key] = m[1];
                    }
                    return result;
                }""")

            except Exception as e:
                logger.error(f"起点数据采集失败: {e}")
                raise
            finally:
                await browser.close()

        return self._normalize_stats(stats)

    def _normalize_stats(self, raw: dict) -> dict:
        """将采集到的原始数据标准化为整数"""
        def parse_num(val) -> int:
            if val is None:
                return 0
            s = str(val).replace(",", "").strip()
            if "万" in s:
                return int(float(s.replace("万", "")) * 10000)
            if "亿" in s:
                return int(float(s.replace("亿", "")) * 100000000)
            try:
                return int(float(s))
            except (ValueError, TypeError):
                return 0

        return {
            "reads": parse_num(raw.get("reads")),
            "favorites": parse_num(raw.get("favorites")),
            "recommends": parse_num(raw.get("recommends")),
            "comments": parse_num(raw.get("comments")),
        }

    def _save_stats(self, novel_id: str, platform: str, stats: dict):
        """保存采集数据到数据库"""
        db = SessionLocal()
        try:
            today = date.today()
            existing = db.query(PlatformStats).filter(
                PlatformStats.novel_id == novel_id,
                PlatformStats.platform == platform,
                PlatformStats.stat_date == today,
            ).first()

            if existing:
                existing.reads = stats.get("reads", 0)
                existing.favorites = stats.get("favorites", 0)
                existing.recommends = stats.get("recommends", 0)
                existing.comments = stats.get("comments", 0)
                existing.collected_at = datetime.now(tz=timezone.utc)
            else:
                record = PlatformStats(
                    novel_id=novel_id,
                    platform=platform,
                    stat_date=today,
                    reads=stats.get("reads", 0),
                    favorites=stats.get("favorites", 0),
                    recommends=stats.get("recommends", 0),
                    comments=stats.get("comments", 0),
                )
                db.add(record)

            db.commit()
            logger.info(f"[{platform}] 数据已保存: novel={novel_id}, reads={stats.get('reads')}")
        except Exception as e:
            db.rollback()
            logger.error(f"保存采集数据失败: {e}")
        finally:
            db.close()

    async def collect_all(self, novel_id: str) -> dict:
        """采集所有已配置平台的数据"""
        results = {}
        for platform in self.PLATFORM_CONFIGS:
            sm = self.state_managers[platform]
            if sm.is_ready():
                results[platform] = await self.collect(novel_id, platform)
            else:
                results[platform] = {"status": "skipped", "message": "登录态未就绪"}
        return results

    async def collect_all_scheduled(self) -> dict:
        """定时采集：优先用 API 方式获取番茄数据"""
        from app.services.data.fanqie_stats import FanqieStatsCollector

        results = {}

        # 番茄：API 方式
        fanqie_sm = self.state_managers["fanqie"]
        if fanqie_sm.is_ready():
            try:
                fc = FanqieStatsCollector()
                result = await fc.collect_and_save()
                results["fanqie"] = result
            except Exception as e:
                logger.error("番茄 API 采集失败: %s", e)
                results["fanqie"] = {"ok": False, "error": str(e)}
        else:
            results["fanqie"] = {"ok": False, "error": "登录态未就绪"}

        # 起点：暂用 Playwright（未来可同样 API 化）
        qidian_sm = self.state_managers["qidian"]
        if qidian_sm.is_ready():
            results["qidian"] = {"ok": True, "message": "起点采集需绑定小说ID"}
        else:
            results["qidian"] = {"ok": False, "error": "登录态未就绪"}

        return results

    def get_history(self, novel_id: str, platform: str | None = None, limit: int = 30) -> list[dict]:
        """获取历史采集数据"""
        db = SessionLocal()
        try:
            query = db.query(PlatformStats).filter(PlatformStats.novel_id == novel_id)
            if platform:
                query = query.filter(PlatformStats.platform == platform)
            records = query.order_by(PlatformStats.stat_date.desc()).limit(limit).all()
            return [
                {
                    "id": r.id,
                    "platform": r.platform,
                    "stat_date": r.stat_date.isoformat(),
                    "reads": r.reads,
                    "favorites": r.favorites,
                    "recommends": r.recommends,
                    "comments": r.comments,
                    "rank": r.rank,
                    "revenue": r.revenue,
                    "collected_at": r.collected_at.isoformat() if r.collected_at else None,
                }
                for r in records
            ]
        finally:
            db.close()
