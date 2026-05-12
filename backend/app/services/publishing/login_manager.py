"""通用平台登录态管理 (Playwright storage_state)"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("NOVELFORGE_DATA_DIR", "./data"))
STATES_DIR = DATA_DIR / "login_states"


class LoginStateManager:
    """管理各平台的浏览器登录态 (cookies + localStorage)"""

    def __init__(self, platform: str, state_dir: str | None = None):
        self.platform = platform
        self.state_dir = Path(state_dir) if state_dir else STATES_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)

    @property
    def state_file(self) -> str:
        return str(self.state_dir / f"{self.platform}_state.json")

    def get_status(self) -> dict:
        """获取当前登录态状态"""
        path = Path(self.state_file)
        if not path.exists():
            return {
                "platform": self.platform,
                "ready": False,
                "exists": False,
                "size": 0,
                "modified_at": None,
                "message": "登录态文件不存在，请先采集登录态",
            }
        stat = path.stat()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            has_cookies = bool(data.get("cookies"))
            modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            return {
                "platform": self.platform,
                "ready": has_cookies,
                "exists": True,
                "size": stat.st_size,
                "modified_at": modified_at,
                "message": "登录态已就绪" if has_cookies else "登录态文件存在但无有效cookies",
            }
        except Exception as e:
            logger.warning(f"[{self.platform}] 读取登录态文件失败: {e}")
            return {
                "platform": self.platform,
                "ready": False,
                "exists": True,
                "size": stat.st_size,
                "modified_at": None,
                "message": f"登录态文件损坏: {e}",
            }

    def save_state(self, cookies: list[dict], local_storage: dict | None = None) -> dict:
        """保存登录态"""
        path = Path(self.state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "cookies": cookies,
            "origins": local_storage.get("origins", []) if local_storage else [],
            "local_storage": local_storage or {},
            "captured_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[{self.platform}] 登录态已保存: {len(cookies)} cookies")
        return self.get_status()

    def load_state(self) -> dict | None:
        """加载登录态"""
        path = Path(self.state_file)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[{self.platform}] 加载登录态失败: {e}")
            return None

    def clear_state(self) -> dict:
        """清除登录态"""
        path = Path(self.state_file)
        if path.exists():
            path.unlink()
            logger.info(f"[{self.platform}] 登录态已清除")
        return self.get_status()

    def is_ready(self) -> bool:
        """登录态是否可用"""
        return self.get_status()["ready"]
