import { BackendUrl } from './config.js';
import { doms, isDomAvailable } from './doms.js';
import { updateSRInfo, setUpscaleRatio } from './info.js';

// ===================== 【全局状态 / 常量】 =====================
const srState = {
  isProcessing: false,
  srKey: null,
  remoteAvailable: false,
  srCount: 
};

// 定时器容器（防止内存泄漏）
let timers = {
  statusCheck: null,
  imageWatch: null
};

// 初始化锁（杜绝重复初始化）
let srInitialized = false;

// 医学超分标准倍率
const MEDICAL_UPSCALE_RATIO = .;

// ===================== 【初始化函数】 =====================
export function initSRService() {
  if (srInitialized) return; // 只初始化一次

  // 清理旧定时器
  clearAllTimers();

  checkRemoteStatus();
  bindSREvents();
  watchImageStatus();
  updateButtonState();

  // 定时检查服务状态
  timers.statusCheck = setInterval(checkRemoteStatus, );
  
  srInitialized = true;
  console.log(' 医学影像超分服务初始化完成');
}

// 重置超分状态
export function resetSRState() {
  srState.srKey = null;
  srState.isProcessing = false;
  srState.srCount = ;
  
  updateSRInfo(srState.srCount);
  setUpscaleRatio(.); // 重置为医学标准倍原图
  updateButtonState();
  setUIState('idle');
}

// 清理所有定时器
function clearAllTimers() {
  if (timers.statusCheck) clearInterval(timers.statusCheck);
  if (timers.imageWatch) clearInterval(timers.imageWatch);
  timers = { statusCheck: null, imageWatch: null };
}

// ===================== 【核心：图像有效性校验 → 杜绝全黑/无效图】 =====================
function validateImageData(pixelData, width, height) {
  try {
    if (!pixelData || pixelData.length === ) {
      console.error(' 像素数据为空');
      return false;
    }
    if (width <=  || height <= ) {
      console.error(' 无效图像尺寸:', { width, height });
      return false;
    }

    const totalPixels = pixelData.length;
    console.log(` 图像像素统计: 总像素=${totalPixels}, 尺寸=${width}x${height}`);
    
    // 计算像素统计
    let minVal = ;
    let maxVal = ;
    let sum = ;
    let blackPixelCount = ;
    const step = Math.max(, Math.floor(totalPixels / ));
    
    for (let i = ; i < totalPixels; i += step) {
      const val = pixelData[i];
      if (val < minVal) minVal = val;
      if (val > maxVal) maxVal = val;
      sum += val;
      if (val <= ) blackPixelCount++;
    }
    
    const avgVal = sum / (totalPixels / step);
    const blackRatio = (blackPixelCount / (totalPixels / step))  ;
    
    console.log(` 像素统计: 最小值=${minVal}, 最大值=${maxVal}, 平均值=${avgVal.toFixed()}, 黑色像素比例=${blackRatio.toFixed()}%`);
    
    // 检查是否为全黑图像
    const blackThreshold = totalPixels  .;
    if (blackPixelCount >= blackThreshold  .) {
      console.error(' 检测到全黑图像，拒绝渲染');
      return false;
    }
    
    return true;
  } catch (e) {
    console.error(' 图像校验异常:', e);
    return false;
  }
}

// ===================== 【核心工具函数】 =====================
// 实时监听图像加载
function watchImageStatus() {
  timers.imageWatch = setInterval(() => {
    if (!window.cornerstone || !isDomAvailable(doms.root)) return;
    
    const enabledElement = cornerstone.getEnabledElement(doms.root);
    // 安全初始化全局状态
    window._ctsr = window._ctsr || {};
    window._ctsr.fileOpened = !!enabledElement?.image;
    window._ctsr.currentImage = enabledElement?.image || null;
    
    updateButtonState();
  }, );
}

// 检查远程服务状态
async function checkRemoteStatus() {
  try {
    const res = await fetch(`${BackendUrl}ping`, { method: 'GET', signal: AbortSignal.timeout() });
    srState.remoteAvailable = res.ok;
  } catch (e) {
    srState.remoteAvailable = false;
  } finally {
    updateRemoteStatus();
    updateButtonState();
  }
}

// 更新服务状态UI
function updateRemoteStatus() {
  if (!doms.remoteStatus || !doms.remoteIP) return;
  doms.remoteStatus.textContent = srState.remoteAvailable ? '运行中' : '未连接';
  doms.remoteStatus.style.color = srState.remoteAvailable ? 'green' : 'red';
  doms.remoteStatus.style.fontWeight = 'bold';
  doms.remoteIP.textContent = BackendUrl || 'N/A';
}

// 更新超分按钮状态
function updateButtonState() {
  if (!doms.srBtn) return;
  const hasImage = !!(window._ctsr?.fileOpened && window._ctsr.currentImage);
  const canProcess = srState.remoteAvailable && hasImage;
  
  doms.srBtn.disabled = !canProcess || srState.isProcessing;
  doms.srBtn.style.opacity = srState.isProcessing ? '.' : (canProcess ? '' : '.');
  doms.srBtn.innerHTML = srState.isProcessing ? '处理中...' : '<i class="fa fa-bolt"></i>超分辨率';
}

// UI状态控制
function setUIState(state) {
  if (!doms.srLoading || !doms.srDone) return;
  doms.srLoading.style.display = state === 'loading' ? 'block' : 'none';
  doms.srDone.style.display = state === 'ready' ? 'block' : 'none';
}

// 系统通知
function showNotification(message, type = 'info', duration = ) {
  document.getElementById('ctsr-notification')?.remove();
  const container = document.createElement('div');
  container.id = 'ctsr-notification';
  const colors = { 
    error: 'f', 
    success: 'caf', 
    warning: 'ff', 
    info: 'f' 
  };
  container.innerHTML = `<div style="position:fixed;top:px;right:px;padding:px px;border-radius:px;color:white;font-weight:bold;z-index:;background:${colors[type]}">${message}</div>`;
  document.body.appendChild(container);
  setTimeout(() => container.remove(), duration);
}

// 获取有效图像Blob（修复兼容性）
function getValidImageBlob() {
  return new Promise((resolve, reject) => {
    if (!window.cornerstone || !isDomAvailable(doms.root)) return reject('系统未就绪');
    
    const enabledElement = cornerstone.getEnabledElement(doms.root);
    if (!enabledElement?.image) return reject('无有效图像');
    
    const canvas = document.querySelector('.cornerstone-canvas');
    if (!canvas) return reject('图像画布未生成');

    // 兼容所有浏览器的图像转换
    setTimeout(() => {
      canvas.toBlob((blob) => {
        blob ? resolve(blob) : reject('图像转换失败');
      }, 'image/png');
    }, );
  });
}

// 加载并显示Web图像（修复CORS问题）
async function loadAndViewWebImage(url) {
  return new Promise((resolve, reject) => {
    console.log(`️ 加载图片，URL: ${url}`);
    
    //  核心修复：使用标准的HTTP URL作为imageId，避免自定义协议导致的CORS错误
    // 由于在initCornerstone中已经为'http'和'https'协议注册了普通图片加载器
    // 这里直接使用完整的HTTP URL即可
    const imageId = url;
    
    cornerstone.loadImage(imageId).then(image => {
      console.log(' Cornerstone图像加载完成，尺寸:', `${image.width}x${image.height}`);
      
      // 获取默认视口
      const viewport = cornerstone.getDefaultViewportForImage(doms.root, image);
      
      // 智能计算初始缩放比例
      const displayDiv = doms.root;
      if (displayDiv) {
        const containerWidth = displayDiv.clientWidth;
        const containerHeight = displayDiv.clientHeight;
        
        if (containerWidth >  && containerHeight > ) {
          const scaleX = containerWidth / image.width;
          const scaleY = containerHeight / image.height;
          const initialScale = Math.min(scaleX, scaleY)  .; // %填充
          
          viewport.scale = initialScale;
          viewport.translation = { x: , y:  };
          
          console.log(' 智能缩放配置:', {
            container: `${containerWidth}x${containerHeight}`,
            image: `${image.width}x${image.height}`,
            appliedScale: initialScale.toFixed()
          });
        }
      }
      
      // 显示图像
      cornerstone.displayImage(doms.root, image, viewport);
      resolve();
    }).catch(error => {
      console.error(' Cornerstone加载图像失败:', error);
      reject(error);
    });
  });
}

// ===================== 【超分核心】 =====================
async function handleSuperResolution() {
  if (srState.isProcessing) {
    showNotification('正在处理中，请稍候...', 'info');
    return;
  }
  if (!window._ctsr?.fileOpened || !srState.remoteAvailable) {
    showNotification('请先加载图像或检查服务状态', 'warning');
    return;
  }

  try {
    srState.isProcessing = true;
    updateButtonState();
    setUIState('loading');
    showNotification('开始医学影像超分处理...', 'info');

    // 获取原始图像真实尺寸
    const { width: originalWidth, height: originalHeight } = window._ctsr.currentImage;
    console.log(' 原始图像尺寸:', { width: originalWidth, height: originalHeight });
    
    const targetWidth = originalWidth  MEDICAL_UPSCALE_RATIO;
    const targetHeight = originalHeight  MEDICAL_UPSCALE_RATIO;
    console.log(' 目标超分尺寸:', { width: targetWidth, height: targetHeight });

    // 上传图像
    console.log(' 准备上传图像...');
    const blob = await getValidImageBlob();
    console.log(' 上传图像Blob:', { size: blob.size, type: blob.type });
    
    const formData = new FormData();
    formData.append('image', blob);
    // 医学标准倍率传参
    formData.append('width', targetWidth);
    formData.append('height', targetHeight);

    console.log(' 发送超分请求到:', `${BackendUrl}predict`);
    // 请求超分接口
    const res = await fetch(`${BackendUrl}predict`, {
      method: 'POST', 
      body: formData, 
      signal: AbortSignal.timeout()
    });
    
    console.log(' 收到响应:', res.status, res.statusText);
    const result = await res.json();
    console.log(' 响应数据:', result);

    if (!result.success) {
      console.error(' 超分处理失败:', result.error);
      throw new Error(result.error || '超分处理失败');
    }
    
    console.log(' 超分处理成功:', {
      filename: result.filename,
      originalSize: result.original_size,
      outputSize: result.output_size,
      scale: result.scale
    });
    
    srState.srKey = result.filename;
    setUIState('ready');
    showNotification(' 超分处理完成', 'success', );

  } catch (e) {
    console.error(' 超分过程异常:', e);
    showNotification(` 处理失败：${e.message}`, 'error');
  } finally {
    srState.isProcessing = false;
    updateButtonState();
  }
}

// 应用超分结果
async function handleReplaceSRResult() {
  if (!srState.srKey) {
    showNotification('暂无超分结果', 'warning');
    return;
  }

  try {
    console.log(' 开始获取超分结果:', srState.srKey);
    setUIState('loading');
    
    const url = `${BackendUrl}get_output?filename=${srState.srKey}`;
    console.log(' 直接使用图片URL:', url);
    
    await loadAndViewWebImage(url);

    // 更新医学标准超分信息
    srState.srCount++;
    updateSRInfo(srState.srCount);
    setUpscaleRatio(MEDICAL_UPSCALE_RATIO);
    
    showNotification(' 超分结果已应用', 'success');
  } catch (e) {
    console.error(' 加载超分结果失败:', e);
    showNotification(` 加载失败：${e.message}`, 'error');
  } finally {
    setUIState('ready');
  }
}

// 绑定按钮事件（仅绑定一次）
function bindSREvents() {
  // 先清空旧事件，防止重复触发
  if (doms.srBtn) {
    doms.srBtn.replaceWith(doms.srBtn.cloneNode(true));
    document.getElementById('sr-btn').addEventListener('click', handleSuperResolution);
  }
  if (doms.srReplace) {
    doms.srReplace.replaceWith(doms.srReplace.cloneNode(true));
    document.getElementById('sr-replace').addEventListener('click', handleReplaceSRResult);
  }
}

// ===================== 【销毁自动初始化】 =====================
// 移除原自动初始化，完全由主调度器控制
// document.addEventListener('DOMContentLoaded', initSRService);

// 导出
export default {
  initSRService,
  resetSRState,
  srState
};
