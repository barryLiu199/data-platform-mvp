<script setup lang="ts">
import { ref } from 'vue'

const visible = ref(false)
const position = ref({ x: 0, y: 0 })
const nodeId = ref<string | null>(null)
const isSkipped = ref(false)

const emit = defineEmits<{
  (e: 'skip', id: string): void
  (e: 'unskip', id: string): void
  (e: 'delete', id: string): void
  (e: 'config', id: string): void
}>()

function show(event: MouseEvent, id: string, skip: boolean) {
  event.preventDefault()
  nodeId.value = id
  isSkipped.value = skip
  position.value = { x: event.clientX, y: event.clientY }
  visible.value = true
  document.addEventListener('click', hide, { once: true })
}

function hide() { visible.value = false }

function toggleSkip() {
  if (!nodeId.value) return
  if (isSkipped.value) emit('unskip', nodeId.value)
  else emit('skip', nodeId.value)
  hide()
}

function deleteNode() {
  if (!nodeId.value) return
  emit('delete', nodeId.value)
  hide()
}

function openConfig() {
  if (!nodeId.value) return
  emit('config', nodeId.value)
  hide()
}

defineExpose({ show })
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="ctx-menu" :style="{ left: position.x + 'px', top: position.y + 'px' }">
      <div class="ctx-menu__item" @click="openConfig">
        节点配置
      </div>
      <div class="ctx-menu__item" @click="toggleSkip">
        {{ isSkipped ? '取消跳过' : '跳过节点' }}
      </div>
      <div class="ctx-menu__item ctx-menu__item--danger" @click="deleteNode">
        删除节点
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ctx-menu { position: fixed; z-index: 9999; background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.12); min-width: 120px; padding: 4px 0; }
.ctx-menu__item { padding: 8px 16px; font-size: 13px; cursor: pointer; transition: background 0.15s; }
.ctx-menu__item:hover { background: #f0f5ff; }
.ctx-menu__item--danger { color: #ef4444; }
.ctx-menu__item--danger:hover { background: #fef2f2; }
</style>
