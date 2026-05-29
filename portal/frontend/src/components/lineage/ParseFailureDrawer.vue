<script setup lang="ts">
import { ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { getColumnParseFailures } from '../../api'
import type { ColumnParseFailureItem } from '../../api'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'open-manual'): void
  (e: 'changed'): void
}>()

const items = ref<ColumnParseFailureItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await getColumnParseFailures({ page: page.value, page_size: pageSize })
    items.value = res.items || []
    total.value = res.total || 0
  } catch {
    items.value = []
    total.value = 0
  }
  loading.value = false
}

watch(() => props.visible, (v) => { if (v) { page.value = 1; load() } })

function onPage(p: number) { page.value = p; load() }
function onClose() { emit('update:visible', false) }
function onManual() { emit('open-manual') }
</script>

<template>
  <a-drawer
    :visible="visible"
    title="字段血缘 — 未解析清单"
    width="640"
    :footer="false"
    @cancel="onClose"
  >
    <div class="drawer-toolbar">
      <span class="text-muted">共 {{ total }} 条解析失败记录</span>
      <a-button size="small" type="primary" @click="onManual">手工补登</a-button>
    </div>

    <a-list :loading="loading" :bordered="false">
      <a-list-item v-for="it in items" :key="it.id">
        <div class="failure-item">
          <div class="failure-item__head">
            <a-tag color="red" size="small">{{ it.entity_type }}#{{ it.entity_id }}</a-tag>
            <span class="failure-item__name">{{ it.entity_name }}</span>
            <span class="failure-item__time">{{ it.created_at }}</span>
          </div>
          <div v-if="it.sql_snippet" class="failure-item__sql">{{ it.sql_snippet }}</div>
          <div class="failure-item__error">{{ it.error_msg }}</div>
        </div>
      </a-list-item>
      <template #empty>
        <div class="empty">暂无解析失败记录 🎉</div>
      </template>
    </a-list>

    <a-pagination
      v-if="total > pageSize"
      :total="total"
      :current="page"
      :page-size="pageSize"
      simple
      @change="onPage"
      style="margin-top: 16px; text-align: center"
    />
  </a-drawer>
</template>

<style scoped>
.drawer-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--color-border);
  margin-bottom: var(--space-3);
}
.text-muted { color: var(--color-text-tertiary); font-size: var(--font-size-xs); }
.failure-item { width: 100%; }
.failure-item__head {
  display: flex; align-items: center; gap: var(--space-2);
  margin-bottom: var(--space-1);
}
.failure-item__name { font-weight: var(--font-weight-semibold); flex: 1; }
.failure-item__time { color: var(--color-text-tertiary); font-size: 11px; }
.failure-item__sql {
  font-family: monospace;
  font-size: 11px;
  background: var(--color-bg-elevated);
  padding: 6px 8px;
  border-radius: 4px;
  margin-bottom: var(--space-1);
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}
.failure-item__error {
  color: var(--color-danger);
  font-size: var(--font-size-xs);
}
.empty {
  padding: 60px 0;
  text-align: center;
  color: var(--color-text-tertiary);
}
</style>
