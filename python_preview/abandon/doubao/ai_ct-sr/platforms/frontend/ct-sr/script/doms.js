/
  DOM工具类（修复版：杜绝事件重复绑定、增强稳定性）
 /
export const doms = {
  root: null,
  wwInput: null,
  wlInput: null,
  applyWWWL: null,
  presetWWWL: null,
  openDicom: null,
  srBtn: null,
  remoteStatus: null,
  remoteIP: null,
  invertBtn: null,
  resetBtn: null,
  srReplace: null,
  srLoading: null,
  srDone: null,
  currentZoomRate: null,
  zoomIn: null,
  zoomOut: null,
  forceReset: null,
  diagnoseBtn: null,
  toggleRgbModeBtn: null
};

/
  判断DOM元素是否有效
 /
export function isDomAvailable(element) {
  if (!element) return false;
  return element instanceof HTMLElement;
}

/
  根据ID获取DOM元素
 /
export function getDOMElement(id) {
  if (!id || typeof id !== 'string') {
    console.warn('无效DOM ID:', id);
    return null;
  }
  try {
    return document.getElementById(id);
  } catch (error) {
    console.error(`获取DOM失败 [${id}]:`, error);
    return null;
  }
}

/
  等待DOM元素加载完成（稳定版）
 /
export function waitForElement(id, timeout = ) {
  return new Promise((resolve, reject) => {
    const el = getDOMElement(id);
    if (isDomAvailable(el)) {
      resolve(el);
      return;
    }

    const observer = new MutationObserver((mutations, obs) => {
      const target = getDOMElement(id);
      if (isDomAvailable(target)) {
        obs.disconnect();
        resolve(target);
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });

    setTimeout(() => {
      observer.disconnect();
      reject(new Error(`等待DOM超时 [${id}]`));
    }, timeout);
  });
}

/
  初始化所有DOM映射（容错增强）
 /
export async function initDoms() {
  console.log(' 初始化DOM元素...');
  
  const domMap = [
    { key: 'root', id: 'image-display' },
    { key: 'wwInput', id: 'ww-input' },
    { key: 'wlInput', id: 'wl-input' },
    { key: 'applyWWWL', id: 'apply-btn' },
    { key: 'presetWWWL', id: 'presetWWWL' },
    { key: 'openDicom', id: 'open-dicom' },
    { key: 'srBtn', id: 'sr-btn' },
    { key: 'remoteStatus', id: 'remote-status' },
    { key: 'remoteIP', id: 'remote-ip' },
    { key: 'invertBtn', id: 'invert-btn' },
    { key: 'resetBtn', id: 'reset-btn' },
    { key: 'srReplace', id: 'sr-replace' },
    { key: 'srLoading', id: 'sr-loading' },
    { key: 'srDone', id: 'sr-done' },
    { key: 'currentZoomRate', id: 'current-zoom-rate' },
    { key: 'zoomIn', id: 'zoomIn-btn' },
    { key: 'zoomOut', id: 'zoomOut-btn' },
    { key: 'forceReset', id: 'forceReset' },
    { key: 'diagnoseBtn', id: 'diagnoseBtn' },
    { key: 'toggleRgbModeBtn', id: 'toggle-rgb-mode-btn' }
  ];

  // 并行加载 + 强容错
  const promises = domMap.map(async ({ key, id }) => {
    try {
      doms[key] = await waitForElement(id, );
      console.log(` ${key} → ${id}`);
    } catch (err) {
      doms[key] = null;
      console.warn(`️ ${key} 未找到: ${id}`);
    }
  });

  await Promise.all(promises);
  console.log(' DOM初始化完成');
  return doms;
}

/
   核心修复：安全克隆并替换DOM（清空所有旧事件，彻底解决重复触发BUG）
 /
export function safeCloneAndReplace(oldElement) {
  if (!isDomAvailable(oldElement)) return null;

  try {
    // 克隆节点 + 清空所有事件监听
    const newElement = oldElement.cloneNode(true);
    const parent = oldElement.parentNode;

    if (isDomAvailable(parent)) {
      // 先移除旧元素，再插入新元素（杜绝事件残留）
      oldElement.remove();
      parent.appendChild(newElement);
    }

    return newElement;
  } catch (e) {
    console.error('克隆DOM失败:', e);
    return oldElement;
  }
}
