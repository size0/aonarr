import { defineStore } from 'pinia'
import { ref } from 'vue'
import { llmApi, type StageModelConfig } from '../api/llmSettings'

export const useLLMSettingsStore = defineStore('llmSettings', () => {
  const config = ref<StageModelConfig | null>(null)
  const loading = ref(false)

  async function loadConfig() {
    loading.value = true
    try {
      config.value = await llmApi.getConfig()
    } finally {
      loading.value = false
    }
  }

  async function applyPreset(preset: string) {
    await llmApi.applyPreset(preset)
    await loadConfig()
  }

  async function bindStage(stage: string, profileId: string) {
    await llmApi.bindStage(stage, profileId)
    await loadConfig()
  }

  return { config, loading, loadConfig, applyPreset, bindStage }
})
