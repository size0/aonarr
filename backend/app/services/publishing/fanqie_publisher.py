"""番茄小说作家后台浏览器发布器 (Playwright)"""
import asyncio
import logging
import os
import re
from typing import Literal

from app.services.publishing.login_manager import LoginStateManager

logger = logging.getLogger(__name__)

FANQIE_LOGIN_URL = "https://fanqienovel.com/main/writer/?enter_from=author_zone"
FANQIE_BOOK_MANAGE_URL = "https://fanqienovel.com/main/writer/book-manage"


class FanqiePublisher:
    """通过 Playwright 自动化番茄作家后台完成章节发布"""

    def __init__(self, state_manager: LoginStateManager | None = None):
        self.state_manager = state_manager or LoginStateManager("fanqie")

    async def capture_login_state(self, timeout_seconds: int = 300) -> dict:
        """打开浏览器让用户手动登录，保存 storage_state。
        使用 sync API + to_thread 避免 Windows ProactorEventLoop 不兼容问题。
        """
        return await asyncio.to_thread(
            self._capture_login_sync, timeout_seconds
        )

    def _capture_login_sync(self, timeout_seconds: int = 300) -> dict:
        """同步版登录态采集（在独立线程中运行）"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("请先安装 playwright: pip install playwright && playwright install chromium")

        import time

        state_path = self.state_manager.state_file
        os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)

            if os.path.exists(state_path):
                logger.info(f"加载已有登录态: {state_path}")
                context = browser.new_context(storage_state=state_path)
            else:
                context = browser.new_context()

            page = context.new_page()

            try:
                page.goto(FANQIE_LOGIN_URL, timeout=60000)
            except Exception as e:
                logger.warning(f"打开番茄页面超时: {e}")

            logger.info(f"已打开番茄作家后台，等待用户登录（超时 {timeout_seconds}s）")

            login_detected = False
            deadline = time.monotonic() + timeout_seconds
            dashboard_keywords = ["作品管理", "创建新书", "书籍管理", "数据中心", "章节管理"]

            while time.monotonic() < deadline:
                for kw in dashboard_keywords:
                    try:
                        if page.locator(f'text="{kw}"').first.is_visible():
                            logger.info(f"检测到登录成功标志: '{kw}'")
                            login_detected = True
                            break
                    except Exception:
                        pass
                if login_detected:
                    break

                current_url = page.url
                if ("book-manage" in current_url or "chapter" in current_url or
                    ("writer" in current_url and "login" not in current_url
                     and "enter_from" not in current_url)):
                    logger.info(f"检测到URL变化，登录成功: {current_url}")
                    login_detected = True
                    break

                time.sleep(2)

            if not login_detected:
                browser.close()
                raise TimeoutError(f"登录超时（{timeout_seconds}s），请重试")

            time.sleep(2)
            context.storage_state(path=state_path)
            logger.info(f"番茄登录态已保存到 {state_path}")
            browser.close()

            return self.state_manager.get_status()

    async def _clear_popups(self, editor_page):
        """清除番茄的新手引导弹窗"""
        for _ in range(3):
            await editor_page.keyboard.press("Escape")
            await editor_page.wait_for_timeout(200)

        for _ in range(10):
            clicked = False
            try:
                for text in ["下一步", "完成", "我知道了", "跳过"]:
                    btns = await editor_page.get_by_text(text, exact=True).element_handles()
                    for btn in btns:
                        box = await btn.bounding_box()
                        if box and box["y"] > 100:
                            await btn.click()
                            await editor_page.wait_for_timeout(600)
                            clicked = True
            except Exception:
                pass
            if not clicked:
                break

    async def publish_chapter(
        self,
        chapter_title: str,
        chapter_content: str,
        book_name: str,
        mode: Literal["save_draft", "publish"] = "save_draft",
        volume_name: str | None = None,
        ai_disclosure: bool = False,
    ) -> dict:
        """发布单个章节到番茄"""
        state_path = self.state_manager.state_file
        if not os.path.exists(state_path):
            raise RuntimeError("登录态不可用，请先采集登录态")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError("请先安装 playwright: pip install playwright && playwright install chromium")

        result = {"status": "failed", "message": "", "payload": {}}

        m = re.search(r"第(\d+)章", chapter_title)
        chapter_num = m.group(1) if m else ""
        pure_title = re.sub(r"第\d+章\s*", "", chapter_title).strip()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(storage_state=state_path)
            page = await context.new_page()

            try:
                # 1. 跳转到书籍管理页
                await page.goto(FANQIE_BOOK_MANAGE_URL, timeout=60000)
                await page.wait_for_timeout(3000)

                if "login" in page.url:
                    raise RuntimeError("登录态已过期，请重新采集")

                # 2. 找到目标书的「章节管理」按钮
                logger.info(f"寻找作品「{book_name}」...")
                manage_clicked = False

                book_cards = page.locator("div, li, section, article").filter(has_text=book_name)
                card_count = await book_cards.count()

                for i in range(card_count - 1, -1, -1):
                    card = book_cards.nth(i)
                    try:
                        if not await card.is_visible():
                            continue
                        await card.hover(timeout=3000)
                        await page.wait_for_timeout(1000)
                        manage_btn = card.get_by_text("章节管理").first
                        if await manage_btn.is_visible():
                            await manage_btn.click()
                            manage_clicked = True
                            break
                    except Exception:
                        continue

                if not manage_clicked:
                    try:
                        await page.get_by_text("章节管理").first.click()
                        manage_clicked = True
                    except Exception:
                        pass

                if not manage_clicked:
                    result["message"] = f"未找到作品「{book_name}」的章节管理入口"
                    await browser.close()
                    return result

                await page.wait_for_timeout(4000)
                original_pages = len(context.pages)

                # 3. 定位编辑器页面
                editor_page = context.pages[-1] if len(context.pages) > 1 and context.pages[-1] != page else page

                # 4. 检查是否有未完成的草稿
                if chapter_num:
                    draft_row = editor_page.locator("tr, li, .chapter-item").filter(
                        has_text=re.compile(rf"第\s*{chapter_num}\s*章")
                    ).first
                    try:
                        if await draft_row.is_visible():
                            logger.info(f"发现已有草稿: 第{chapter_num}章")
                            edit_icon = draft_row.locator("td").last.locator("svg, i, a, span, button, img").first
                            if await edit_icon.is_visible():
                                await edit_icon.click(force=True)
                            else:
                                await draft_row.click(force=True)
                        else:
                            new_btn = editor_page.get_by_role("button", name="新建章节").first
                            if not await new_btn.is_visible():
                                new_btn = editor_page.get_by_text("新建章节").first
                            await new_btn.click(force=True)
                    except Exception:
                        new_btn = editor_page.get_by_role("button", name="新建章节").first
                        if not await new_btn.is_visible():
                            new_btn = editor_page.get_by_text("新建章节").first
                        await new_btn.click(force=True)
                else:
                    new_btn = editor_page.get_by_role("button", name="新建章节").first
                    if not await new_btn.is_visible():
                        new_btn = editor_page.get_by_text("新建章节").first
                    await new_btn.click(force=True)

                await page.wait_for_timeout(4000)

                if len(context.pages) > original_pages:
                    editor_page = context.pages[-1]

                # 5. 清除弹窗
                await self._clear_popups(editor_page)

                # 6. 填写章节序号和标题
                logger.info(f"填写章节: 第{chapter_num}章 {pure_title}")
                num_input = editor_page.locator('input[type="text"]').first
                if await num_input.is_visible():
                    await num_input.fill(chapter_num, force=True)

                title_input = editor_page.get_by_placeholder("请输入标题", exact=False).first
                if not await title_input.is_visible():
                    title_input = editor_page.get_by_placeholder("请输入章节名", exact=False).first
                if not await title_input.is_visible():
                    title_input = editor_page.locator('input[type="text"]').last
                if await title_input.is_visible():
                    await title_input.fill(pure_title, force=True)

                # 7. 注入正文
                logger.info("注入正文内容...")
                editor = editor_page.locator(".ql-editor").first
                if not await editor.is_visible():
                    editor = editor_page.locator(".ProseMirror").first
                if not await editor.is_visible():
                    editor = editor_page.locator('[contenteditable="true"]').first

                if await editor.is_visible():
                    await editor.click(force=True)
                    await editor_page.keyboard.press("Control+A")
                    await editor_page.keyboard.press("Backspace")
                    handle = await editor.element_handle()
                    await editor_page.evaluate(
                        "([el, text]) => { el.innerText = text; el.dispatchEvent(new Event('input', {bubbles: true})); }",
                        [handle, chapter_content],
                    )
                    await editor.click()
                    await editor_page.keyboard.press("End")
                    await editor_page.keyboard.press("Space")
                    await page.wait_for_timeout(500)
                    await editor_page.keyboard.press("Backspace")
                else:
                    result["message"] = "未找到正文编辑器"
                    await browser.close()
                    return result

                # 8A. 存草稿模式
                if mode == "save_draft":
                    save_btn = editor_page.get_by_text("存草稿", exact=False).first
                    if await save_btn.is_visible():
                        await save_btn.click()
                        await page.wait_for_timeout(2000)
                        result["status"] = "success"
                        result["message"] = "草稿保存成功"
                    else:
                        result["message"] = "未找到存草稿按钮"
                    await browser.close()
                    return result

                # 8B. 正式发布
                logger.info("点击下一步...")
                next_btn = editor_page.get_by_text("下一步", exact=True).last
                if not await next_btn.is_visible():
                    next_btn = editor_page.get_by_role("button", name="下一步").first
                if await next_btn.is_visible():
                    await next_btn.click(force=True)
                    await editor_page.wait_for_timeout(3000)

                    # 处理错别字弹窗
                    try:
                        submit_typo = editor_page.get_by_role("button", name="提交").first
                        await submit_typo.wait_for(state="visible", timeout=5000)
                        await submit_typo.click(force=True)
                        await editor_page.wait_for_timeout(1500)
                    except Exception:
                        pass

                    # 处理内容风险检测弹窗
                    try:
                        risk_txt = editor_page.get_by_text("内容风险检测", exact=False).last
                        await risk_txt.wait_for(state="visible", timeout=5000)
                        cancel_btn = editor_page.get_by_role("button", name="取消").last
                        await cancel_btn.wait_for(state="visible", timeout=3000)
                        await cancel_btn.click(force=True)
                        await editor_page.wait_for_timeout(1000)
                    except Exception:
                        pass

                    # 确认发布
                    try:
                        publish_btn = editor_page.get_by_role("button", name="确认发布").first
                        try:
                            await publish_btn.wait_for(state="visible", timeout=8000)
                        except Exception:
                            for btn_name in ["发布", "确认", "确定发布", "立即发布"]:
                                fallback = editor_page.get_by_role("button", name=btn_name).first
                                if await fallback.is_visible():
                                    publish_btn = fallback
                                    break
                            else:
                                for txt in ["确认发布", "发布章节", "发布"]:
                                    fallback = editor_page.get_by_text(txt, exact=False).last
                                    try:
                                        if await fallback.is_visible():
                                            publish_btn = fallback
                                            break
                                    except Exception:
                                        continue
                                else:
                                    raise TimeoutError("找不到发布确认按钮")

                        # AI 声明选择
                        if not ai_disclosure:
                            try:
                                ai_no = editor_page.get_by_text("否", exact=True).first
                                await ai_no.wait_for(state="visible", timeout=3000)
                                await ai_no.click(force=True)
                                await editor_page.wait_for_timeout(500)
                            except Exception:
                                pass

                        await publish_btn.click(force=True)
                        await page.wait_for_timeout(3000)

                        result["status"] = "success"
                        result["message"] = "发布成功"
                        logger.info(f"番茄发布成功: 第{chapter_num}章 {pure_title}")

                    except Exception as e:
                        logger.error(f"确认发布面板操作失败: {e}")
                        result["message"] = f"确认发布面板操作失败: {e}"
                else:
                    result["message"] = "未找到'下一步'按钮"

            except RuntimeError:
                raise
            except Exception as e:
                logger.error(f"番茄发布失败: {e}")
                result["message"] = str(e)
            finally:
                for pg in context.pages[1:]:
                    try:
                        await pg.close()
                    except Exception:
                        pass
                await browser.close()

        return result
