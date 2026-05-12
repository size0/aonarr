import { defineStore } from 'pinia'
import { ref } from 'vue'
import { novelApi, type NovelDTO } from '../api/novels'

export const useNovelsStore = defineStore('novels', () => {
  const novels = ref<NovelDTO[]>([])
  const loading = ref(false)

  async function loadNovels() {
    loading.value = true
    try {
      novels.value = await novelApi.list()
    } finally {
      loading.value = false
    }
  }

  async function createNovel(data: Partial<NovelDTO>) {
    const created = await novelApi.create(data)
    novels.value.unshift(created)
    return created
  }

  async function deleteNovel(id: string) {
    await novelApi.delete(id)
    novels.value = novels.value.filter(n => n.id !== id)
  }

  return { novels, loading, loadNovels, createNovel, deleteNovel }
})
