import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: () => import('./views/DashboardPage.vue') },
    { path: '/create', component: () => import('./views/CreateWizardPage.vue') },
    { path: '/studio', component: () => import('./views/StudioPage.vue') },
    { path: '/booklab', component: () => import('./views/BookLabPage.vue') },
    { path: '/blueprint', component: () => import('./views/BlueprintPage.vue') },
    { path: '/worldview', redirect: '/blueprint' },
    { path: '/outline', redirect: '/blueprint' },
    { path: '/publish', component: () => import('./views/PublishPage.vue') },
    { path: '/data', component: () => import('./views/DataBoardPage.vue') },
    { path: '/predict', component: () => import('./views/PredictPage.vue') },
    { path: '/inspiration', component: () => import('./views/InspirationPage.vue') },
    { path: '/learn', component: () => import('./views/LearnHubPage.vue') },
    { path: '/prompts', component: () => import('./views/PromptsPage.vue') },
    { path: '/settings', component: () => import('./views/SettingsPage.vue') },
  ],
})

export default router
