// 图像缩放与平移模块 - 修复版（无重复事件、无卡顿、无泄漏）
import { doms, isDomAvailable } from './doms.js'

// 全局缩放配置
const zoomState = {
  currentZoom: .,
  maxZoom: .,
  minZoom: .,
  zoomStep: .
}

//  核心：初始化锁，杜绝重复执行
let zoomPanInitialized = false

// ===================== 缩放状态更新 =====================
export function updateZoom(zoom) {
  const validZoom = isNaN(+zoom) || zoom == null ? . : +zoom
  zoomState.currentZoom = Math.max(zoomState.minZoom, Math.min(zoomState.maxZoom, validZoom))

  // 同步全局状态
  window._ctsr ||= {}
  window._ctsr.zoom = zoomState.currentZoom

  // 同步UI显示
  const zoomEl = doms.currentZoomRate
  if (zoomEl) zoomEl.textContent = zoomState.currentZoom.toFixed()
}

// ===================== 缩放核心处理 =====================
function handleZoom(direction) {
  if (!window.cornerstone || !isDomAvailable(doms.root)) return

  try {
    const viewport = cornerstone.getViewport(doms.root)
    if (!viewport) return

    let newScale = viewport.scale || .
    newScale += direction === 'in' ? zoomState.zoomStep : -zoomState.zoomStep
    newScale = Math.max(zoomState.minZoom, Math.min(zoomState.maxZoom, newScale))

    viewport.scale = newScale
    cornerstone.setViewport(doms.root, viewport)
    updateZoom(newScale)
  } catch (error) {
    console.error(` 缩放失败:`, error)
  }
}

// ===================== 缩放按钮 + 滚轮 =====================
function enableZooming() {
  const zoomInBtn = doms.zoomIn
  const zoomOutBtn = doms.zoomOut
  const rootEl = doms.root

  // 放大按钮（先克隆清空旧事件，再绑定）
  if (zoomInBtn) {
    zoomInBtn.replaceWith(zoomInBtn.cloneNode(true))
    document.getElementById('zoomIn-btn').addEventListener('click', () => handleZoom('in'))
    console.log(' 放大按钮已绑定')
  }
  // 缩小按钮
  if (zoomOutBtn) {
    zoomOutBtn.replaceWith(zoomOutBtn.cloneNode(true))
    document.getElementById('zoomOut-btn').addEventListener('click', () => handleZoom('out'))
    console.log(' 缩小按钮已绑定')
  }
  // 鼠标滚轮缩放
  if (rootEl) {
    rootEl.addEventListener('wheel', (e) => {
      e.preventDefault()
      handleZoom(e.deltaY <  ? 'in' : 'out')
    }, { passive: false })
  }
}

// ===================== 拖拽平移功能 =====================
function enablePanning() {
  const rootEl = doms.root
  if (!rootEl || !window.cornerstone) return

  let isDragging = false
  let lastX = 
  let lastY = 

  rootEl.addEventListener('mousedown', (e) => {
    if (e.button !== ) return
    e.preventDefault()
    e.stopPropagation()

    const rect = rootEl.getBoundingClientRect()
    lastX = e.clientX - rect.left
    lastY = e.clientY - rect.top
    isDragging = true

    const mouseMoveHandler = (e) => {
      if (!isDragging) return
      const rect = rootEl.getBoundingClientRect()
      const currentX = e.clientX - rect.left
      const currentY = e.clientY - rect.top

      const deltaX = currentX - lastX
      const deltaY = currentY - lastY
      lastX = currentX
      lastY = currentY

      try {
        const viewport = cornerstone.getViewport(rootEl)
        if (!viewport) return
        viewport.translation ||= { x: , y:  }
        const scale = viewport.scale || .
        viewport.translation.x += deltaX / scale
        viewport.translation.y += deltaY / scale
        cornerstone.setViewport(rootEl, viewport)
      } catch (err) {
        console.error(' 平移失败:', err)
      }
    }

    const endDrag = () => {
      isDragging = false
      // 安全移除事件
      document.removeEventListener('mousemove', mouseMoveHandler)
      document.removeEventListener('mouseup', endDrag)
      document.removeEventListener('mouseleave', endDrag)
    }

    document.addEventListener('mousemove', mouseMoveHandler)
    document.addEventListener('mouseup', endDrag)
    document.addEventListener('mouseleave', endDrag)
  })
}

// ===================== 键盘快捷键 =====================
function initKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    if (['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return
    if (e.ctrlKey && (e.key === '+' || e.key === '=')) {
      e.preventDefault()
      handleZoom('in')
    }
    if (e.ctrlKey && e.key === '-') {
      e.preventDefault()
      handleZoom('out')
    }
  })
}

// ===================== 模块初始化（仅执行次） =====================
export function initZoomPanModule() {
  // 锁死：只初始化一次
  if (zoomPanInitialized) return
  if (!doms.root) {
    console.error(' 图像显示元素未找到')
    return
  }

  enableZooming()
  enablePanning()
  initKeyboardShortcuts()
  updateZoom(.)
  
  zoomPanInitialized = true
  console.log(' 缩放平移模块初始化完成')
}

// =====================  核心修复：删除自动初始化！ =====================
// 原代码的自动启动会和主调度器冲突，已彻底删除
