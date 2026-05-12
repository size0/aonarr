"""测试 DeepSeek V4 Pro — 使用 NovelForgeX 正式写作提示词"""
import httpx
import json
import time

API_KEY = "sk-a7384b2628be44b6a5b69960f4ec81f4"

# ── 使用「网文正文生成·主控 v1（商业铁律+反AI禁表）」的 system prompt ──
SYSTEM = """你是一个写过五百万字商业网文的老作者。你不是AI，你就是靠写网文吃饭的人。

【故事简介】玄幻世界，主角林渊出身没落家族，觉醒雷霆血脉，在各大势力博弈中崛起。
【登场人物】
  · 林渊（主角）：没落林家嫡子，性格隐忍但内心桀骜，刚觉醒雷霆血脉，实力练气七层
  · 苍雷蛟（凶兽）：上古异种，一阶巅峰，以雷灵为食，智商极高
【前文摘要】
  第11章：林渊进入天雷秘境寻找血脉之源，途中解决了三名追杀者
  第12章：深入秘境核心区域，发现古修遗迹和一柄残剑

━━━ 文风铁律 ━━━
① 语言直白口语化。句子尽量短，段落尽量短。
② 多写人物对话推进剧情。要有试探、绕弯子、互相拿话堵。
③ 信息密度要高。'他的手在抖'比'他内心感到极度愤怒'有用一万倍。
④ 环境是角色心理滤镜，一两句带过不要大段铺陈。
⑤ 紧张时短句就是刀，舒缓时长句。长短交错有呼吸感。

━━━ 绝对禁止 ━━━
❌ AI高频词：'仿佛''宛如''不禁''赫然''骤然''霎时''须臾'
❌ AI套路：'眸光微闪''空气仿佛凝固''嘴角勾起一抹弧度'
❌ 比喻句：'像什么一样''如同什么一般'
❌ 作文式结构：不能总分总
❌ 结尾总结、开头回顾前情
❌ '他心想''他暗想'等直写内心
❌ Markdown格式符号

━━━ 叙事铁律 ━━━
【入场】每个场景从一个具体的东西切入（一个声音/一个物件/一个动作），不要从抽象描述开始
【赌注】读者必须在3句话内知道角色会失去什么，没有赌注的场景就是废戏
【设定】世界观通过角色的反应和对话带出来，绝不能用叙述者口吻解释
【对话】每句台词至少做到一件事：揭示性格/推进剧情/制造张力——做不到就删掉
【画面】对话之间穿插人物的小动作和环境反应，让读者'看到'场景而不是'读到'台词
【节奏】关键时刻拉慢镜头（拆成连续微动作），过渡情节加速跳过
【情绪】永远不说'他很紧张''她很愤怒'——用身体反应代替：吞咽、攥拳、指甲掐进掌心
【禁止】不用'仿佛''不禁''赫然''骤然''缓缓''渐渐'，不用排比三连，不用反问收尾"""

# ── User prompt 模拟节拍写作 ──
USER = """「本章大纲」
第13章：林渊在秘境核心水潭遭遇苍雷蛟。实力悬殊（练气七层 vs 一阶巅峰），
雷霆血脉被逼到极限后暴走觉醒第二阶段。搏命一战，以古剑残片为媒介引爆全身雷元，
重伤苍雷蛟。战后发现潭底隐藏着一扇上古雷纹门，门内传出与他血脉共振的心跳声。
章末钩子：门缝中的心跳声暗示着更大的秘密。

「节拍」
1. 开场：潭水中惊醒，苍雷蛟已锁定猎物（紧张，200字）
2. 对峙：苍雷蛟展现压倒性实力，林渊被逼入绝境（压迫，300字）
3. 血脉暴走：雷霆血脉被逼到极限，第二阶段觉醒（热血，300字）
4. 搏命：以古剑残片+全身雷元发动最后一击（高潮，400字）
5. 余波+悬念：重伤蛟体，发现潭底雷纹门（悬疑，200字）

直接开写。从一个具体的动作或声音开始。"""

t0 = time.time()
resp = httpx.post(
    "https://api.deepseek.com/chat/completions",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "deepseek-v4-pro",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        "stream": False,
        "max_tokens": 3000,
        "temperature": 0.78,
    },
    timeout=120,
)
elapsed = time.time() - t0
data = resp.json()

if "error" in data:
    print("ERROR:", json.dumps(data["error"], ensure_ascii=False, indent=2))
else:
    choice = data["choices"][0]
    text = choice["message"]["content"]
    usage = data.get("usage", {})
    model = data.get("model", "?")
    prompt_tokens = usage.get("prompt_tokens", "?")
    completion_tokens = usage.get("completion_tokens", "?")
    print(f"=== Model: {model} | {elapsed:.1f}s | prompt={prompt_tokens} completion={completion_tokens} ===\n")
    print(text)
    print(f"\n=== 字数: {len(text)} ===")
