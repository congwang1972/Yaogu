import * as echarts from 'echarts'

export const CHART_THEME = 'yaogu-dark'
export const CHART_UP = '#FF4D4F'
export const CHART_DOWN = '#16C784'

// 主题注册必须在首次渲染图表前完成，因此在模块加载时执行一次。
echarts.registerTheme(CHART_THEME, {
  backgroundColor: 'transparent',
  textStyle: { color: '#8B93A7', fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif' },
  axisPointer: { lineStyle: { color: '#4A5163' }, crossStyle: { color: '#4A5163' } },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#2A3040' } },
    axisTick: { show: false },
    axisLabel: { color: '#8B93A7', fontSize: 11 },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: '#8B93A7', fontSize: 11 },
    splitLine: { lineStyle: { color: '#1F2430', type: 'dashed' } },
  },
  tooltip: {
    backgroundColor: '#1B2130',
    borderColor: '#2A3040',
    textStyle: { color: '#E6EAF2', fontSize: 12 },
  },
})
