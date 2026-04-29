import type { createDefaultBibleForm } from './formDefaults'

type BibleForm = ReturnType<typeof createDefaultBibleForm>

export function createBiblePayload(form: BibleForm) {
  return {
    ...form,
    content_limits: ['不复制参考项目提示词', '不突破已定义世界规则'],
    cast_members: [
      {
        id: 'cast-main',
        name: '陆沉',
        role: 'protagonist',
        motivation: '重建宗门并查明灵气衰退真相',
        voice_hint: '话少，判断直接',
        forbidden_actions: ['无理由背叛同伴'],
      },
    ],
    places: [
      {
        id: 'place-sect',
        name: '玄衡旧宗',
        kind: 'sect',
        summary: '破败宗门遗址，藏有旧纪元阵图',
        parent_place_id: null,
      },
    ],
    plot_lines: [
      {
        id: 'plot-main',
        name: '重启灵脉',
        goal: '找到九处灵脉节点并重启宗门大阵',
        stakes: '失败则宗门遗址被诸城瓜分',
        current_state: '发现第一枚阵钥',
      },
    ],
    constraint_rules: [
      {
        id: 'rule-tone',
        scope: 'style',
        rule: '保持连载爽感，每章必须有推进和钩子',
        severity: 'warn',
      },
    ],
  }
}
