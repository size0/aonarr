import apiClient from './client'

export interface OutlineNodeDTO {
  id: string
  novel_id: string
  parent_id: string | null
  level: string  // volume | act | chapter | scene | beat
  title: string
  summary: string
  sort_order: number
  metadata_json: Record<string, any>
  created_at: string | null
  children?: OutlineNodeDTO[]
}

export interface OutlineNodeCreate {
  parent_id?: string | null
  level?: string
  title?: string
  summary?: string
  sort_order?: number
  metadata_json?: string
}

export interface OutlineNodeUpdate {
  parent_id?: string | null
  level?: string
  title?: string
  summary?: string
  sort_order?: number
  metadata_json?: string
}

export interface ReorderItem {
  id: string
  sort_order: number
  parent_id?: string | null
}

export const outlineApi = {
  async getTree(novelId: string): Promise<OutlineNodeDTO[]> {
    const res = await apiClient.get(`/novels/${novelId}/outline`)
    return res.data
  },

  async getFlat(novelId: string): Promise<OutlineNodeDTO[]> {
    const res = await apiClient.get(`/novels/${novelId}/outline`, { params: { flat: true } })
    return res.data
  },

  async createNode(novelId: string, data: OutlineNodeCreate): Promise<OutlineNodeDTO> {
    const res = await apiClient.post(`/novels/${novelId}/outline`, data)
    return res.data
  },

  async updateNode(novelId: string, nodeId: string, data: OutlineNodeUpdate): Promise<OutlineNodeDTO> {
    const res = await apiClient.patch(`/novels/${novelId}/outline/${nodeId}`, data)
    return res.data
  },

  async deleteNode(novelId: string, nodeId: string): Promise<void> {
    await apiClient.delete(`/novels/${novelId}/outline/${nodeId}`)
  },

  async reorder(novelId: string, items: ReorderItem[]): Promise<void> {
    await apiClient.post(`/novels/${novelId}/outline/reorder`, { items })
  },
}
