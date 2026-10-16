import { doms, isDomAvailable } from './doms.js'
import { DefaultWWWL } from './wwwl.js'
import { updateZoom } from './zoom-pan.js'

// ===================== 图像反相功能 =====================
function initInvertImage() {
  const invertBtn = doms.invertBtn
  if (!invertBtn) {
    console.warn('️ 反相按钮未找到')
    return
  }

  // 完全按照你抄袭的源代码写法 - 使用 onclick 而不是 addEventListener
  invertBtn.onclick = () => {
    if (!window.cornerstone || !isDomAvailable(doms.root)) return
    const viewport = cornerstone.getViewport(doms.root)
    if (!viewport) return

    viewport.invert = !viewport.invert
    cornerstone.setViewport(doms.root, viewport)
    console.log(` 图像反相：${viewport.invert ? '开启' : '关闭'}`)
  }

  console.log(' 反相功能初始化完成')
}

// ===================== 重置按钮初始化 =====================
function initResetImage() {
  const resetBtn = doms.resetBtn
  if (!resetBtn) {
    console.warn('️ 重置按钮未找到')
    return
  }

  // 完全按照你抄袭的源代码写法 - 使用 onclick 而不是 addEventListener
  resetBtn.onclick = () => {
    console.log(' 执行完整重置')
    
    // . 重置预设选择
    if (doms.presetWWWL) doms.presetWWWL.selectedIndex = -
    
    // . 重置窗宽窗位显示
    if (window.initWWWLDisplay) {
      window.initWWWLDisplay()
    }
    
    // . 重置缩放
    updateZoom()
    
    // . 使用 cornerstone 内置的重置功能
    if (window.cornerstone && isDomAvailable(doms.root)) {
      cornerstone.reset(doms.root)
    }
    
    // . 重置超分UI状态
    if (doms.srLoading) doms.srLoading.style.display = 'none'
    if (doms.srDone) doms.srDone.style.display = 'none'
    if (doms.srBtn) doms.srBtn.disabled = false

    console.log(' 完整重置完成')
  }

  console.log(' 重置功能初始化完成')
}

// ===================== 统一初始化 =====================
function initOtherFunctions() {
  initInvertImage()
  initResetImage()
}

export function initOther() {
  initOtherFunctions()
}

// ===================== 全局重置函数（供外部调用） =====================
window.forceResetDisplay = function () {
  // 兼容窗宽窗位模块，正确传参
  if (window.setWWWL) {
    window.setWWWL(DefaultWWWL.ww, DefaultWWWL.wl)
  }
  console.log(' 全局图像显示重置完成')
}
