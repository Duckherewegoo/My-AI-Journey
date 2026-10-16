// UI扩展功能模块 - 修复版（无重复弹窗、精简核心功能）
console.log(' 加载UI扩展功能...');

//  核心修复：初始化锁，杜绝重复绑定（解决弹窗次的BUG）
let uiExtrasInitialized = false;

// 自动初始化（安全单次执行）
document.addEventListener('DOMContentLoaded', () => {
  if (!uiExtrasInitialized) initUIExtras();
});

// ===================== 初始化入口（仅执行次） =====================
function initUIExtras() {
  if (uiExtrasInitialized) return;
  console.log(' 初始化UI扩展功能...');
  
  initDetailToggle();
  initToolButtons();
  
  uiExtrasInitialized = true;
  console.log(' UI扩展功能初始化完成');
}

// ===================== 详细信息切换 =====================
function initDetailToggle() {
  const toggleBtn = document.getElementById('show-more-info');
  const detailPanel = document.getElementById('detail-info');
  if (!toggleBtn || !detailPanel) return;

  //  修复：先移除旧事件，再绑定新事件
  toggleBtn.replaceWith(toggleBtn.cloneNode(true));
  const newBtn = document.getElementById('show-more-info');
  newBtn.addEventListener('click', (e) => {
    e.preventDefault();
    const isHidden = detailPanel.style.display === 'none';
    detailPanel.style.display = isHidden ? 'block' : 'none';
    newBtn.textContent = isHidden ? '[隐藏详细信息]' : '[显示更多信息]';
  });
}

// ===================== 工具按钮绑定 =====================
function initToolButtons() {
  // 强制重置按钮
  const forceResetBtn = document.getElementById('forceReset');
  if (forceResetBtn) {
    forceResetBtn.replaceWith(forceResetBtn.cloneNode(true));
    document.getElementById('forceReset').addEventListener('click', () => {
      console.log(' 触发强制重置');
      window.cleanReset?.() ?? location.reload();
    });
  }

  // 诊断按钮（核心修复：仅绑定次事件）
  const diagnoseBtn = document.getElementById('diagnoseBtn');
  if (diagnoseBtn) {
    diagnoseBtn.replaceWith(diagnoseBtn.cloneNode(true));
    const newDiagnoseBtn = document.getElementById('diagnoseBtn');
    newDiagnoseBtn.addEventListener('click', () => {
      console.log(' 触发系统诊断');
      window.diagnoseViewport?.() ?? defaultDiagnose();
    });
  }
}

// ===================== 默认诊断功能 =====================
function defaultDiagnose() {
  console.log('===  系统诊断信息 ===');
  // 库状态检查
  console.log('库状态:', {
    cornerstone: !!window.cornerstone,
    cornerstoneWADOImageLoader: !!window.cornerstoneWADOImageLoader,
    dicomParser: !!window.dicomParser
  });

  // DOM检查
  console.log('关键DOM:', {
    imageDisplay: !!document.getElementById('image-display'),
    srBtn: !!document.getElementById('sr-btn'),
    wwInput: !!document.getElementById('ww-input'),
    wlInput: !!document.getElementById('wl-input')
  });

  showDiagnosticResult();
}

// ===================== 诊断结果弹窗 =====================
function showDiagnosticResult() {
  const info = `
库状态:
- cornerstone: ${!!window.cornerstone ? ' 已加载' : ' 未加载'}
- DICOM加载器: ${!!window.cornerstoneWADOImageLoader ? ' 已加载' : ' 未加载'}

全局状态: ${window._ctsr ? ' 正常' : ' 异常'}
  `;
  alert('诊断信息已输出到控制台\n\n' + info);
}

// ===================== 全局重置函数 =====================
window.cleanReset = function () {
  console.log(' 执行清理重置...');
  const element = document.getElementById('image-display');
  
  // 重置Cornerstone
  if (element) window.cornerstone?.reset(element);
  
  // 重置全局状态
  if (window._ctsr) {
    window._ctsr.fileOpened = false;
    window._ctsr.currentImage = null;
  }

  // 重置文件输入
  const fileInput = document.getElementById('openDicom');
  if (fileInput) fileInput.value = '';

  resetInfoDisplay();
  showNotification('系统已重置', 'success');
  console.log(' 清理重置完成');
};

// ===================== 全局视口诊断 =====================
window.diagnoseViewport = function () {
  const element = document.getElementById('image-display');
  if (!element || !window.cornerstone) {
    alert(!element ? '图像显示元素未找到' : 'Cornerstone未加载');
    return;
  }

  try {
    const viewport = cornerstone.getViewport(element);
    alert(`视口诊断:
缩放: ${viewport.scale.toFixed()}
窗宽: ${viewport.voi?.windowWidth || 'N/A'}
窗位: ${viewport.voi?.windowCenter || 'N/A'}`);
  } catch (err) {
    alert('视口诊断失败: ' + err.message);
  }
};

// ===================== 重置信息面板 =====================
function resetInfoDisplay() {
  const elements = {
    'info-filename': 'N/A', 'info-type': 'N/A', 'info-h': 'N/A', 'info-w': 'N/A'
  };
  Object.keys(elements).forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = elements[id];
  });

  const detail = document.getElementById('detail-info');
  const toggle = document.getElementById('show-more-info');
  if (detail) detail.style.display = 'none';
  if (toggle) toggle.textContent = '[显示更多信息]';
}

// ===================== 全局通知提示 =====================
function showNotification(message, type = 'info', duration = ) {
  document.getElementById('ui-extras-notification')?.remove();
  const notify = document.createElement('div');
  notify.id = 'ui-extras-notification';
  notify.style.cssText = `
    position: fixed;top:px;right:px;padding:px px;
    border-radius:px;color:white;z-index:;
    background: ${type === 'success' ? 'caf' : type === 'error' ? 'f' : 'f'};
  `;
  notify.textContent = message;
  document.body.appendChild(notify);
  setTimeout(() => notify.remove(), duration);
}

// ===================== 全局API =====================
window.uiExtras = {
  init: initUIExtras,
  showNotification
};

console.log(' UI扩展功能加载完成');
