import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { novelApi, type NovelDTO, type ChapterDTO } from '../api/novels'

export const useCreationStore = defineStore('creation', () => {
  const currentNovel = ref<NovelDTO | null>(null)
  const chapters = ref<ChapterDTO[]>([])
  const currentChapter = ref<ChapterDTO | null>(null)
  const loading = ref(false)
  const sseStreaming = ref(false)

  const sortedChapters = computed(() =>
    [...chapters.value].sort((a, b) => a.number - b.number)
  )

  async function selectNovel(novelId: string) {
    loading.value = true
    try {
      currentNovel.value = await novelApi.get(novelId)
      chapters.value = await novelApi.listChapters(novelId)
      currentChapter.value = null
    } finally {
      loading.value = false
    }
  }

  function selectChapter(chapter: ChapterDTO) {
    currentChapter.value = chapter
  }

  async function refreshChapters() {
    if (!currentNovel.value) return
    chapters.value = await novelApi.listChapters(currentNovel.value.id)
  }

  async function addChapter(data: Partial<ChapterDTO>) {
    if (!currentNovel.value) return
    const created = await novelApi.createChapter(currentNovel.value.id, data)
    chapters.value.push(created)
    currentChapter.value = created
    return created
  }

  function $reset() {
    currentNovel.value = null
    chapters.value = []
    currentChapter.value = null
    loading.value = false
    sseStreaming.value = false
  }

  return {
    currentNovel, chapters, sortedChapters, currentChapter,
    loading, sseStreaming,
    selectNovel, selectChapter, refreshChapters, addChapter, $reset,
  }
})
