// 医学影像超分辨率系统 - 核心初始化调度器
import { doms, isDomAvailable, initDoms } from './doms.js';
import { initWWWL } from './wwwl.js';
import { initFileLoader } from './file.js';
import { initInfoDisplay } from './info.js';
import { initSRService } from './sr.js';
import { initZoomPanModule } from './zoom-pan.js';
import { initOther } from './other.js';
import { initDefaultImage } from './default.js';

// 全局初始化锁（防止重复执行）
let cornerstoneInitialized = false;
let appInitialized = false;

// 系统配置
const initConfig = {
  enableUIExtras: true
};

// ==============================================
// 全局服务重连
// ==============================================
window.reconnectService = function () {
  console.log(' 强制重连超分服务...');
  const notify = window.uiExtras?.showNotification || showReconnectStatus;

  try {
    initSRService();
    notify('服务重连成功', 'success');
  } catch (err) {
    console.error('重连失败:', err);
    notify(`重连失败：${err.message}`, 'error');
    setTimeout(() => location.reload(), );
  }
};

// ==============================================
// 重连状态弹窗
// ==============================================
function showReconnectStatus(message, type = 'info') {
  document.getElementById('reconnect-status')?.remove();
  const statusDiv = document.createElement('div');
  statusDiv.id = 'reconnect-status';
  statusDiv.style.cssText = `
    position: fixed; top: %; left: %; transform: translate(-%, -%);
    padding: px; border-radius: px; z-index: ;
    background: ${type === 'error' ? 'fdda' : 'decf'};
    color: ${type === 'error' ? 'c' : 'c'};
    border: px solid ${type === 'error' ? 'fccb' : 'beeeb'};
    text-align: center; box-shadow:  px px rgba(,,,.);
  `;
  statusDiv.innerHTML = `
    <h>服务重连</h>
    <p>${message}</p>
    <button onclick="this.parentElement.remove()" style="margin:px;padding:px px">取消</button>
    <button onclick="location.reload()" style="background:bff;color:white;padding:px px">刷新</button>
  `;
  document.body.appendChild(statusDiv);
}

// ==============================================
// 重连按钮
// ==============================================
function addReconnectButton() {
  document.getElementById('reconnect-service-btn')?.remove();
  const btn = document.createElement('button');
  btn.id = 'reconnect-service-btn';
  btn.innerHTML = ' 重连服务';
  btn.style.cssText = `
    position: fixed; top: px; right: px; z-index: ;
    padding: px px; border-radius: px; border: none;
    background: ffc; color: ; cursor: pointer;
  `;
  btn.onclick = window.reconnectService;
  document.body.appendChild(btn);
}

// ==============================================
// Cornerstone 核心初始化（DICOM + 普通图像）
// ==============================================
function initCornerstone() {
  if (cornerstoneInitialized) {
    console.log(' Cornerstone 已初始化');
    return true;
  }
  
  console.log(' 初始化 Cornerstone...');
  if (!window.cornerstone) {
    console.error(' Cornerstone 核心库未加载');
    return false;
  }
  
  try {
    // 注册Web图像加载器
    if (window.cornerstoneWebImageLoader) {
      cornerstoneWebImageLoader.external.cornerstone = cornerstone;
      // 注册多种图像ID模式
      cornerstone.registerImageLoader('http', cornerstoneWebImageLoader.loadImage);
      cornerstone.registerImageLoader('https', cornerstoneWebImageLoader.loadImage);
      cornerstone.registerImageLoader('wadouri', cornerstoneWebImageLoader.loadImage);
      console.log(' Web图像加载器注册成功');
    }
    
    // 启用显示容器
    if (isDomAvailable(doms.root)) {
      cornerstone.enable(doms.root);
      console.log(' Cornerstone显示容器已启用');
    } else {
      console.error(' 显示容器未找到: image-display');
      return false;
    }
    
    cornerstoneInitialized = true;
    console.log(' Cornerstone 初始化完成');
    return true;
  } catch (err) {
    console.error(' Cornerstone 初始化失败:', err);
    return false;
  }
}

// ==============================================
// 统一初始化所有业务模块
// ==============================================
export async function initAllModules() {
  console.log(' 医学影像超分系统 - 开始初始化');
  
  //  第一步：必须先初始化DOM映射
  try {
    console.log(' 初始化DOM映射...');
    await initDoms();  // 等待所有DOM元素映射完成
    console.log(' DOM映射完成');
  } catch (err) {
    console.error(' DOM初始化失败，系统无法启动:', err);
    return;
  }
  
  //  第二步：验证关键DOM元素是否找到
  if (!isDomAvailable(doms.root)) {
    console.error(' 核心显示容器未找到: image-display');
    return;
  }
  
  console.log(' DOM映射完成，开始初始化功能模块...');
  
  //  第三步：按依赖顺序初始化功能模块
  // . 必须先初始化Cornerstone（图像显示核心）
  console.log(' 初始化Cornerstone...');
  if (!initCornerstone()) {
    console.error(' Cornerstone初始化失败');
    return;
  }
  
  // . 初始化信息显示
  console.log(' 初始化信息显示...');
  initInfoDisplay();
  
  // . 初始化文件加载（此时Cornerstone已就绪）
  console.log(' 初始化文件加载...');
  initFileLoader();
  
  // . 初始化窗宽窗位（依赖doms中的控件引用）
  console.log(' 初始化窗宽窗位...');
  initWWWL();
  
  // . 初始化其他功能模块
  console.log(' 初始化缩放平移...');
  initZoomPanModule();
  
  console.log(' 初始化其他功能...');
  initOther();
  
  // . 可选UI扩展
  if (initConfig.enableUIExtras && window.uiExtras?.init) {
    console.log(' 初始化UI扩展...');
    window.uiExtras.init();
  }
  
  // . 初始化超分服务
  console.log(' 初始化超分服务...');
  initSRService();
  
  // . 添加重连按钮
  console.log(' 添加重连按钮...');
  addReconnectButton();
  
  // . 初始化默认占位图
  console.log(' 初始化默认占位图...');
  initDefaultImage();
  
  console.log(' 系统初始化全部完成');
}

// ==============================================
// 应用主入口
// ==============================================
export async function initApp() {
  if (appInitialized) {
    console.log('️ 应用已初始化，跳过重复初始化');
    return;
  }

  console.log(' 医学影像超分系统 - 开始初始化');
  try {
    //  修复：移除了重复的 initDoms 调用
    // 现在 initDoms 只在 initAllModules 中调用一次
    await initAllModules(); // 初始化所有功能

    appInitialized = true;
    window.showAppNotification?.('系统初始化完成', 'success');
    console.log(' 系统初始化全部完成');
  } catch (err) {
    console.error(' 初始化失败:', err);
    showError(`初始化失败：${err.message}`);
  }
}

// ==============================================
// 错误提示
// ==============================================
function showError(msg) {
  const errBox = document.createElement('div');
  errBox.style.cssText = `
    position: fixed; top: %; left: %; transform: translate(-%, -%);
    background: fdda; color: c; padding: px; border-radius: px; z-index: ;
  `;
  errBox.innerHTML = `
    <h>系统错误</h><p>${msg}</p>
    <button onclick="location.reload()" style="margin-top:px;padding:px px">刷新重试</button>
  `;
  document.body.appendChild(errBox);
}

// ==============================================
// 安全启动
// ==============================================
async function startup() {
  try {
    console.log(' 启动医学影像超分系统...');
    await initApp();
  } catch (err) {
    console.error('启动失败:', err);
  }
}

// ==============================================
// 自动启动
// ==============================================
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', startup);
  console.log(' 等待DOM加载完成...');
} else {
  console.log(' DOM已就绪，立即启动...');
  startup();
}

// ==============================================
// 全局暴露方法
// ==============================================
window.initCTSRApp = initApp;
window.retryInitialization = () => {
  appInitialized = false;
  cornerstoneInitialized = false;
  startup();
};

console.log(' 初始化调度器加载完成');
