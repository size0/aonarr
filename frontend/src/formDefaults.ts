export function createDefaultLLMForm() {
  return {
    name: '本地 OpenAI 兼容模型',
    provider_type: 'openai_compatible',
    base_url: 'http://localhost:11434/v1',
    model: 'demo-model',
    api_key: 'demo-key',
  }
}

export function createDefaultProjectForm() {
  return {
    title: '长夜星火',
    genre: '玄幻',
    target_chapter_count: 120,
    target_words_per_chapter: 3000,
    style_goal: '节奏紧凑，冲突清晰，章末有钩子',
  }
}

export function createDefaultBibleForm() {
  return {
    premise: '灵气衰退的时代，少年在废弃宗门中发现旧纪元传承。',
    world_summary: '宗门衰败，诸城割据，灵脉成为各方争夺的核心。',
    tone_profile: '第三人称，冷静克制，少解释，多行动。',
  }
}

export function createDefaultRunForm() {
  return {
    target_chapter_count: 3,
    cost_limit: 1,
  }
}
