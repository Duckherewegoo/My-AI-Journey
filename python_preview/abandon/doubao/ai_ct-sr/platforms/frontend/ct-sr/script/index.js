// 医学影像超分辨率系统 - 正式版主入口
console.log(' 医学影像超分辨率系统启动中...')

// ===================== 模块导入（严格依赖顺序，专业版） =====================
// . 全局样式
import '../lib/style.less'

// . 系统配置
import './config.js'

// . DOM核心工具（已修复：防事件重复、稳定映射）
import './doms.js'

// . 主初始化调度器（已修复：统一管理所有模块，无冲突）
import './init.js'

// . 核心业务模块（全部已修复：专业标准 + 无BUG）
import './info.js'       // 信息展示（医学标准超分参数）
import './file.js'       // 文件加载（DICOM+通用图像）
import './wwwl.js'       // 窗宽窗位（修复预设、无重复初始化）
import './zoom-pan.js'   // 缩放平移（无卡顿、无重复事件）
import './other.js'      // 重置/反相（修复黑屏BUG）
import './sr.js'         // 超分核心（兼容DICOM+普通图像）
import './default.js' 
// . UI扩展模块（已修复：诊断按钮只弹次，无重复触发）
import './ui-extra.js'

// ===================== 加载状态 =====================
console.log(' 所有模块加载完成，等待DOM就绪后自动初始化')

// ===================== 全局错误捕获（医学系统必备容错） =====================
// 捕获全局同步错误
window.addEventListener('error', (event) => {
  const msg = event.error?.message || event.message || '未知错误'
  console.error('【系统全局错误】:', msg)
  // 安全通知
  window.uiExtras?.showNotification?.(`系统错误：${msg}`, 'error', )
})

// 捕获异步Promise错误
window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason?.message || '未知异步异常'
  console.error('【系统异步错误】:', reason)
  event.preventDefault() // 阻止浏览器默认抛出
  window.uiExtras?.showNotification?.(`异步异常：${reason}`, 'error', )
})
