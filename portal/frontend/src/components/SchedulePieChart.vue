<template>
  <div ref="chartRef" class="pie-chart-container"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import * as echarts from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GraphicComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([PieChart, TooltipComponent, LegendComponent, GraphicComponent, CanvasRenderer])

interface ChartItem {
  name: string
  value: number
  color: string
}

const props = defineProps<{ data: ChartItem[] }>()

const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

const total = computed(() => props.data.reduce((s, d) => s + d.value, 0))
const isEmpty = computed(() => total.value === 0)

function buildOption() {
  const seriesData = isEmpty.value
    ? [{ value: 1, name: '暂无数据', itemStyle: { color: '#E5E8ED' } }]
    : props.data
        .filter(d => d.value > 0)
        .map(d => ({
          value: d.value,
          name: d.name,
          itemStyle: { color: d.color },
        }))

  return {
    tooltip: isEmpty.value
      ? { show: false }
      : {
          trigger: 'item' as const,
          backgroundColor: 'rgba(255,255,255,0.96)',
          borderColor: '#E2E8F0',
          borderWidth: 1,
          padding: [8, 12],
          textStyle: { color: '#0F172A', fontSize: 13 },
          formatter: (p: any) => {
            const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color};margin-right:6px;"></span>`
            return `${dot}${p.name}<br/><b style="font-size:16px;margin-left:14px;">${p.value}</b> <span style="color:#94A3B8">(${p.percent}%)</span>`
          },
        },
    legend: {
      show: false,
    },
    series: [
      {
        type: 'pie',
        radius: ['52%', '72%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: false,
        padAngle: isEmpty.value ? 0 : 2,
        itemStyle: {
          borderRadius: isEmpty.value ? 0 : 6,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: { show: false },
        emphasis: isEmpty.value
          ? { disabled: true }
          : {
              scale: true,
              scaleSize: 6,
              label: {
                show: true,
                fontSize: 13,
                fontWeight: 600,
                color: '#0F172A',
                formatter: '{b}\n{d}%',
              },
            },
        animationType: 'scale',
        animationEasing: 'cubicOut',
        animationDuration: 600,
        data: seriesData,
      },
    ],
    graphic: [
      {
        type: 'text',
        left: 'center',
        top: '42%',
        style: {
          text: isEmpty.value ? '-' : String(total.value),
          textAlign: 'center',
          fontSize: 26,
          fontWeight: 700,
          fill: '#0F172A',
          fontFamily: '-apple-system, BlinkMacSystemFont, PingFang SC, sans-serif',
        },
      },
      {
        type: 'text',
        left: 'center',
        top: '55%',
        style: {
          text: isEmpty.value ? '暂无数据' : '总执行',
          textAlign: 'center',
          fontSize: 12,
          fill: '#94A3B8',
          fontFamily: '-apple-system, BlinkMacSystemFont, PingFang SC, sans-serif',
        },
      },
    ],
  }
}

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  chart.setOption(buildOption())
}

watch(
  () => props.data,
  () => {
    if (chart) {
      chart.setOption(buildOption(), true)
    }
  },
  { deep: true },
)

onMounted(() => {
  initChart()
  if (chartRef.value) {
    observer = new ResizeObserver(() => {
      chart?.resize()
    })
    observer.observe(chartRef.value)
  }
})

onUnmounted(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.pie-chart-container {
  width: 100%;
  height: 260px;
  min-height: 200px;
}
</style>
