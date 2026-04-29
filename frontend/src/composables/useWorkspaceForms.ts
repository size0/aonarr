import { ref, type Ref } from 'vue'
import {
  createDefaultBibleForm,
  createDefaultLLMForm,
  createDefaultProjectForm,
  createDefaultRunForm,
} from '../formDefaults'
import type { Project } from '../types'

type UseWorkspaceFormsSource = {
  selectedProject: Ref<Project | null>
}

export function useWorkspaceForms(source: UseWorkspaceFormsSource) {
  const llmForm = ref(createDefaultLLMForm())
  const newProjectForm = ref(createDefaultProjectForm())
  const projectForm = ref(createDefaultProjectForm())
  const bibleForm = ref(createDefaultBibleForm())
  const runForm = ref(createDefaultRunForm())

  function syncProjectFormFromSelectedProject() {
    if (!source.selectedProject.value) return
    projectForm.value = {
      title: source.selectedProject.value.title,
      genre: source.selectedProject.value.genre,
      target_chapter_count: source.selectedProject.value.target_chapter_count,
      target_words_per_chapter: source.selectedProject.value.target_words_per_chapter,
      style_goal: source.selectedProject.value.style_goal,
    }
  }

  return {
    bibleForm,
    llmForm,
    newProjectForm,
    projectForm,
    runForm,
    syncProjectFormFromSelectedProject,
  }
}
