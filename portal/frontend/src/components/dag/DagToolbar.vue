<script setup lang="ts">
defineProps<{ workflowName: string; status: string }>()
const emit = defineEmits<{
  (e: 'save'): void
  (e: 'test'): void
  (e: 'publish'): void
  (e: 'run'): void
  (e: 'back'): void
  (e: 'autoLayout'): void
  (e: 'versions'): void
}>()

const statusMap: Record<string, { text: string; color: string }> = {
  draft: { text: '草稿', color: '#86909c' },
  tested: { text: '已测试', color: '#ff7d00' },
  online: { text: '已上线', color: '#00b42a' },
  offline: { text: '已下线', color: '#f53f3f' },
}
</script>

<template>
  <div class="dag-toolbar">
    <div class="dag-toolbar__left">
      <button class="dag-toolbar__btn dag-toolbar__btn--back" @click="emit('back')">
        &larr; 返回
      </button>
      <span class="dag-toolbar__name">{{ workflowName || '未命名工作流' }}</span>
      <span class="dag-toolbar__status" :style="{ color: statusMap[status]?.color }">
        {{ statusMap[status]?.text || status }}
      </span>
    </div>
    <div class="dag-toolbar__right">
      <button class="dag-toolbar__btn" @click="emit('versions')">版本</button>
      <button class="dag-toolbar__btn" @click="emit('autoLayout')">自动布局</button>
      <button class="dag-toolbar__btn" @click="emit('save')">保存</button>
      <button class="dag-toolbar__btn" @click="emit('test')">测试</button>
      <button class="dag-toolbar__btn dag-toolbar__btn--primary" @click="emit('publish')">发布</button>
      <button class="dag-toolbar__btn" @click="emit('run')">运行</button>
    </div>
  </div>
</template>

<style scoped>
.dag-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 8px 16px; border-bottom: 1px solid #e5e7eb; background: #fff; }
.dag-toolbar__left { display: flex; align-items: center; gap: 12px; }
.dag-toolbar__right { display: flex; align-items: center; gap: 8px; }
.dag-toolbar__name { font-size: 15px; font-weight: 600; }
.dag-toolbar__status { font-size: 12px; }
.dag-toolbar__btn { padding: 6px 14px; border: 1px solid #d9d9d9; border-radius: 4px; background: #fff; font-size: 13px; cursor: pointer; transition: all 0.15s; }
.dag-toolbar__btn:hover { border-color: #165dff; color: #165dff; }
.dag-toolbar__btn--primary { background: #165dff; color: #fff; border-color: #165dff; }
.dag-toolbar__btn--primary:hover { background: #4080ff; }
.dag-toolbar__btn--back { border: none; color: #666; }
.dag-toolbar__btn--back:hover { color: #165dff; }
</style>
