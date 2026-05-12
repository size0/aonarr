"""质量雷达 — 纯本地启发式章节质量评分

不调用 LLM，要快。返回六维雷达分数:
- naturalness: 自然度 (句式重复/机械感)
- reading_power: 阅读吸引力 (钩子/悬念/冲突)
- pacing: 节奏 (张弛有度)
- dialogue: 对话质量 (比例/生动度)
- foreshadowing: 伏笔暗示密度
- continuity: 连贯性 (过渡/衔接)
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class QualityScore:
    """多维质量评分 (0-100)

    基础六维 (纯启发式，快):
      naturalness, reading_power, pacing, dialogue, foreshadowing, continuity
    扩展维度 (启发式):
      ai_detect, vocab_diversity, emotion_arc, sentence_variety
    每个维度附带 issues 列表 (AuditIssue)
    """
    naturalness: float | None = None
    reading_power: float | None = None
    pacing: float | None = None
    dialogue: float | None = None
    foreshadowing: float | None = None
    continuity: float | None = None
    # 扩展维度
    ai_detect: float | None = None        # AI 味检测 (越高越好=越不像AI)
    vocab_diversity: float | None = None  # 词汇多样性
    emotion_arc: float | None = None      # 情感弧线
    sentence_variety: float | None = None # 句式多样性
    # 问题列表
    issues: list = field(default_factory=list)

    @property
    def overall(self) -> float:
        scores = [self.naturalness, self.reading_power, self.pacing,
                  self.dialogue, self.foreshadowing, self.continuity,
                  self.ai_detect, self.vocab_diversity, self.emotion_arc,
                  self.sentence_variety]
        evaluated = [s for s in scores if s is not None]
        return sum(evaluated) / len(evaluated) if evaluated else 0.0

    @property
    def pass_rate(self) -> bool:
        """是否通过审计 (overall >= 60 且无 critical issue)"""
        return self.overall >= 60 and not any(
            i.get('severity') == 'critical' for i in self.issues
        )

    def to_dict(self) -> dict:
        def _r(v: float | None) -> float:
            return round(v, 1) if v is not None else 0.0
        return {
            "naturalness": _r(self.naturalness),
            "reading_power": _r(self.reading_power),
            "pacing": _r(self.pacing),
            "dialogue": _r(self.dialogue),
            "foreshadowing": _r(self.foreshadowing),
            "continuity": _r(self.continuity),
            "ai_detect": _r(self.ai_detect),
            "vocab_diversity": _r(self.vocab_diversity),
            "emotion_arc": _r(self.emotion_arc),
            "sentence_variety": _r(self.sentence_variety),
            "overall": round(self.overall, 1),
            "passed": self.pass_rate,
            "issues": self.issues,
        }


# ── 句式/对话/修辞 正则 ──────────────────────────────────────────

_SENTENCE_END = re.compile(r'[。！？!?\u2026]+')
_DIALOGUE_RE = re.compile(r'[\u201c"](.*?)[\u201d"]', re.DOTALL)
_HOOK_PATTERNS = [
    re.compile(r"(?:突然|忽然|猛然|骤然|霜时|刹那|瞬间)"),
    re.compile(r"(?:难道|莫非|究竟|到底|为何|怎么会|为什么)"),
    re.compile(r"(?:却不知|殊不知|岂料|哪知|谁料|不曾想|没想到)"),
    re.compile(r"(?:一个.*出现|一道.*闪过|一声.*响起)"),
    re.compile(r"[？?!！]{2,}"),
    re.compile(r"(?:等等|不对|不应该|终于|果然|原来如此|可是)"),
    re.compile(r"(?:死死|狠狠|紧紧|重重|狠|使劲|拼命)"),
    re.compile(r"[……]{1,}"),  # 省略号
]
_CONFLICT_PATTERNS = [
    re.compile(r"(?:不行|不许|不可能|休想|别想|你敢|你给我|滚)"),
    re.compile(r"(?:怒道|喝道|厉声|冷笑|冷哼|怒喝|呵斥|轻蔑|嘻笑)"),
    re.compile(r"(?:危险|威胁|对峙|冲突|争执|反抗|抗拒|拉扯|推搞)"),
    re.compile(r"(?:经不住|没办法|来不及|必须|强迫|不得不|必须得)"),
    re.compile(r"(?:手在抖|拳头|放开|住手|闪迟|抽回)"),
]
_FORESHADOW_PATTERNS = [
    re.compile(r"(?:日后|将来|以后|总有一天|迟早|终有一日|早晚|过几天)"),
    re.compile(r"(?:隐约|似乎|好像|莫名|不知为何|总觉得|有种)"),
    re.compile(r"(?:暗中|悄悄|不为人知|秘密|还不知道|没发现)"),
    re.compile(r"(?:留下|埋下|种下).{0,5}(?:伏笔|隐患|种子|根源)"),
    re.compile(r"(?:等他|改天|下次|回头再|到时候|总会|早晚会)"),
]
_TRANSITION_PATTERNS = [
    re.compile(r"(?:与此同时|另一边|话分两头|且说|回头再说)"),
    re.compile(r"(?:时光飞逝|光阴似箭|转眼间|不知不觉|一晃|过了一会儿)"),
    re.compile(r"(?:然而|不过|但是|可是|话虽如此|尽管|只是)"),
    re.compile(r"(?:等到|过了|之后|接下来|随后|紧接着|此时|这时)"),
]
_REPETITION_MIN_LEN = 6


def score_chapter(text: str) -> QualityScore:
    """对章节文本进行多维质量评分（纯启发式，不调LLM）"""
    qs = QualityScore()

    if not text or len(text) < 50:
        return qs

    qs.naturalness = _score_naturalness(text)
    qs.reading_power = _score_reading_power(text)
    qs.pacing = _score_pacing(text)
    qs.dialogue = _score_dialogue(text)
    qs.foreshadowing = _score_foreshadowing(text)
    qs.continuity = _score_continuity(text)
    # 扩展维度
    qs.ai_detect = _score_ai_detect(text)
    qs.vocab_diversity = _score_vocab_diversity(text)
    qs.emotion_arc = _score_emotion_arc(text)
    qs.sentence_variety = _score_sentence_variety(text)
    # 收集问题
    qs.issues = _collect_issues(qs, text)

    return qs


# ── 各维度评分 ──────────────────────────────────────────────────

def _score_naturalness(text: str) -> float:
    """自然度: 检测句式重复/机械感"""
    sentences = [s.strip() for s in _SENTENCE_END.split(text) if len(s.strip()) > 3]
    if len(sentences) < 3:
        return 50.0

    score = 80.0

    # 1) 句首重复率 — 多个句子以相同前缀开头
    starts = [s[:3] for s in sentences if len(s) >= 3]
    start_counts = Counter(starts)
    if starts:
        max_repeat_ratio = max(start_counts.values()) / len(starts)
        if max_repeat_ratio > 0.3:
            score -= (max_repeat_ratio - 0.3) * 80  # 重罚

    # 2) 句长方差过低 → 机械感
    lengths = [len(s) for s in sentences]
    mean_len = sum(lengths) / len(lengths)
    variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
    std = variance ** 0.5
    if std < 5:
        score -= 15  # 过于均匀

    # 3) 短语级重复
    ngrams: Counter = Counter()
    for s in sentences:
        for i in range(len(s) - _REPETITION_MIN_LEN + 1):
            gram = s[i:i + _REPETITION_MIN_LEN]
            if not re.search(r'[\s\u3000]', gram):
                ngrams[gram] += 1
    high_repeat = sum(1 for v in ngrams.values() if v >= 4)
    if high_repeat > 5:
        score -= min(high_repeat * 2, 20)

    # 4) "的了吗呢"连续出现过多
    particle_ratio = len(re.findall(r'[的了吗呢啊哦吧嘛]', text)) / len(text)
    if particle_ratio > 0.08:
        score -= (particle_ratio - 0.08) * 200

    return max(0, min(100, score))


def _score_reading_power(text: str) -> float:
    """阅读吸引力: 钩子/悬念/冲突密度"""
    char_count = len(text)
    if char_count < 100:
        return 50.0

    score = 45.0
    per_1000 = 1000 / char_count

    # 钩子密度
    hook_count = sum(len(p.findall(text)) for p in _HOOK_PATTERNS)
    hook_density = hook_count * per_1000
    score += min(hook_density * 6, 25)

    # 冲突密度
    conflict_count = sum(len(p.findall(text)) for p in _CONFLICT_PATTERNS)
    conflict_density = conflict_count * per_1000
    score += min(conflict_density * 5, 20)

    # 段末悬念 — 段落以问号或省略号结尾
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if paragraphs:
        suspense_endings = sum(
            1 for p in paragraphs
            if p.endswith(("？", "?", "……", "...", "！", "!", "——", "—"))
        )
        suspense_ratio = suspense_endings / len(paragraphs)
        score += min(suspense_ratio * 40, 20)

    # 对话张力 — 对话中的问句和短句增加张力感
    dialogues = _DIALOGUE_RE.findall(text)
    if dialogues:
        tense_dlg = sum(1 for d in dialogues if '?' in d or '？' in d or '!' in d or '！' in d or len(d) < 8)
        if len(dialogues) > 0:
            score += min(tense_dlg / len(dialogues) * 15, 10)

    return max(0, min(100, score))


def _score_pacing(text: str) -> float:
    """节奏: 句长分布张弛有度"""
    sentences = [s.strip() for s in _SENTENCE_END.split(text) if len(s.strip()) > 2]
    if len(sentences) < 5:
        return 50.0

    lengths = [len(s) for s in sentences]
    mean_len = sum(lengths) / len(lengths)
    std = (sum((l - mean_len) ** 2 for l in lengths) / len(lengths)) ** 0.5

    score = 60.0

    # 变化度适中为佳 (std 8-30 为正常网文)
    if 8 <= std <= 30:
        score += 20
    elif std < 5:
        score -= 10  # 过于单调
    elif std > 40:
        score -= 5  # 过于混乱（对话密集时正常偏高）

    # 短长交替检测 — 相邻句子长度变化（放宽阈值）
    changes = 0
    for i in range(1, len(lengths)):
        if (lengths[i] < 20 and lengths[i-1] > 20) or (lengths[i] > 20 and lengths[i-1] < 20):
            changes += 1
    if len(lengths) > 1:
        change_ratio = changes / (len(lengths) - 1)
        score += min(change_ratio * 40, 20)

    # 段落长度变化
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if len(paragraphs) > 3:
        para_lens = [len(p) for p in paragraphs]
        para_std = (sum((l - sum(para_lens)/len(para_lens))**2 for l in para_lens) / len(para_lens)) ** 0.5
        if para_std > 20:
            score += 10

    # 对话密度加分（对话密集=快节奏=好节奏）
    dialogues = _DIALOGUE_RE.findall(text)
    if dialogues:
        dlg_ratio = sum(len(d) for d in dialogues) / len(text)
        if 0.25 <= dlg_ratio <= 0.55:
            score += 10

    return max(0, min(100, score))


def _score_dialogue(text: str) -> float:
    """对话质量: 比例/长度分布/动作标签"""
    dialogues = _DIALOGUE_RE.findall(text)
    if not dialogues:
        return 40.0

    char_count = len(text)
    total_dlg_chars = sum(len(d) for d in dialogues)
    dlg_ratio = total_dlg_chars / char_count if char_count else 0

    score = 50.0

    # 对话比例 — 20-45% 为宜
    if 0.20 <= dlg_ratio <= 0.45:
        score += 20
    elif dlg_ratio < 0.10:
        score -= 10
    elif dlg_ratio > 0.60:
        score -= 15

    # 对话长度分布 — 不应全是长对话或全是短对话
    dlg_lens = [len(d) for d in dialogues]
    if dlg_lens:
        short_dlg = sum(1 for l in dlg_lens if l < 10)
        long_dlg = sum(1 for l in dlg_lens if l > 50)
        variety = (short_dlg > 0 and long_dlg > 0)
        if variety:
            score += 10

    # 动作标签 — 对话附近有动作描写
    action_tags = len(re.findall(
        r'[\u201d"][\s\n]*[\u4e00-\u9fff]{1,4}(?:道|说|喊|叫|笑|怒|叹|问)',
        text,
    ))
    if dialogues and action_tags > 0:
        tag_ratio = action_tags / len(dialogues)
        score += min(tag_ratio * 20, 15)

    # 避免"说说说" — 对话标签重复
    say_tags = re.findall(r'(\S{0,2}(?:说道|说|道))', text)
    if say_tags:
        say_counter = Counter(say_tags)
        most_common_count = say_counter.most_common(1)[0][1]
        if len(dialogues) > 3 and most_common_count / len(dialogues) > 0.5:
            score -= 10

    return max(0, min(100, score))


def _score_foreshadowing(text: str) -> float:
    """伏笔暗示密度"""
    char_count = len(text)
    if char_count < 200:
        return 50.0

    score = 50.0
    per_1000 = 1000 / char_count

    foreshadow_count = sum(len(p.findall(text)) for p in _FORESHADOW_PATTERNS)
    density = foreshadow_count * per_1000

    # 适度为佳 (0.5-5 per 1000 chars)
    if density >= 0.5:
        score += min(density * 10, 30)
    if density > 8:
        score -= 10  # 过多反而不自然

    # 隐性伏笔：疑问句、省略号、未解答的问题
    mystery_count = len(re.findall(r'[？?]', text))
    ellipsis_count = len(re.findall(r'……|\.\.\.|\u2014\u2014', text))
    implicit_density = (mystery_count + ellipsis_count) * per_1000
    score += min(implicit_density * 3, 15)

    return max(0, min(100, score))


def _score_continuity(text: str) -> float:
    """连贯性: 过渡/衔接词/场景切换"""
    char_count = len(text)
    if char_count < 200:
        return 50.0

    score = 55.0
    per_1000 = 1000 / char_count

    # 过渡短语密度
    transition_count = sum(len(p.findall(text)) for p in _TRANSITION_PATTERNS)
    t_density = transition_count * per_1000
    if t_density >= 0.5:
        score += min(t_density * 6, 20)

    # 段落间的逻辑连接
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if len(paragraphs) > 3:
        connected = 0
        connectors = re.compile(r'^(?:然而|不过|但|因此|于是|接着|随后|此时|这时|紧接着|话说|只是|只不过|正当|就在|他|她|林)')
        for p in paragraphs[1:]:
            if connectors.match(p):
                connected += 1
        conn_ratio = connected / (len(paragraphs) - 1)
        score += min(conn_ratio * 30, 15)

    # 对话-叙述交替（自然衔接的标志）
    if len(paragraphs) > 5:
        dlg_pattern = re.compile(r'[“"]')
        alternations = 0
        prev_is_dlg = bool(dlg_pattern.search(paragraphs[0]))
        for p in paragraphs[1:]:
            curr_is_dlg = bool(dlg_pattern.search(p))
            if curr_is_dlg != prev_is_dlg:
                alternations += 1
            prev_is_dlg = curr_is_dlg
        alt_ratio = alternations / (len(paragraphs) - 1)
        if alt_ratio > 0.3:
            score += 10

    # 场景跳跃检测 — 过多场景突变扣分
    scene_breaks = len(re.findall(r'\n\s*\n\s*\n', text))
    if scene_breaks > 5:
        score -= min((scene_breaks - 5) * 3, 15)

    return max(0, min(100, score))


# ── AI 味疲劳词检测词表 ──────────────────────────────────────────────

_AI_FATIGUE_WORDS = [
    "不禁", "竟然", "居然", "内心深处", "心中暗想", "不由自主",
    "默默地", "缓缓地", "微微一笑", "淡淡地", "轻轻地",
    "不知不觉", "仿佛", "似乎", "显然", "毫无疑问",
    "一股", "一丝", "一抹", "一缕", "一阵",
    "眼眸", "瞳子", "瞳光", "瞳中", "薄唇", "轻启",
    "唇角", "眉眼", "眉宇", "凤眸", "星眸",
    "蓦地", "蓦然", "倏地", "倏然", "旋即",
    "心下", "暗忖", "思忖", "暗道", "心道",
    "嘴角微微上扬", "嘴角勾起", "勾起一抹",
    "深吸一口气", "长舒一口气",
]
_AI_BANNED_PATTERNS = [
    re.compile(r"(?:一股|一丝|一缕|一抹)(?:暖|冷|寒|热|莫名|异样|说不清)"),
    re.compile(r"(?:不禁|不由得|下意识)(?:地?)"),
    re.compile(r"眼中闪过一(?:丝|抹|道)"),
    re.compile(r"(?:挺拔|修长)的身(?:影|姿|形)"),
    re.compile(r"(?:清冷|低沉|磁性|沙哑)的(?:声音|嗓音|声线)"),
]


def _score_ai_detect(text: str) -> float:
    """AI 味检测: 越高越好=越不像AI生成"""
    if len(text) < 100:
        return 50.0

    score = 85.0
    per_1000 = 1000 / len(text)

    # 疲劳词密度
    fatigue_count = sum(text.count(w) for w in _AI_FATIGUE_WORDS)
    fatigue_density = fatigue_count * per_1000
    if fatigue_density > 8:
        score -= min((fatigue_density - 8) * 3, 30)
    elif fatigue_density > 4:
        score -= (fatigue_density - 4) * 2

    # 禁用句式
    banned_hits = sum(len(p.findall(text)) for p in _AI_BANNED_PATTERNS)
    banned_density = banned_hits * per_1000
    if banned_density > 3:
        score -= min((banned_density - 3) * 4, 25)
    elif banned_density > 1:
        score -= (banned_density - 1) * 2

    # "的"字过密
    de_count = text.count("的")
    de_density = de_count * per_1000
    if de_density > 40:
        score -= min((de_density - 40) * 0.5, 10)

    # 段落首句模式重复（AI常见）
    paragraphs = [p.strip() for p in text.split("\n") if len(p.strip()) > 5]
    if len(paragraphs) > 5:
        para_starts = [p[:4] for p in paragraphs]
        start_counter = Counter(para_starts)
        max_repeat = max(start_counter.values())
        if max_repeat / len(paragraphs) > 0.25:
            score -= 10

    return max(0, min(100, score))


def _score_vocab_diversity(text: str) -> float:
    """词汇多样性: 基于字/词 type-token ratio"""
    if len(text) < 100:
        return 50.0

    # 字级 TTR
    chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
    if not chars:
        return 50.0

    unique_chars = set(chars)
    char_ttr = len(unique_chars) / len(chars)

    # 长文本 TTR 自然下降，用 MATTR (Moving Average TTR) 思路
    # 对超过 2000 字的文本按窗口计算平均 TTR
    if len(chars) > 2000:
        window = 500
        ttrs = []
        for start in range(0, len(chars) - window, window // 2):
            seg = chars[start:start + window]
            ttrs.append(len(set(seg)) / len(seg))
        char_ttr = sum(ttrs) / len(ttrs) if ttrs else char_ttr

    score = 40.0

    # 字级 TTR 0.3-0.6 为正常网文水平
    if char_ttr >= 0.55:
        score += 40
    elif char_ttr >= 0.45:
        score += 35
    elif char_ttr >= 0.38:
        score += 25
    elif char_ttr >= 0.30:
        score += 15
    else:
        score -= 5

    # 检查高频字重复
    char_counter = Counter(chars)
    top5 = char_counter.most_common(5)
    if top5:
        top5_ratio = sum(c for _, c in top5) / len(chars)
        if top5_ratio < 0.1:
            score += 15
        elif top5_ratio > 0.2:
            score -= 10

    return max(0, min(100, score))


_EMOTION_WORDS = {
    "positive": re.compile(r"(?:高兴|开心|喜悦|欢喜|兴奋|激动|感动|温暖|幸福|快乐|满足|欣慰|得意|骄傲|自豪|笑了|咧嘴|眼睛亮|松了口气|心里踏实|舒服)"),
    "negative": re.compile(r"(?:悲伤|痛苦|愤怒|恐惧|绝望|焦虑|不安|恐慌|愤恨|仇恨|嫉妒|委屈|无奈|心痛|心酸|难受|憋屈|窝火|咬牙|攥紧|发抖|哭|眼眶|鼻子酸)"),
    "tension":  re.compile(r"(?:紧张|害怕|惊恐|战栗|颤抖|冷汗|惊惧|恐惧|心惊|胆寒|骇然|惊骇|吓|愣|呆|僵|定住|喉咙|屏住|咽了口)"),
}


def _score_emotion_arc(text: str) -> float:
    """情感弧线: 检测情感变化是否丰富、有起伏"""
    if len(text) < 200:
        return 50.0

    # 将文本分成 4 段，检测每段情感分布
    segment_len = len(text) // 4
    segments = [text[i*segment_len:(i+1)*segment_len] for i in range(4)]

    emotion_scores = []
    for seg in segments:
        pos = len(_EMOTION_WORDS["positive"].findall(seg))
        neg = len(_EMOTION_WORDS["negative"].findall(seg))
        ten = len(_EMOTION_WORDS["tension"].findall(seg))
        total = pos + neg + ten
        if total == 0:
            emotion_scores.append(0)
        else:
            polarity = (pos - neg) / total
            emotion_scores.append(polarity)

    score = 50.0

    # 有情感变化加分
    if len(set(round(e, 1) for e in emotion_scores)) > 1:
        score += 15

    # 情感起伏幅度
    if emotion_scores:
        amplitude = max(emotion_scores) - min(emotion_scores)
        if amplitude > 0.5:
            score += 20
        elif amplitude > 0.2:
            score += 10

    # 不能全是同一情感
    total_pos = sum(len(_EMOTION_WORDS["positive"].findall(s)) for s in segments)
    total_neg = sum(len(_EMOTION_WORDS["negative"].findall(s)) for s in segments)
    total_ten = sum(len(_EMOTION_WORDS["tension"].findall(s)) for s in segments)
    all_emo = total_pos + total_neg + total_ten
    if all_emo > 0:
        types_used = sum(1 for v in [total_pos, total_neg, total_ten] if v > 0)
        score += types_used * 5

    return max(0, min(100, score))


def _score_sentence_variety(text: str) -> float:
    """句式多样性: 句子开头/结尾/长度分布"""
    sentences = [s.strip() for s in _SENTENCE_END.split(text) if len(s.strip()) > 3]
    if len(sentences) < 5:
        return 50.0

    score = 55.0

    # 句首多样性
    starts_2char = [s[:2] for s in sentences if len(s) >= 2]
    if starts_2char:
        unique_starts = len(set(starts_2char))
        start_variety = unique_starts / len(starts_2char)
        if start_variety > 0.7:
            score += 20
        elif start_variety > 0.5:
            score += 10
        elif start_variety < 0.3:
            score -= 15

    # 句长分布 — 应有短句、中句、长句
    lengths = [len(s) for s in sentences]
    short = sum(1 for l in lengths if l < 10)
    medium = sum(1 for l in lengths if 10 <= l <= 30)
    long = sum(1 for l in lengths if l > 30)
    total = len(lengths)
    types_present = sum(1 for v in [short, medium, long] if v > 0)
    if types_present == 3:
        score += 15
    elif types_present == 2:
        score += 5

    # 没有某种类型占比过大（但对话密集文本短句多是正常的）
    max_ratio = max(short, medium, long) / total if total else 0
    dlg_count = len(_DIALOGUE_RE.findall(text))
    is_dialogue_heavy = dlg_count > len(sentences) * 0.3
    if max_ratio > 0.7 and not is_dialogue_heavy:
        score -= 10
    elif max_ratio > 0.85:
        score -= 5  # 即使对话多，极端不平衡也扣一点

    # 对话中的句式变化（问句、感叹、祈使的混合）
    if dlg_count > 3:
        dlg_texts = _DIALOGUE_RE.findall(text)
        q_count = sum(1 for d in dlg_texts if '？' in d or '?' in d)
        excl_count = sum(1 for d in dlg_texts if '！' in d or '!' in d)
        stmt_count = dlg_count - q_count - excl_count
        dlg_types = sum(1 for v in [q_count, excl_count, stmt_count] if v > 0)
        if dlg_types >= 3:
            score += 10
        elif dlg_types >= 2:
            score += 5

    return max(0, min(100, score))


def _collect_issues(qs: QualityScore, text: str) -> list[dict]:
    """根据各维度分数收集问题列表"""
    issues = []

    def add(dim: str, severity: str, msg: str):
        issues.append({"dimension": dim, "severity": severity, "message": msg})

    def _below(val: float | None, threshold: float) -> bool:
        return val is not None and val < threshold

    if _below(qs.naturalness, 50):
        add("naturalness", "critical" if qs.naturalness < 30 else "warning",
            f"自然度偏低({qs.naturalness:.0f})，可能存在句式重复或机械感")
    if _below(qs.reading_power, 45):
        add("reading_power", "warning", f"阅读吸引力不足({qs.reading_power:.0f})")
    if _below(qs.pacing, 40):
        add("pacing", "warning", f"节奏单调({qs.pacing:.0f})，缺乏张弛变化")
    if _below(qs.dialogue, 35):
        add("dialogue", "warning", f"对话质量偏低({qs.dialogue:.0f})")
    if _below(qs.ai_detect, 50):
        add("ai_detect", "critical" if qs.ai_detect < 30 else "warning",
            f"AI味过重({qs.ai_detect:.0f})，疲劳词/套路句式过多")
    if _below(qs.vocab_diversity, 40):
        add("vocab_diversity", "warning", f"词汇多样性不足({qs.vocab_diversity:.0f})")
    if _below(qs.emotion_arc, 40):
        add("emotion_arc", "info", f"情感弧线平淡({qs.emotion_arc:.0f})")
    if _below(qs.sentence_variety, 40):
        add("sentence_variety", "warning", f"句式过于单一({qs.sentence_variety:.0f})")

    return issues
