<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import {
  PERSONAL_RESOURCE_DEFS,
  type PersonalResourceTab,
} from '@/constants/personalResources'

const props = defineProps<{
  visible: boolean
  activeTab: PersonalResourceTab
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'update:activeTab', val: PersonalResourceTab): void
  (e: 'open-report', payload: unknown): void
  (e: 'open-conversation', payload: unknown): void
  (e: 'open-question', payload: { query: string; action: 'send' | 'fill' }): void
}>()

const PersonalMemoryPanel = defineAsyncComponent(
  () => import('@/components/personal/PersonalMemoryPanel.vue'),
)
const PersonalTokenUsage = defineAsyncComponent(
  () => import('@/components/personal/PersonalTokenUsage.vue'),
)
const DataPortalHome = defineAsyncComponent(
  () => import('@/views/DataPortalHome.vue'),
)
const SkillsManagement = defineAsyncComponent(
  () => import('@/views/SkillsManagement.vue'),
)
const McpManagement = defineAsyncComponent(
  () => import('@/views/McpManagement.vue'),
)
const TaskCenter = defineAsyncComponent(
  () => import('@/views/TaskCenter.vue'),
)

const close = () => emit('update:visible', false)

const setTab = (tab: PersonalResourceTab) => {
  if (props.activeTab === tab) return
  emit('update:activeTab', tab)
}
</script>

<template>
  <div
    v-if="visible"
    class="absolute inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
    @click.self="close"
  >
    <div
      class="bg-white/95 dark:bg-gray-800/95 backdrop-blur-md rounded-2xl shadow-2xl w-[min(920px,96vw)] max-h-[85vh] border border-gray-200/80 dark:border-gray-700/80 transform transition-all scale-100 animate-fade-in-up flex flex-col overflow-hidden"
    >
      <!-- Header -->
      <div class="flex justify-between items-center px-5 sm:px-6 pt-5 pb-3 flex-shrink-0">
        <h3 class="text-sm font-black text-gray-800 dark:text-gray-100 uppercase tracking-widest">
          我的资源
        </h3>
        <button
          type="button"
          class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          aria-label="关闭"
          @click="close"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      <!-- Tabs -->
      <div
        class="flex flex-shrink-0 gap-1 overflow-x-auto px-5 sm:px-6 pb-3 border-b border-gray-100 dark:border-gray-700/60"
      >
        <button
          v-for="spec in PERSONAL_RESOURCE_DEFS"
          :key="spec.tab"
          type="button"
          class="whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-bold transition-colors"
          :class="
            activeTab === spec.tab
              ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200'
              : 'text-gray-500 hover:bg-gray-50 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-700/50 dark:hover:text-gray-200'
          "
          @click="setTab(spec.tab)"
        >
          {{ spec.label }}
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 min-h-0 overflow-y-auto px-4 sm:px-5 py-4 custom-scrollbar">
        <PersonalMemoryPanel v-if="activeTab === 'memory'" />
        <PersonalTokenUsage v-else-if="activeTab === 'tokens'" />
        <DataPortalHome
          v-else-if="activeTab === 'data'"
          embedded
          delegate-navigation
          @open-report="emit('open-report', $event)"
          @open-conversation="emit('open-conversation', $event)"
          @open-question="emit('open-question', $event)"
        />
        <SkillsManagement v-else-if="activeTab === 'skills'" personal-only />
        <McpManagement v-else-if="activeTab === 'mcp'" personal-only />
        <TaskCenter
          v-else-if="activeTab === 'tasks'"
          personal-only
          embedded
          @open-report="emit('open-report', $event)"
        />
      </div>
    </div>
  </div>
</template>
