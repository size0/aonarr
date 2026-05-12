"""起点中文网作家后台浏览器发布器 (Playwright)"""
import asyncio
import logging
from typing import Literal

from app.services.publishing.login_manager import LoginStateManager

logger = logging.getLogger(__name__)

QIDIAN_WRITER_URL = "https://write.qq.com"
QIDIAN_LOGIN_URL = f"{QIDIAN_WRITER_URL}/portal/dashboard/books"
QIDIAN_WORKS_URL = f"{QIDIAN_WRITER_URL}/portal/dashboard/books"


class QidianPublisher:
    """通过 Playwright 自动化起点作家专区完成章节发布"""

    def __init__(self, state_manager: LoginStateManager | None = None):
        self.state_manager = state_manager or LoginStateManager("qidian")

    async def capture_login_state(self, timeout_seconds: int = 300) -> dict:
        """打开浏览器让用户手动登录起点，捕获登录态。
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

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            page = context.new_page()
            page.goto(QIDIAN_LOGIN_URL)

            logger.info(f"已打开起点登录页，等待用户登录（超时 {timeout_seconds}s）")

            login_detected = False
            deadline = time.monotonic() + timeout_seconds
            dashboard_keywords = ["作品管理", "创建作品", "书籍管理", "章节管理", "数据中心", "稿费"]

            while time.monotonic() < deadline:
                current_url = page.url

                if "passport" in current_url or "login" in current_url:
                    time.sleep(2)
                    continue

                # 检测验证码
                captcha_visible = False
                for cap_sel in ['#tcaptcha_iframe', '[class*="tcaptcha"]', '[class*="captcha-"]']:
                    try:
                        if page.locator(cap_sel).first.is_visible():
                            captcha_visible = True
                            break
                    except Exception:
                        pass
                if captcha_visible:
                    logger.info("起点：检测到验证码，等待用户完成...")
                    time.sleep(3)
                    continue

                # 检测作家后台关键元素
                for kw in dashboard_keywords:
                    try:
                        if page.locator(f'text="{kw}"').first.is_visible():
                            logger.info(f"起点：检测到登录成功标志: '{kw}'")
                            login_detected = True
                            break
                    except Exception:
                        pass
                if login_detected:
                    break

                # URL 兜底
                if "write.qq.com" in current_url and "passport" not in current_url:
                    time.sleep(3)
                    if "passport" not in page.url and "login" not in page.url:
                        login_detected = True
                        break

                time.sleep(2)

            if not login_detected:
                browser.close()
                raise TimeoutError(f"登录超时（{timeout_seconds}s），请重试")

            time.sleep(2)

            try:
                page.goto(QIDIAN_WORKS_URL, wait_until="domcontentloaded", timeout=15000)
                time.sleep(2)
            except Exception:
                pass

            cookies = context.cookies()
            local_storage = page.evaluate("() => Object.assign({}, localStorage)")
            browser.close()

            return self.state_manager.save_state(
                cookies=[dict(c) for c in cookies],
                local_storage=local_storage,
            )

    async def _find_visible(self, page, selectors: list[str]):
        """依次尝试选择器，返回第一个可见的 Locator"""
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible():
                    return loc
            except Exception:
                pass
        return None

    async def publish_chapter(
        self,
        chapter_title: str,
        chapter_content: str,
        book_name: str,
        mode: Literal["save_draft", "publish"] = "save_draft",
        volume_name: str | None = None,
        ai_disclosure: bool = False,
    ) -> dict:
        """发布单个章节到起点"""
        state = self.state_manager.load_state()
        if not state or not state.get("cookies"):
            raise RuntimeError("起点登录态不可用，请先采集登录态")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError("请先安装 playwright: pip install playwright && playwright install chromium")

        result = {"status": "failed", "message": "", "payload": {}}

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            await context.add_cookies(state["cookies"])
            page = await context.new_page()

            try:
                # 1. 访问作品列表页
                await page.goto(QIDIAN_WORKS_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                if "passport" in page.url or "login" in page.url:
                    await browser.close()
                    raise RuntimeError("起点登录态已过期，请重新采集")

                logger.info(f"起点：寻找作品「{book_name}」...")

                # 2. 找到「去写作」按钮
                new_btn = None
                all_page_text = await page.inner_text("body")
                if book_name not in all_page_text:
                    result["message"] = f"未找到作品「{book_name}」"
                    await browser.close()
                    return result

                for container_sel in ['tr', 'li', 'div[class*="book"]', 'div[class*="work"]', 'div[class*="item"]']:
                    containers = page.locator(container_sel)
                    count = await containers.count()
                    for i in range(count):
                        container = containers.nth(i)
                        try:
                            text = await container.inner_text()
                            if book_name in text:
                                for btn_text in ["去写作", "新建章节", "添加章节"]:
                                    btn = container.locator(f'a:has-text("{btn_text}"), button:has-text("{btn_text}")').first
                                    try:
                                        if await btn.is_visible():
                                            new_btn = btn
                                            break
                                    except Exception:
                                        pass
                                if new_btn:
                                    break
                        except Exception:
                            continue
                    if new_btn:
                        break

                if not new_btn:
                    new_btn = await self._find_visible(page, [
                        'a:has-text("去写作")',
                        'button:has-text("去写作")',
                        'a:has-text("新建章节")',
                    ])

                if new_btn:
                    async with context.expect_page(timeout=10000) as new_page_info:
                        await new_btn.click(force=True)
                    try:
                        editor_page = await new_page_info.value
                        await editor_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        editor_page = page
                    await asyncio.sleep(5)

                    # 关闭弹窗
                    for dismiss_text in ["知道了", "我知道了", "关闭", "跳过"]:
                        try:
                            dismiss_btn = editor_page.locator(f'button:has-text("{dismiss_text}")').first
                            if await dismiss_btn.is_visible():
                                await dismiss_btn.click(force=True)
                                await asyncio.sleep(1)
                        except Exception:
                            pass
                else:
                    result["message"] = "未找到'去写作'按钮"
                    await browser.close()
                    return result

                # 3. 分卷选择
                if volume_name:
                    vol_sel = await self._find_visible(editor_page, [
                        'select[name*="volume"]', 'select[class*="volume"]',
                    ])
                    if vol_sel:
                        await vol_sel.select_option(label=volume_name)

                # 4. 填入标题
                logger.info(f"起点：填写标题「{chapter_title}」...")
                title_loc = await self._find_visible(editor_page, [
                    'input[name="chapterName"]',
                    'input[placeholder*="章节名"]',
                    'input[placeholder*="标题"]',
                    'input.j_chapterName',
                    '#chapterName',
                    'input[type="text"]',
                ])
                if title_loc:
                    await title_loc.click(force=True)
                    await title_loc.fill("")
                    await title_loc.type(chapter_title, delay=10)

                # 5. 填入正文
                logger.info("起点：注入正文...")
                editor_sels = [
                    '.ql-editor', '.ProseMirror', '[contenteditable="true"]',
                    '#chapterContent', 'textarea[name="content"]', 'textarea',
                ]
                editor_loc = None
                editor_frame = None

                for attempt in range(5):
                    editor_loc = await self._find_visible(editor_page, editor_sels)
                    if editor_loc:
                        editor_frame = editor_page.main_frame
                        break
                    # 在 iframe 中查找
                    for frame in editor_page.frames:
                        if frame == editor_page.main_frame:
                            continue
                        for sel in ['body', '[contenteditable="true"]', '.ql-editor']:
                            try:
                                loc = frame.locator(sel).first
                                if await loc.is_visible():
                                    editor_loc = loc
                                    editor_frame = frame  # noqa: F841
                                    break
                            except Exception:
                                pass
                        if editor_loc:
                            break
                    if editor_loc:
                        break
                    await asyncio.sleep(3)

                if editor_loc:
                    tag = await editor_loc.evaluate("el => el.tagName")
                    if tag.lower() == "textarea":
                        await editor_loc.fill(chapter_content)
                    else:
                        lines = [l.strip() for l in chapter_content.split('\n') if l.strip()]
                        html_content = ''.join(f'<p>{l}</p>' for l in lines)
                        try:
                            injected = await editor_page.evaluate(
                                """(html) => {
                                    if (typeof tinymce !== 'undefined' && tinymce.activeEditor) {
                                        tinymce.activeEditor.setContent(html);
                                        tinymce.activeEditor.fire('change');
                                        tinymce.activeEditor.save();
                                        return 'tinymce';
                                    }
                                    return null;
                                }""",
                                html_content,
                            )
                            if injected != 'tinymce':
                                raise Exception("TinyMCE 不可用")
                        except Exception:
                            await editor_loc.evaluate(
                                """(el, html) => {
                                    el.innerHTML = html;
                                    el.dispatchEvent(new Event('input', {bubbles: true}));
                                    el.dispatchEvent(new Event('change', {bubbles: true}));
                                }""",
                                html_content,
                            )
                    logger.info(f"起点：正文已注入（{len(chapter_content)}字）")
                else:
                    result["message"] = "未找到正文编辑器"
                    await browser.close()
                    return result

                await asyncio.sleep(1)

                # 6. AI 声明
                if ai_disclosure:
                    ai_loc = await self._find_visible(editor_page, [
                        'input[type="checkbox"][name*="ai"]', 'label:has-text("AI")',
                    ])
                    if ai_loc:
                        await ai_loc.click(force=True)

                # 7. 保存/发布
                if mode == "publish":
                    btn_loc = await self._find_visible(editor_page, [
                        'button:has-text("发布")', 'a:has-text("发布")', 'input[value="发布"]',
                    ])
                else:
                    btn_loc = await self._find_visible(editor_page, [
                        'button:has-text("保存")', 'button:has-text("存草稿")', 'a:has-text("保存")',
                    ])

                if btn_loc:
                    pre_click_url = editor_page.url  # noqa: F841
                    await btn_loc.click(force=True)
                    await asyncio.sleep(5)

                    # 验证码检测
                    captcha_loc = await self._find_visible(editor_page, [
                        '#tcaptcha_iframe', '[class*="tcaptcha"]',
                    ])
                    if captcha_loc:
                        result["status"] = "captcha"
                        result["message"] = "触发验证码，需要人工处理后重试"
                        await browser.close()
                        return result

                    # 确认弹窗
                    for confirm_text in ["确认发布", "确定", "确认"]:
                        try:
                            confirm_btn = editor_page.locator(f'button:has-text("{confirm_text}")').first
                            if await confirm_btn.is_visible():
                                await confirm_btn.click(force=True)
                                await asyncio.sleep(3)
                                break
                        except Exception:
                            pass

                    # 成功检测
                    err_loc = await self._find_visible(editor_page, [
                        '.el-message--error', '.error-tip', '[class*="error"]',
                    ])
                    if err_loc:
                        try:
                            error_text = await err_loc.inner_text()
                        except Exception:
                            error_text = "未知错误"
                        result["message"] = f"发布失败：{error_text}"
                    else:
                        result["status"] = "success"
                        result["message"] = f"起点{'发布' if mode == 'publish' else '草稿保存'}成功"
                else:
                    result["message"] = "未找到保存/发布按钮"

            except RuntimeError:
                raise
            except Exception as e:
                logger.error(f"起点发布失败: {e}")
                result["message"] = str(e)
            finally:
                await browser.close()

        return result
