import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { outlineApi, type OutlineNodeDTO, type OutlineNodeCreate, type OutlineNodeUpdate, type ReorderItem } from '../api/outline'

export const useOutlineStore = defineStore('outline', () => {
  const tree = ref<OutlineNodeDTO[]>([])
  const loading = ref(false)
  const currentNovelId = ref<string>('')
  const selectedNodeId = ref<string>('')

  const selectedNode = computed(() => {
    if (!selectedNodeId.value) return null
    return findNode(tree.value, selectedNodeId.value)
  })

  const flatNodes = computed(() => {
    const flat: OutlineNodeDTO[] = []
    function walk(nodes: OutlineNodeDTO[]) {
      for (const n of nodes) {
        flat.push(n)
        if (n.children?.length) walk(n.children)
      }
    }
    walk(tree.value)
    return flat
  })

  function findNode(nodes: OutlineNodeDTO[], id: string): OutlineNodeDTO | null {
    for (const n of nodes) {
      if (n.id === id) return n
      if (n.children?.length) {
        const found = findNode(n.children, id)
        if (found) return found
      }
    }
    return null
  }

  async function loadOutline(novelId: string) {
    loading.value = true
    currentNovelId.value = novelId
    try {
      tree.value = await outlineApi.getTree(novelId)
    } catch (e) {
      tree.value = []
    } finally {
      loading.value = false
    }
  }

  async function addNode(data: OutlineNodeCreate) {
    if (!currentNovelId.value) return null
    const node = await outlineApi.createNode(currentNovelId.value, data)
    await loadOutline(currentNovelId.value)
    return node
  }

  async function updateNode(nodeId: string, data: OutlineNodeUpdate) {
    if (!currentNovelId.value) return null
    const updated = await outlineApi.updateNode(currentNovelId.value, nodeId, data)
    await loadOutline(currentNovelId.value)
    return updated
  }

  async function deleteNode(nodeId: string) {
    if (!currentNovelId.value) return
    await outlineApi.deleteNode(currentNovelId.value, nodeId)
    if (selectedNodeId.value === nodeId) selectedNodeId.value = ''
    await loadOutline(currentNovelId.value)
  }

  async function reorder(items: ReorderItem[]) {
    if (!currentNovelId.value) return
    await outlineApi.reorder(currentNovelId.value, items)
    await loadOutline(currentNovelId.value)
  }

  function selectNode(id: string) {
    selectedNodeId.value = id
  }

  return {
    tree, loading, currentNovelId, selectedNodeId, selectedNode, flatNodes,
    loadOutline, addNode, updateNode, deleteNode, reorder, selectNode,
  }
})
