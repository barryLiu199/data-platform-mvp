import { ref, onMounted, onUnmounted } from 'vue'

/**
 * 可拖拽面板宽度 composable
 * @param storageKey localStorage 持久化 key
 * @param defaultWidth 默认宽度
 * @param minWidth 最小宽度
 * @param maxWidth 最大宽度
 */
export function useResizePanel(
  storageKey: string,
  defaultWidth = 280,
  minWidth = 180,
  maxWidth = 480
) {
  const saved = localStorage.getItem(storageKey)
  const width = ref(saved ? Math.max(minWidth, Math.min(maxWidth, Number(saved))) : defaultWidth)
  const dragging = ref(false)

  let startX = 0
  let startW = 0

  function onMouseDown(e: MouseEvent) {
    e.preventDefault()
    dragging.value = true
    startX = e.clientX
    startW = width.value
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  function onMouseMove(e: MouseEvent) {
    const delta = e.clientX - startX
    width.value = Math.max(minWidth, Math.min(maxWidth, startW + delta))
  }

  function onMouseUp() {
    dragging.value = false
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    localStorage.setItem(storageKey, String(width.value))
  }

  onUnmounted(() => {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  })

  return { width, dragging, onMouseDown }
}
