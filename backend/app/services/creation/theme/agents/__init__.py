"""内置题材 Agent 汇总"""
from app.services.creation.theme.agents.xuanhuan_agent import XuanhuanThemeAgent
from app.services.creation.theme.agents.xianxia_agent import XianxiaThemeAgent
from app.services.creation.theme.agents.wuxia_agent import WuxiaThemeAgent
from app.services.creation.theme.agents.dushi_agent import DushiThemeAgent
from app.services.creation.theme.agents.zhichang_agent import ZhichangThemeAgent
from app.services.creation.theme.agents.romance_agent import RomanceThemeAgent
from app.services.creation.theme.agents.suspense_agent import SuspenseThemeAgent
from app.services.creation.theme.agents.scifi_agent import ScifiThemeAgent
from app.services.creation.theme.agents.history_agent import HistoryThemeAgent
from app.services.creation.theme.agents.game_agent import GameThemeAgent
from app.services.creation.theme.agents.fantasy_agent import FantasyThemeAgent
from app.services.creation.theme.agents.other_agent import OtherThemeAgent

ALL_AGENTS = [
    XuanhuanThemeAgent,
    XianxiaThemeAgent,
    WuxiaThemeAgent,
    DushiThemeAgent,
    ZhichangThemeAgent,
    RomanceThemeAgent,
    SuspenseThemeAgent,
    ScifiThemeAgent,
    HistoryThemeAgent,
    GameThemeAgent,
    FantasyThemeAgent,
    OtherThemeAgent,
]
