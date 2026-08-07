<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import axios from '@/utils/axios'
import { useToast } from '@/composables/useToast'
import { useUser } from '@/composables/useUser'
import ConfirmModal from '../../components/ConfirmModal.vue'
import Switch from '../Switch.vue'
import McpToolTester from './McpToolTester.vue'
import {
  buildDefaultMcpServerName,
  buildMcpServerNamePrefix,
  composeMcpServerName,
  normalizeMcpServerNameSuffix,
  stripMcpServerNamePrefix,
} from '@/utils/mcpServerName'
import {
  parseMcpServersPaste,
  suggestMcpNameSuffixFromKey,
} from '@/utils/parseMcpServersPaste'
import { 
  PlusIcon,
  BeakerIcon,
  EyeIcon,
  EyeSlashIcon,
  CodeBracketIcon,
  ListBulletIcon,
  ArrowPathIcon,
  TrashIcon,
  PencilSquareIcon,
  LinkIcon,
  CloudArrowDownIcon,
  MagnifyingGlassIcon,
  SparklesIcon,
  ShoppingBagIcon,
  ClipboardDocumentIcon,
  ChevronLeftIcon,
} from '@heroicons/vue/24/outline'

const props = withDefaults(defineProps<{
  scope?: 'global' | 'personal'
}>(), {
  scope: 'global'
})

const { showToast } = useToast()
const { userInfo } = useUser()
const canSave = computed(() => {
  if (props.scope === 'personal') return true
  return userInfo.value?.role === 'admin'
})

const namePrefix = computed(() =>
  buildMcpServerNamePrefix(props.scope, userInfo.value?.user_name),
)

/** 用户只填后缀；保存时与固定前缀拼接 */
const serverNameSuffix = ref('')
/** 第一步录入方式：手动 / JSON 粘贴 */
const connectionInputTab = ref<'manual' | 'json'>('manual')
const mcpJsonPaste = ref('')
const mcpJsonPasteHint = ref('')

const syncFullServerName = () => {
  newServer.value.server_name = composeMcpServerName(
    props.scope,
    userInfo.value?.user_name,
    serverNameSuffix.value,
  )
}

watch(serverNameSuffix, () => {
  syncFullServerName()
})

watch(
  () => [props.scope, userInfo.value?.user_name] as const,
  () => {
    syncFullServerName()
  },
)

const getApiErrorMessage = (error: any, fallback: string) => {
  const responseData = error?.response?.data
  const candidates = [
    responseData?.message,
    responseData?.detail,
    responseData?.data?.message,
    responseData?.data?.detail,
  ]
  const message = candidates.find((value) => typeof value === 'string' && value.trim())
  return message || fallback
}

const servers = ref<any[]>([])
const loading = ref(false)
const showAddModal = ref(false)
const isEditing = ref(false)
const editingId = ref('')

// Tool Tester Logic
const showTester = ref(false)
const toolToTest = ref<any>(null)

const openTester = (tool: any) => {
  toolToTest.value = tool
  showTester.value = true
}

const wizardStep = ref<1 | 2>(1) // 1: Input & Verify, 2: Preview & Name
const verifying = ref(false)
const discoveredTools = ref<any[]>([])
const syncLoading = ref<Record<string, boolean>>({})
const statusLoading = ref<Record<string, boolean>>({})
const credentialNeedsAttention = (server: any) =>
  ['migration_pending', 'rotation_required'].includes(String(server?.credential_status || ''))
const credentialStatusLabel = (server: any) =>
  server?.credential_status === 'migration_pending' ? '凭据待加密' : '凭据待重录'

type McpAgentUsage = {
  id: string
  name: string
  display_name: string
  is_enabled: boolean
  active: boolean
  version_count: number
}

type McpServerUsage = {
  server_id: string
  bound_agent_count: number
  active_agent_count: number
  bound_version_count: number
  agents: McpAgentUsage[]
}

const selectedServerUsage = ref<McpServerUsage | null>(null)
const usageLoading = ref<Record<string, boolean>>({})
const showStatusConfirm = ref(false)
const statusConfirmServer = ref<any | null>(null)
const statusConfirmUsage = ref<McpServerUsage | null>(null)
const statusConfirmLoading = ref(false)

// Batch Actions Logic
const selectedToolIds = ref<Set<string>>(new Set())
const selectedServer = ref<any>(null)
const tools = ref<any[]>([])
const toolsLoading = ref(false)
const isSelectedServerEnabled = computed(() => Number(selectedServer.value?.enabled_status) === 1)
const canManageSelectedTools = computed(() => canSave.value && isSelectedServerEnabled.value)
const canManageTool = (tool: any) => canManageSelectedTools.value && tool?.is_available !== false

const isAllSelected = computed(() => {
  const selectableTools = tools.value.filter(tool => tool.is_available !== false)
  return selectableTools.length > 0 && selectedToolIds.value.size === selectableTools.length
})

const toggleSelectAll = () => {
  if (!canManageSelectedTools.value) return
  if (isAllSelected.value) {
    selectedToolIds.value.clear()
  } else {
    tools.value
      .filter(tool => tool.is_available !== false)
      .forEach(tool => selectedToolIds.value.add(tool.id))
  }
}

const toggleSelectTool = (id: string) => {
  if (!canManageSelectedTools.value) return
  if (selectedToolIds.value.has(id)) {
    selectedToolIds.value.delete(id)
  } else {
    selectedToolIds.value.add(id)
  }
}

const batchUpdateStatus = async (published: boolean) => {
  const ids = tools.value
    .filter(tool => selectedToolIds.value.has(tool.id) && tool.is_available !== false)
    .map(tool => tool.id)
  if (!canManageSelectedTools.value || ids.length === 0) return
  
  loading.value = true
  try {
    // Batch update in parallel
    await Promise.all(ids.map(id => 
      axios.put(`/api/portal/mcp/tools/${id}/publish?published=${published}`)
    ))
    
    showToast(`成功${published ? '发布' : '下线'} ${ids.length} 个工具`, 'success')
    if (selectedServer.value) {
      fetchTools(selectedServer.value.id)
      fetchServerUsage(selectedServer.value.id).then((usage) => {
        if (selectedServer.value) selectedServerUsage.value = usage
      })
    }
    selectedToolIds.value.clear()
  } catch (e) {
    showToast(getApiErrorMessage(e, '批量操作失败'), 'error')
  } finally {
    loading.value = false
  }
}

// Headers Editing Logic
const headerMode = ref<'simple' | 'advanced'>('simple')
const headerPairs = ref<{ key: string, value: string }[]>([{ key: '', value: '' }])

const addHeaderPair = () => {
  markAuthHeadersDirty()
  headerPairs.value.push({ key: '', value: '' })
}
const removeHeaderPair = (index: number) => {
  markAuthHeadersDirty()
  headerPairs.value.splice(index, 1)
  if (headerPairs.value.length === 0) addHeaderPair()
}

const newServer = ref({
  server_name: '',
  remark: '',
  sse_url: '',
  auth_headers: '{}',
  enabled_status: 1
})
const existingAuthHeadersConfigured = ref(false)
const authHeadersDirty = ref(false)
const editingCredentialStatus = ref('empty')

const markAuthHeadersDirty = () => {
  authHeadersDirty.value = true
}

// Sync Header Pairs to JSON string
watch(headerPairs, (newPairs) => {
  if (headerMode.value === 'simple') {
    if (isEditing.value && existingAuthHeadersConfigured.value && !authHeadersDirty.value) {
      newServer.value.auth_headers = ''
      return
    }
    const obj: Record<string, string> = {}
    newPairs.forEach(p => {
      if (p.key.trim()) obj[p.key.trim()] = p.value
    })
    newServer.value.auth_headers = JSON.stringify(obj, null, 2)
  }
}, { deep: true })

// Sync JSON string to Header Pairs
const syncJsonToPairs = () => {
  try {
    const obj = JSON.parse(newServer.value.auth_headers)
    const pairs = Object.entries(obj).map(([k, v]) => ({ key: k, value: String(v) }))
    headerPairs.value = pairs.length > 0 ? pairs : [{ key: '', value: '' }]
  } catch (e) {
    console.error("Invalid JSON for headers")
  }
}

const toggleHeaderMode = () => {
  if (headerMode.value === 'advanced') {
    syncJsonToPairs()
    headerMode.value = 'simple'
  } else {
    headerMode.value = 'advanced'
  }
}

const fetchServers = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/portal/mcp/servers', {
      params: { scope: props.scope }
    })
    servers.value = res.data
  } catch (e) {
    showToast(getApiErrorMessage(e, '获取 MCP 服务列表失败'), 'error')
  } finally {
    loading.value = false
  }
}

const resetWizard = () => {
  isEditing.value = false
  editingId.value = ''
  wizardStep.value = 1
  verifying.value = false
  discoveredTools.value = []
  newServer.value = { server_name: '', remark: '', sse_url: '', auth_headers: '{}', enabled_status: 1 }
  serverNameSuffix.value = ''
  connectionInputTab.value = 'manual'
  mcpJsonPaste.value = ''
  mcpJsonPasteHint.value = ''
  headerPairs.value = [{ key: '', value: '' }]
  headerMode.value = 'simple'
  existingAuthHeadersConfigured.value = false
  authHeadersDirty.value = false
  editingCredentialStatus.value = 'empty'
}

const openEditModal = (server: any) => {
  isEditing.value = true
  editingId.value = server.id
  wizardStep.value = 1
  serverNameSuffix.value = stripMcpServerNamePrefix(
    server.server_name,
    props.scope,
    userInfo.value?.user_name,
  )
  existingAuthHeadersConfigured.value = Boolean(server.has_auth_headers)
  authHeadersDirty.value = false
  editingCredentialStatus.value = String(server.credential_status || 'empty')
  headerPairs.value = [{ key: '', value: '' }]
  newServer.value = {
    server_name: server.server_name,
    remark: server.remark || '',
    sse_url: server.sse_url,
    auth_headers: '',
    enabled_status: server.enabled_status
  }
  syncFullServerName()
  syncJsonToPairs()
  showAddModal.value = true
}

const toggleServerStatus = async (server: any, enabled: boolean) => {
  if (
    !canSave.value
    || statusLoading.value[server.id]
    || (enabled && credentialNeedsAttention(server))
  ) return false

  const nextStatus = enabled ? 1 : 0
  if (Number(server.enabled_status) === nextStatus) return true

  statusLoading.value[server.id] = true
  try {
    const response = await axios.put(`/api/portal/mcp/servers/${server.id}`, {
      server_name: server.server_name,
      remark: server.remark || '',
      sse_url: server.sse_url,
      enabled_status: nextStatus,
      scope: props.scope,
    })
    const savedStatus = Number(response.data?.enabled_status ?? nextStatus)
    server.enabled_status = savedStatus
    if (selectedServer.value?.id === server.id) {
      selectedServer.value = { ...selectedServer.value, enabled_status: savedStatus }
    }
    showToast(savedStatus === 1 ? 'MCP 服务已启用' : 'MCP 服务已禁用', 'success')
    return true
  } catch (e: any) {
    showToast(getApiErrorMessage(e, '更新 MCP 服务状态失败'), 'error')
    return false
  } finally {
    statusLoading.value[server.id] = false
  }
}

const fetchServerUsage = async (serverId: string): Promise<McpServerUsage | null> => {
  usageLoading.value[serverId] = true
  try {
    const response = await axios.get(`/api/portal/mcp/servers/${serverId}/usage`)
    return response.data
  } catch (e: any) {
    showToast(getApiErrorMessage(e, '获取 MCP 使用情况失败'), 'error')
    return null
  } finally {
    usageLoading.value[serverId] = false
  }
}

const formatUsageImpact = (usage: McpServerUsage | null, action: '禁用' | '删除') => {
  if (!usage || usage.bound_agent_count === 0) {
    return `${action}后，关联的 MCP 工具将立即不可用。`
  }

  const names = usage.agents
    .slice(0, 5)
    .map(agent => agent.display_name || agent.name)
    .join('、')
  const more = usage.agents.length > 5 ? ` 等 ${usage.agents.length} 个智能体` : ''
  return `${action}后，关联的 MCP 工具将立即不可用。\n受影响智能体：${names}${more}\n其中当前生效：${usage.active_agent_count} 个。`
}

const handleServerStatusChange = async (server: any, enabled: boolean) => {
  if (enabled) {
    await toggleServerStatus(server, true)
    return
  }

  if (statusLoading.value[server.id]) return
  statusLoading.value[server.id] = true
  try {
    const usage = await fetchServerUsage(server.id)
    if (!usage) return
    statusConfirmServer.value = server
    statusConfirmUsage.value = usage
    showStatusConfirm.value = true
  } finally {
    statusLoading.value[server.id] = false
  }
}

const executeStatusChange = async () => {
  if (!statusConfirmServer.value) return
  statusConfirmLoading.value = true
  const success = await toggleServerStatus(statusConfirmServer.value, false)
  statusConfirmLoading.value = false
  if (success) {
    showStatusConfirm.value = false
    statusConfirmServer.value = null
    statusConfirmUsage.value = null
  }
}

const cancelStatusConfirm = () => {
  if (statusConfirmLoading.value) return
  showStatusConfirm.value = false
  statusConfirmServer.value = null
  statusConfirmUsage.value = null
}

const applyMcpJsonPaste = (options?: { connect?: boolean }) => {
  const result = parseMcpServersPaste(mcpJsonPaste.value)
  if (!result.ok) {
    mcpJsonPasteHint.value = result.error
    showToast(result.error, 'warning')
    return false
  }
  const entry = result.entries[0]
  if (!entry) {
    mcpJsonPasteHint.value = '配置中没有可用的 MCP 服务条目'
    showToast(mcpJsonPasteHint.value, 'warning')
    return false
  }
  newServer.value.sse_url = entry.url

  const headerEntries = Object.entries(entry.headers || {})
  if (headerEntries.length) {
    headerMode.value = 'simple'
    headerPairs.value = headerEntries.map(([key, value]) => ({ key, value }))
    newServer.value.auth_headers = JSON.stringify(Object.fromEntries(headerEntries), null, 2)
  } else {
    headerPairs.value = [{ key: '', value: '' }]
    newServer.value.auth_headers = '{}'
  }

  const suggested = suggestMcpNameSuffixFromKey(entry.key)
  if (suggested) {
    serverNameSuffix.value = suggested
    syncFullServerName()
  }

  if (entry.key) {
    newServer.value.remark = `来自配置：${entry.key}${entry.type ? `（${entry.type}）` : ''}`
  }

  mcpJsonPasteHint.value = result.warning
    || `已解析「${entry.key}」→ ${entry.url}`

  if (options?.connect) {
    void handleVerify()
  } else {
    showToast(`已从 JSON 解析：${entry.key}`, 'success')
  }
  return true
}

const handleVerify = async () => {
  if (!newServer.value.sse_url) {
    showToast(connectionInputTab.value === 'json' ? '请先粘贴并解析有效的 MCP JSON' : '请输入服务地址', 'warning')
    return
  }
  
  verifying.value = true
  try {
    const payload: Record<string, unknown> = {
      ...newServer.value,
      ...(isEditing.value ? { server_id: editingId.value } : {}),
    }
    if (isEditing.value && !newServer.value.auth_headers.trim()) {
      delete payload.auth_headers
    }
    const res = await axios.post('/api/portal/mcp/verify', payload)
    discoveredTools.value = res.data.tools
    wizardStep.value = 2
    if (!normalizeMcpServerNameSuffix(serverNameSuffix.value)) {
        try {
            const url = new URL(newServer.value.sse_url)
            let suffix = normalizeMcpServerNameSuffix(url.hostname) || 'server'
            let candidate = composeMcpServerName(props.scope, userInfo.value?.user_name, suffix)
            let counter = 1
            while (servers.value.some((s: any) => s.server_name === candidate && s.id !== editingId.value)) {
                counter++
                candidate = composeMcpServerName(
                  props.scope,
                  userInfo.value?.user_name,
                  `${suffix}-${counter}`,
                )
            }
            serverNameSuffix.value = stripMcpServerNamePrefix(
              candidate,
              props.scope,
              userInfo.value?.user_name,
            )
        } catch {
            serverNameSuffix.value = normalizeMcpServerNameSuffix(
              buildDefaultMcpServerName(props.scope, userInfo.value?.user_name, 'server').replace(
                namePrefix.value,
                '',
              ),
            ) || 'server'
        }
        syncFullServerName()
    }
    showToast('连接成功，已发现工具', 'success')
  } catch (e: any) {
    showToast(getApiErrorMessage(e, '连接失败，请检查地址或认证信息'), 'error')
  } finally {
    verifying.value = false
  }
}

const addServer = async () => {
  syncFullServerName()
  if (!normalizeMcpServerNameSuffix(serverNameSuffix.value)) {
    showToast('请填写服务名称后缀', 'warning')
    return
  }
  if (!newServer.value.server_name || !newServer.value.sse_url) {
    showToast('请填写完整信息', 'warning')
    return
  }
  if (headerMode.value === 'advanced' && !(isEditing.value && !newServer.value.auth_headers.trim())) {
    try { JSON.parse(newServer.value.auth_headers) }
    catch (e) { showToast('JSON 格式错误', 'error'); return }
  }

  try {
    const payload: Record<string, unknown> = { ...newServer.value, scope: props.scope }
    if (isEditing.value && !newServer.value.auth_headers.trim()) {
      delete payload.auth_headers
    }
    if (isEditing.value) {
      await axios.put(`/api/portal/mcp/servers/${editingId.value}`, payload)
      showToast('更新成功', 'success')
    } else {
      await axios.post('/api/portal/mcp/servers', payload)
      showToast('添加成功', 'success')
    }
    showAddModal.value = false
    fetchServers()
    resetWizard()
  } catch (e: any) {
    showToast(getApiErrorMessage(e, '操作失败'), 'error')
  }
}

// Deletion Logic
const showDeleteConfirm = ref(false)
const serverToDelete = ref<string | null>(null)
const deleteServerUsage = ref<McpServerUsage | null>(null)
const deleteLoading = ref(false)

const confirmDeleteServer = async (server: any) => {
  const usage = await fetchServerUsage(server.id)
  if (!usage) return
  serverToDelete.value = server.id
  deleteServerUsage.value = usage
  showDeleteConfirm.value = true
}

const executeDeleteServer = async () => {
  if (!serverToDelete.value) return
  const deletingId = serverToDelete.value
  deleteLoading.value = true
  try {
    await axios.delete(`/api/portal/mcp/servers/${deletingId}`)
    showToast('删除成功', 'success')
    showDeleteConfirm.value = false
    serverToDelete.value = null
    deleteServerUsage.value = null
    fetchServers()
    if (selectedServer.value?.id === deletingId) {
      selectedServer.value = null
      selectedServerUsage.value = null
    }
  } catch (e) {
    showToast(getApiErrorMessage(e, '删除失败'), 'error')
  } finally {
    deleteLoading.value = false
  }
}

const cancelDeleteServer = () => {
  if (deleteLoading.value) return
  showDeleteConfirm.value = false
  serverToDelete.value = null
  deleteServerUsage.value = null
}

const syncTools = async (id: string) => {
  if (syncLoading.value[id]) return
  
  syncLoading.value[id] = true
  try {
    const response = await axios.post(`/api/portal/mcp/servers/${id}/sync`)
    const remoteDeletedCount = Number(response.data?.remote_deleted_count || 0)
    showToast(
      remoteDeletedCount > 0
        ? `同步成功，已标记 ${remoteDeletedCount} 个远端已删除工具`
        : '同步成功',
      'success',
    )
    fetchServers()
    if (selectedServer.value?.id === id) {
        fetchTools(id)
        fetchServerUsage(id).then((usage) => {
          if (selectedServer.value?.id === id) selectedServerUsage.value = usage
        })
    }
  } catch (e: any) {
    showToast(getApiErrorMessage(e, '同步失败'), 'error')
  } finally {
    syncLoading.value[id] = false
  }
}

const fetchTools = async (serverId: string) => {
  toolsLoading.value = true
  try {
    const res = await axios.get(`/api/portal/mcp/servers/${serverId}/tools`)
    tools.value = res.data
  } catch (e) {
    showToast(getApiErrorMessage(e, '获取工具列表失败'), 'error')
  } finally {
    toolsLoading.value = false
  }
}

const selectServer = (server: any) => {
  selectedServer.value = server
  selectedServerUsage.value = null
  selectedToolIds.value = new Set()
  fetchTools(server.id)
  fetchServerUsage(server.id).then((usage) => {
    if (selectedServer.value?.id === server.id) selectedServerUsage.value = usage
  })
}

/** 移动端从工具详情返回服务列表 */
const clearSelectedServer = () => {
  selectedServer.value = null
  selectedServerUsage.value = null
  tools.value = []
  selectedToolIds.value = new Set()
}

const togglePublish = async (tool: any) => {
  if (!canManageTool(tool)) return
  try {
    const newStatus = !tool.is_published
    await axios.put(`/api/portal/mcp/tools/${tool.id}/publish?published=${newStatus}`)
    tool.is_published = newStatus
    showToast(newStatus ? '工具已发布' : '工具已下线', 'success')
    if (selectedServer.value) {
      fetchServerUsage(selectedServer.value.id).then((usage) => {
        if (selectedServer.value) selectedServerUsage.value = usage
      })
    }
  } catch (e) {
    showToast(getApiErrorMessage(e, '操作失败'), 'error')
  }
}

onMounted(fetchServers)
</script>

<template>
  <div class="flex h-full min-h-[28rem] flex-col gap-3 lg:min-h-0 lg:flex-row lg:gap-6">
    <!-- Left: Server List — 移动端选中服务后隐藏，避免左右挤成一条 -->
    <div
      class="flex w-full flex-col overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm lg:w-1/3"
      :class="selectedServer ? 'hidden lg:flex' : 'flex'"
    >
      <!-- Market Guide (High Contrast with Dynamic Scope Theme) -->
      <div 
        class="border-b border-white/10 p-3 text-white transition-colors duration-300 sm:p-4"
        :class="props.scope === 'personal' ? 'bg-slate-950' : 'bg-slate-900'"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <h4 
              class="flex items-center text-sm font-black transition-colors duration-300"
              :class="props.scope === 'personal' ? 'text-emerald-400' : 'text-indigo-400'"
            >
              <ShoppingBagIcon class="mr-1.5 h-4 w-4 shrink-0" />
              探索 MCP 市场
            </h4>
            <p class="mt-1 text-[10px] leading-relaxed text-slate-400 sm:line-clamp-none">
              {{ props.scope === 'personal' ? '去魔搭寻找并接入私有扩展' : '去魔搭寻找更多公共工具集' }}
            </p>
            <div class="mt-2">
              <a 
                href="https://modelscope.cn/mcp" 
                target="_blank" 
                class="inline-flex items-center rounded px-2 py-1 text-[10px] font-bold text-white shadow-sm transition-all duration-200"
                :class="props.scope === 'personal' ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-indigo-600 hover:bg-indigo-500'"
              >
                立即前往市场
                <MagnifyingGlassIcon class="ml-1 h-3 w-3" />
              </a>
            </div>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between gap-2 border-b border-gray-100 bg-gray-50/80 p-3 sm:p-4">
        <div class="flex min-w-0 flex-wrap items-center gap-2">
          <h3 class="text-[11px] font-bold uppercase tracking-wider text-gray-500 sm:text-xs">
            {{ props.scope === 'personal' ? '已连接服务' : '已连接服务 (平台)' }}
          </h3>
          <span v-if="props.scope === 'global' && !canSave" class="rounded border border-amber-200/60 bg-amber-50 px-1.5 py-0.5 text-[10px] font-normal text-amber-600">
            管理员可编辑
          </span>
        </div>
        <button 
          v-if="canSave" 
          @click="resetWizard(); showAddModal = true" 
          class="flex shrink-0 items-center rounded-md px-2.5 py-1.5 text-[11px] font-bold text-white shadow-sm transition-all sm:px-3"
          :class="props.scope === 'personal' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-primary hover:bg-primary-dark'"
        >
          <PlusIcon class="mr-1 h-3.5 w-3.5" />
          添加
        </button>
      </div>

      <div class="custom-scrollbar max-h-[min(52vh,28rem)] flex-1 overflow-y-auto lg:max-h-none">
        <div v-if="loading" class="p-8 text-center">
          <ArrowPathIcon class="mx-auto h-6 w-6 animate-spin text-gray-300" />
        </div>
        <div v-else-if="servers.length === 0" class="p-8 text-center text-sm italic text-gray-400">
          暂无配置 MCP 服务
        </div>
        <div v-else class="divide-y divide-gray-50">
          <div 
            v-for="server in servers" 
            :key="server.id"
            @click="selectServer(server)"
            class="cursor-pointer p-3 transition-all hover:bg-blue-50/30 sm:p-4"
            :class="selectedServer?.id === server.id ? 'border-l-4 border-primary bg-blue-50' : 'border-l-4 border-transparent'"
          >
            <div class="mb-1.5 flex items-start justify-between gap-2">
              <div class="min-w-0 flex-1">
                <span class="block truncate text-sm font-bold text-gray-900">{{ server.server_name }}</span>
                <p v-if="server.remark" class="mt-0.5 line-clamp-2 text-[11px] leading-snug text-gray-500">{{ server.remark }}</p>
              </div>
              <div class="flex shrink-0 items-center gap-2" @click.stop>
                <span
                  class="text-[10px] font-semibold"
                  :class="credentialNeedsAttention(server)
                    ? 'text-red-600'
                    : (server.enabled_status === 1 ? 'text-emerald-600' : 'text-gray-400')"
                >
                  {{ credentialNeedsAttention(server)
                    ? credentialStatusLabel(server)
                    : (server.enabled_status === 1 ? '运行中' : '已禁用') }}
                </span>
                <Switch
                  :model-value="server.enabled_status === 1"
                  :disabled="!canSave || statusLoading[server.id] || credentialNeedsAttention(server)"
                  :loading="statusLoading[server.id]"
                  :aria-label="`${server.server_name}${server.enabled_status === 1 ? '禁用' : '启用'}`"
                  @update:model-value="handleServerStatusChange(server, $event)"
                />
              </div>
            </div>
            <div class="mb-2 flex items-center truncate font-mono text-[10px] text-gray-400">
              <LinkIcon class="mr-1 h-3 w-3 shrink-0" />
              <span class="truncate">{{ server.sse_url }}</span>
            </div>
            <div class="flex flex-wrap items-center justify-between gap-2">
              <span class="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">
                {{ server.tool_count }} 工具 /
                <span v-if="server.enabled_status === 1" class="font-bold text-green-600">{{ server.published_tool_count }} 已发布</span>
                <span v-else class="font-bold text-gray-400">服务已禁用</span>
                <span v-if="server.stale_tool_count > 0" class="ml-1 text-amber-600">{{ server.stale_tool_count }} 个远端已删除</span>
              </span>
              <div class="flex items-center gap-1">
                <span class="mr-1 hidden text-[9px] italic text-gray-400 sm:inline" v-if="server.last_sync_at">同步于 {{ new Date(server.last_sync_at).toLocaleString() }}</span>
                <div v-if="canSave" class="flex space-x-0.5" @click.stop>
                  <button type="button" @click="openEditModal(server)" class="rounded p-1.5 text-gray-400 transition-colors hover:bg-white hover:text-blue-500" title="编辑配置">
                    <PencilSquareIcon class="h-4 w-4" />
                  </button>
                  <button type="button" @click="syncTools(server.id)" :disabled="syncLoading[server.id] || credentialNeedsAttention(server)" class="rounded p-1.5 text-gray-400 transition-colors hover:bg-white hover:text-primary disabled:cursor-not-allowed disabled:opacity-40">
                    <CloudArrowDownIcon class="h-4 w-4" :class="syncLoading[server.id] ? 'animate-bounce' : ''" />
                  </button>
                  <button type="button" @click="confirmDeleteServer(server)" class="rounded p-1.5 text-gray-400 transition-colors hover:bg-white hover:text-red-500">
                    <TrashIcon class="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Right: Tool List — 移动端仅在选中服务后展示 -->
    <div
      class="flex min-h-[22rem] flex-1 flex-col overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm lg:min-h-0"
      :class="selectedServer ? 'flex' : 'hidden lg:flex'"
    >
      <div v-if="!selectedServer" class="flex flex-1 flex-col items-center justify-center text-gray-400">
        <SparklesIcon class="mb-4 h-12 w-12 opacity-20" />
        <p class="text-sm">请在左侧选择一个 MCP 服务查看工具</p>
      </div>
      
      <template v-else>
        <div class="flex flex-col gap-3 border-b border-gray-200 bg-slate-50 p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4">
          <div class="flex min-w-0 items-start gap-2">
            <button
              type="button"
              class="-ml-1 mt-0.5 rounded-md p-1.5 text-gray-500 hover:bg-white hover:text-gray-800 lg:hidden"
              aria-label="返回服务列表"
              @click="clearSelectedServer"
            >
              <ChevronLeftIcon class="h-5 w-5" />
            </button>
            <input 
              v-if="canSave"
              type="checkbox" 
              :checked="isAllSelected" 
              :disabled="!canManageSelectedTools"
              @change="toggleSelectAll"
              class="mr-1 mt-1 h-4 w-4 rounded border-gray-400 text-primary focus:ring-primary sm:mr-2" 
            />
            <div class="min-w-0">
              <h3 class="truncate text-sm font-bold text-slate-800">{{ selectedServer.server_name }} 工具</h3>
              <p class="mt-0.5 text-[10px] text-amber-600" v-if="!isSelectedServerEnabled">服务已禁用，工具暂不可测试、发布或下线</p>
              <p class="mt-0.5 text-[10px] text-slate-500" v-else-if="selectedToolIds.size === 0">发布后的工具智能体才可见</p>
              <p class="mt-0.5 text-[10px] font-black text-primary" v-else>已选中 {{ selectedToolIds.size }} 个项</p>
              <div v-if="selectedServerUsage" class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px]">
                <span class="text-slate-500">绑定 {{ selectedServerUsage.bound_agent_count }} 个智能体</span>
                <span class="text-emerald-600">生效 {{ selectedServerUsage.active_agent_count }} 个</span>
                <span class="text-slate-400">{{ selectedServerUsage.bound_version_count }} 个版本配置</span>
              </div>
              <span v-else-if="usageLoading[selectedServer.id]" class="mt-1 text-[10px] text-slate-400">正在统计使用情况...</span>
            </div>
          </div>
          
          <div class="flex flex-wrap items-center gap-2 pl-8 sm:pl-0 lg:pl-0">
            <div v-if="canSave && selectedToolIds.size > 0" class="flex items-center space-x-2 rounded-lg border border-gray-200 bg-white p-1 shadow-sm animate-fade-in">
              <button @click="batchUpdateStatus(true)" :disabled="!canManageSelectedTools" class="rounded bg-green-600 px-3 py-1 text-[10px] font-bold text-white shadow-sm transition-all hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50">批量发布</button>
              <button @click="batchUpdateStatus(false)" :disabled="!canManageSelectedTools" class="rounded bg-slate-600 px-3 py-1 text-[10px] font-bold text-white shadow-sm transition-all hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50">批量下线</button>
            </div>
            <button v-if="canSave" @click="syncTools(selectedServer.id)" :disabled="syncLoading[selectedServer.id]" class="flex items-center rounded border border-gray-200 bg-white px-2 py-1 text-[11px] font-bold text-primary hover:underline">
              <ArrowPathIcon class="mr-1 h-3.5 w-3.5" :class="syncLoading[selectedServer.id] ? 'animate-spin' : ''" />
              刷新
            </button>
          </div>
        </div>

        <div class="custom-scrollbar flex-1 overflow-y-auto p-3 sm:p-4">
          <div v-if="toolsLoading" class="p-12 text-center">
            <ArrowPathIcon class="mx-auto h-8 w-8 animate-spin text-gray-200" />
          </div>
          <div v-else-if="tools.length === 0" class="p-12 text-center">
            <p class="text-sm text-gray-400">该服务下暂无同步到的工具，请点击同步按钮。</p>
          </div>
          <div v-else class="grid grid-cols-1 gap-3 sm:gap-4">
            <div 
              v-for="tool in tools" 
              :key="tool.id" 
              @click="canManageTool(tool) && toggleSelectTool(tool.id)"
              class="group flex flex-col gap-3 rounded-lg border p-3 transition-all sm:flex-row sm:items-start sm:justify-between sm:p-4"
              :class="[
                canManageTool(tool) ? 'cursor-pointer' : 'cursor-default',
                selectedToolIds.has(tool.id) ? 'border-primary bg-blue-50/50 shadow-sm' : 'border-gray-100 bg-gray-50/30 hover:border-primary/30'
              ]"
            >
              <div class="flex min-w-0 flex-1 items-start pr-0 sm:pr-4">
                <input 
                  v-if="canSave"
                  type="checkbox" 
                  :checked="selectedToolIds.has(tool.id)" 
                  :disabled="!canManageTool(tool)"
                  @click.stop="toggleSelectTool(tool.id)"
                  class="mr-3 mt-1 h-3.5 w-3.5 rounded border-gray-300 text-primary focus:ring-primary" 
                />
                <div class="min-w-0 flex-1">
                  <div class="mb-1 flex flex-wrap items-center gap-1.5">
                    <span class="text-sm font-bold text-gray-900 break-all">{{ tool.tool_name }}</span>
                    <span v-if="tool.usage_count > 0" class="inline-flex items-center rounded bg-blue-100 px-1.5 py-0.5 text-[9px] font-medium text-blue-700" title="被智能体引用次数">
                      <LinkIcon class="mr-0.5 h-3 w-3" />{{ tool.usage_count }}
                    </span>
                    <span v-if="!isSelectedServerEnabled" class="rounded border border-amber-100 bg-amber-50 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-tighter text-amber-600">服务已禁用</span>
                    <span v-else-if="tool.is_available === false" class="rounded border border-amber-100 bg-amber-50 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-tighter text-amber-600">远端已删除</span>
                    <span v-else-if="tool.is_published" class="rounded border border-green-100 bg-green-50 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-tighter text-green-600">已发布</span>
                    <span v-else class="rounded border border-gray-200 bg-gray-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-tighter text-gray-400">待发布</span>
                  </div>
                  <p class="line-clamp-2 text-xs italic leading-relaxed text-gray-500">
                    {{ tool.tool_description || '暂无描述' }}
                  </p>
                  <div class="mt-2 flex flex-wrap gap-1" v-if="tool.parameter_schema">
                    <code class="rounded border bg-white px-1 text-[9px] text-gray-400" v-for="(_, p) in JSON.parse(tool.parameter_schema).properties" :key="p">{{ p }}</code>
                  </div>
                </div>
              </div>
              <div v-if="canSave" class="flex shrink-0 flex-row items-center justify-end gap-2 sm:flex-col sm:items-end sm:space-y-0 sm:gap-2">
                <button 
                  @click.stop="openTester(tool)"
                  :disabled="!canManageTool(tool)"
                  class="flex items-center rounded-md border border-indigo-100 bg-white px-3 py-1.5 text-[11px] font-bold text-indigo-600 shadow-sm transition-colors hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-40 opacity-100 lg:opacity-0 lg:group-hover:opacity-100"
                  title="在线测试"
                >
                  <BeakerIcon class="mr-1.5 h-3.5 w-3.5" />
                  测试
                </button>
                <button 
                  @click.stop="togglePublish(tool)"
                  :disabled="!canManageTool(tool)"
                  class="flex items-center rounded-md border px-3 py-1.5 text-[11px] font-bold shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40 opacity-100 lg:opacity-0 lg:group-hover:opacity-100"
                  :class="tool.is_published ? 'border-gray-200 bg-white text-gray-600 hover:text-red-600' : 'border-transparent bg-primary text-white hover:bg-primary-dark'"
                >
                  <component :is="tool.is_published ? EyeSlashIcon : EyeIcon" class="mr-1.5 h-3.5 w-3.5" />
                  {{ tool.is_published ? '下线' : '发布' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Tool Tester Drawer -->
    <McpToolTester 
      v-if="toolToTest"
      :tool="toolToTest" 
      :is-open="showTester" 
      @close="showTester = false" 
    />

    <!-- Add Server Modal (Connection Wizard) -->
    <div v-if="showAddModal" class="fixed inset-0 z-[60] flex items-end justify-center bg-gray-900/50 p-0 backdrop-blur-sm sm:items-center sm:p-4">
      <div class="flex max-h-[92dvh] w-full max-w-lg flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl animate-fade-in-up sm:rounded-xl">
        <!-- Wizard Header -->
        <div class="shrink-0 border-b border-gray-100 bg-gray-50/50 p-4 sm:p-6">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-bold text-gray-900">
              {{ wizardStep === 1 ? (isEditing ? '编辑配置' : '第一步：建立连接') : '第二步：确认工具并命名' }}
            </h3>
            <div class="flex space-x-1" v-if="!isEditing">
              <div class="w-2 h-2 rounded-full" :class="wizardStep === 1 ? 'bg-primary' : 'bg-gray-200'"></div>
              <div class="w-2 h-2 rounded-full" :class="wizardStep === 2 ? 'bg-primary' : 'bg-gray-200'"></div>
            </div>
          </div>
          <p class="text-xs text-gray-500">
            {{ wizardStep === 1
              ? (connectionInputTab === 'json'
                ? '粘贴 mcpServers JSON，解析后将自动连接并发现工具。'
                : '手动填写服务地址与鉴权，然后连接并发现工具。')
              : `探测成功！共发现 ${discoveredTools.length} 个工具。请检查列表并为该服务命名。` }}
          </p>
        </div>

        <!-- Wizard Step 1: Input -->
        <div v-if="wizardStep === 1" class="flex-1 space-y-5 overflow-y-auto p-4 sm:p-6">
          <div
            v-if="!isEditing"
            class="flex items-center gap-1 rounded-lg bg-gray-100 dark:bg-gray-800 p-0.5"
          >
            <button
              type="button"
              class="flex-1 py-1.5 text-center text-xs font-semibold rounded-md transition-colors"
              :class="connectionInputTab === 'manual'
                ? 'bg-white shadow-sm text-gray-900'
                : 'text-gray-500 hover:text-gray-700'"
              @click="connectionInputTab = 'manual'"
            >
              手动填写
            </button>
            <button
              type="button"
              class="flex-1 py-1.5 text-center text-xs font-semibold rounded-md transition-colors flex items-center justify-center gap-1"
              :class="connectionInputTab === 'json'
                ? 'bg-white shadow-sm text-indigo-700'
                : 'text-gray-500 hover:text-gray-700'"
              @click="connectionInputTab = 'json'"
            >
              <ClipboardDocumentIcon class="w-3.5 h-3.5" />
              JSON 粘贴
            </button>
          </div>

          <!-- JSON 粘贴 Tab -->
          <div v-if="connectionInputTab === 'json' && !isEditing" class="space-y-3">
            <p class="text-[11px] text-gray-500 leading-relaxed">
              支持 Cursor / Claude Desktop 的
              <code class="px-1 bg-gray-100 rounded text-[10px]">mcpServers</code>
              配置（含 streamable_http）。点击下方按钮将解析并直接连接发现工具。
            </p>
            <textarea
              v-model="mcpJsonPaste"
              rows="8"
              placeholder='{ "mcpServers": { "mcp-trends-hub": { "type": "streamable_http", "url": "https://..." } } }'
              class="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg focus:ring-2 focus:ring-primary outline-none font-mono bg-gray-50 text-gray-800"
              @keydown.stop
            />
            <p v-if="mcpJsonPasteHint" class="text-[10px] text-indigo-700 leading-snug">{{ mcpJsonPasteHint }}</p>
            <p v-if="newServer.sse_url" class="text-[10px] text-gray-500 font-mono truncate" :title="newServer.sse_url">
              当前地址：{{ newServer.sse_url }}
            </p>
          </div>

          <!-- 手动填写 Tab（编辑时强制手动） -->
          <template v-else>
            <div>
              <label class="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5 flex items-center">
                <LinkIcon class="w-3 h-3 mr-1" /> 服务地址（SSE / HTTP）
              </label>
              <input v-model="newServer.sse_url" placeholder="https://..." class="w-full px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-primary outline-none font-mono" />
              <p class="text-[10px] text-gray-400 mt-1">支持 MCP SSE 与 streamable HTTP（如 ModelScope）；连接时自动探测协议。</p>
            </div>
          
            <!-- Dynamic Headers Editor -->
            <div>
              <div class="flex justify-between items-center mb-2">
                <label class="block text-xs font-bold text-gray-700 uppercase tracking-wider">身份认证 (可选)</label>
                <button @click="toggleHeaderMode" class="text-[10px] text-primary font-bold flex items-center hover:underline">
                  <component :is="headerMode === 'simple' ? CodeBracketIcon : ListBulletIcon" class="w-3 h-3 mr-1" />
                  切换到{{ headerMode === 'simple' ? '高级 JSON' : '可视化列表' }}
                </button>
              </div>
              <p
                v-if="isEditing && ['migration_pending', 'rotation_required'].includes(editingCredentialStatus)"
                class="mb-3 rounded border border-red-200 bg-red-50 px-2 py-1.5 text-xs text-red-700"
              >
                历史认证信息已隔离，必须重新填写认证 Header 后才能启用或同步该服务。
              </p>
              <p v-else-if="isEditing && existingAuthHeadersConfigured" class="text-xs text-emerald-700 bg-emerald-50 border border-emerald-100 rounded px-2 py-1.5 mb-3">
                已配置认证信息。留空将保留原凭据；填写新值会覆盖，服务端不会回显旧值。
              </p>

              <div v-if="headerMode === 'simple'" class="space-y-3">
                <p class="text-[10px] text-gray-400 leading-relaxed">
                  如果服务需要令牌或 API Key，请添加下方项。
                  <span class="text-primary cursor-pointer hover:underline" @click="markAuthHeadersDirty(); headerPairs[0] = {key: 'Authorization', value: 'Bearer '}">[常用推荐：Authorization]</span>
                </p>
              
                <div class="space-y-2 bg-gray-50 p-3 rounded-lg border border-gray-100 max-h-[150px] overflow-y-auto custom-scrollbar">
                  <div v-for="(pair, index) in headerPairs" :key="index" class="flex gap-2">
                    <div class="flex-1">
                      <input 
                        v-model="pair.key" 
                        @input="markAuthHeadersDirty"
                        placeholder="名称 (如 Authorization)" 
                        class="w-full px-3 py-1.5 text-xs border rounded focus:ring-1 focus:ring-primary outline-none" 
                      />
                    </div>
                    <div class="flex-1">
                      <input 
                        type="password"
                        v-model="pair.value" 
                        @input="markAuthHeadersDirty"
                        :placeholder="pair.key === 'Authorization' ? 'Bearer sk-...' : '内容 (Value)'" 
                        class="w-full px-3 py-1.5 text-xs border rounded focus:ring-1 focus:ring-primary outline-none" 
                      />
                    </div>
                    <button @click="removeHeaderPair(index)" class="p-1.5 text-gray-400 hover:text-red-500">
                      <TrashIcon class="w-4 h-4" />
                    </button>
                  </div>
                  <button @click="addHeaderPair" class="mt-2 text-[10px] font-bold text-primary flex items-center hover:underline">
                    <PlusIcon class="w-3 h-3 mr-1" /> 继续添加
                  </button>
                </div>
              </div>
              <div v-else>
                <textarea v-model="newServer.auth_headers" @input="markAuthHeadersDirty" rows="4" class="w-full px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-primary outline-none font-mono bg-gray-900 text-green-400" placeholder='{}'></textarea>
              </div>
            </div>
          </template>
        </div>

        <!-- Wizard Step 2: Preview -->
        <div v-else class="flex-1 space-y-5 overflow-y-auto p-4 sm:p-6">
          <div>
            <label class="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">服务显示名称</label>
            <div class="flex items-stretch rounded-lg border border-gray-200 overflow-hidden focus-within:ring-2 focus-within:ring-primary/40">
              <span
                class="shrink-0 px-2.5 py-2 text-sm font-mono bg-gray-100 text-gray-500 border-r border-gray-200 select-all"
                :title="namePrefix"
              >{{ namePrefix }}</span>
              <input
                v-model="serverNameSuffix"
                type="text"
                placeholder="自定义后缀，如 hcp"
                class="flex-1 min-w-0 px-3 py-2 text-sm font-mono outline-none"
                @keydown.stop
              />
            </div>
            <p class="mt-1.5 text-[10px] text-gray-400 leading-relaxed">
              完整名称：
              <span class="font-mono text-gray-600">{{ newServer.server_name || `${namePrefix}…` }}</span>
            </p>
          </div>

          <div>
            <label class="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">
              备注
              <span class="ml-1 font-normal text-gray-400 normal-case tracking-normal">选填</span>
            </label>
            <textarea
              v-model="newServer.remark"
              rows="2"
              maxlength="500"
              placeholder="简要说明该 MCP 的用途，便于在挂载与列表中识别"
              class="w-full px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-primary outline-none resize-none"
            />
          </div>
          
          <div>
            <label class="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-2">发现的工具预览</label>
            <div class="bg-gray-50 rounded-lg border border-gray-100 max-h-[250px] overflow-y-auto divide-y divide-gray-200 custom-scrollbar">
              <div v-for="tool in discoveredTools" :key="tool.name" class="p-3">
                <div class="text-xs font-bold text-gray-800">{{ tool.name }}</div>
                <div class="text-[10px] text-gray-500 line-clamp-1 italic">{{ tool.description || '无描述' }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Wizard Footer -->
        <div class="flex shrink-0 flex-col-reverse gap-3 border-t border-gray-100 bg-gray-50 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-6">
          <button @click="showAddModal = false" class="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700">取消</button>
          
          <div class="flex flex-col gap-2 sm:flex-row sm:space-x-3 sm:gap-0">
            <button v-if="wizardStep === 2" @click="wizardStep = 1" class="px-4 py-2 text-sm font-medium text-primary hover:underline">返回修改</button>
            
            <button 
              v-if="wizardStep === 1 && connectionInputTab === 'json' && !isEditing"
              @click="applyMcpJsonPaste({ connect: true })" 
              :disabled="verifying"
              class="flex items-center justify-center rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-bold text-white shadow-lg shadow-indigo-600/20 transition-all hover:bg-indigo-700 disabled:opacity-50 sm:px-6 sm:py-2"
            >
              <ArrowPathIcon v-if="verifying" class="mr-2 h-4 w-4 animate-spin" />
              {{ verifying ? '正在连接并发现工具...' : '解析并连接发现工具' }}
            </button>

            <button 
              v-else-if="wizardStep === 1"
              @click="handleVerify" 
              :disabled="verifying"
              class="flex items-center justify-center rounded-lg bg-primary px-4 py-2.5 text-sm font-bold text-white shadow-lg shadow-primary/20 transition-all hover:bg-primary-dark disabled:opacity-50 sm:px-6 sm:py-2"
            >
              <ArrowPathIcon v-if="verifying" class="mr-2 h-4 w-4 animate-spin" />
              {{ verifying ? '正在尝试建立连接...' : '连接并发现工具' }}
            </button>
            
            <button 
              v-else
              @click="addServer" 
              class="rounded-lg bg-green-600 px-4 py-2.5 text-sm font-bold text-white shadow-lg shadow-green-600/20 transition-all hover:bg-green-700 active:scale-95 sm:px-6 sm:py-2"
            >
              {{ isEditing ? '保存修改' : '确认并完成添加' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation -->
    <ConfirmModal 
      v-if="showDeleteConfirm"
      title="删除 MCP 服务"
      :message="`确定要删除该服务及其缓存的所有工具吗？此操作不可恢复。\n${formatUsageImpact(deleteServerUsage, '删除')}`"
      type="danger"
      :loading="deleteLoading"
      @confirm="executeDeleteServer"
      @cancel="cancelDeleteServer"
    />

    <ConfirmModal
      v-if="showStatusConfirm"
      title="禁用 MCP 服务"
      :message="formatUsageImpact(statusConfirmUsage, '禁用')"
      type="warning"
      confirm-text="确认禁用"
      :loading="statusConfirmLoading"
      @confirm="executeStatusChange"
      @cancel="cancelStatusConfirm"
    />
  </div>
</template>

<style scoped>
.animate-fade-in-up { animation: fadeInUp 0.3s ease-out; }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #e5e7eb; border-radius: 4px; }
</style>
