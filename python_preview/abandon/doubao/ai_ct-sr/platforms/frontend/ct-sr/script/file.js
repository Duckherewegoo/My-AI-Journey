import { doms, isDomAvailable, safeCloneAndReplace } from './doms.js';
import { updateImageInfo, updateImageError } from './info.js';
import { clearDefaultPlaceholder } from './default.js';

// 全局 RGB 模式状态
let isRgbMode = false;

export function initFileLoader() {
  if (!isDomAvailable(doms.root)) return;
  window._ctsr = {};
  const fileInput = document.getElementById('open-dicom');
  if (fileInput) fileInput.value = '';

  // 初始化容器样式
  if (doms.root) {
    doms.root.style.cssText = `
      width: % !important;
      height: px !important;
      background:  !important;
      position: relative !important;
      overflow: hidden !important;
      z-index:  !important;
    `;
  }

  try {
    if (window.cornerstoneWebImageLoader) cornerstoneWebImageLoader.external.cornerstone = cornerstone;
    if (window.cornerstoneWADOImageLoader) {
      cornerstoneWADOImageLoader.external.cornerstone = cornerstone;
      cornerstoneWADOImageLoader.external.dicomParser = window.dicomParser;
    }
  } catch (e) {}

  // 初始化 RGB 切换按钮
  initRgbToggleButton();

  if (fileInput) fileInput.addEventListener('change', handleFileSelect);
}

//  重新加载当前图像（修复全黑问题）
async function reloadCurrentImage() {
  if (!window._ctsr?.currentFile || !window.cornerstone || !isDomAvailable(doms.root)) return;

  const cs = window.cornerstone;
  const element = doms.root;
  const file = window._ctsr.currentFile;

  try {
    // . 保存当前视口状态（关键！）
    const currentViewport = cs.getViewport(element);
    const savedScale = currentViewport.scale;
    const savedTranslation = { ...currentViewport.translation };
    const savedVoi = { ...currentViewport.voi };

    console.log(' 保存视口状态:', {
      scale: savedScale,
      translation: savedTranslation,
      voi: savedVoi
    });

    // . 重新加载图像
    const fileId = cornerstoneWADOImageLoader.wadouri.fileManager.add(file);
    const image = await cs.loadImage(`dicomfile://${fileId}`);

    // . 根据 RGB 模式设置图像属性（必须在加载后立即设置）
    image.color = isRgbMode;  // 关键：设置是否为彩色图像
    image.unsigned = !isRgbMode;  // RGB 模式通常是有符号的
    image.pixelReplication = !isRgbMode;

    // . 获取新的默认视口
    const newViewport = cs.getDefaultViewportForImage(element, image);
    
    // . 恢复保存的视口状态
    newViewport.scale = savedScale;
    newViewport.translation = savedTranslation;
    newViewport.voi = savedVoi;  // 恢复窗宽窗位

    // . 显示图像并应用恢复的视口
    await cs.displayImage(element, image, newViewport);
    
    // . 强制更新以确保状态生效
    cs.updateImage(element);

    // . 更新全局状态
    window._ctsr.currentImage = image;
    updateImageInfo(file, image);

    console.log(` 图像已切换到 ${isRgbMode ? 'RGB' : '灰度'} 模式（视图状态已恢复）`);
  } catch (err) {
    console.error(' 重新加载图像失败:', err);
    updateImageError(err);
  }
}

function initRgbToggleButton() {
  const toggleBtn = doms.toggleRgbModeBtn;
  if (!toggleBtn) return;

  const safeBtn = safeCloneAndReplace(toggleBtn);
  if (!safeBtn) return;

  safeBtn.addEventListener('click', async () => {
    isRgbMode = !isRgbMode;
    updateRgbButtonUI();
    
    // 如果有图像，重新加载以应用 RGB/Grayscale 模式
    if (window._ctsr?.currentImage) {
      await reloadCurrentImage();
    }
  });

  updateRgbButtonUI();
}

function updateRgbButtonUI() {
  const toggleBtn = doms.toggleRgbModeBtn;
  if (!toggleBtn) return;

  if (isRgbMode) {
    toggleBtn.innerHTML = '<i class="fa fa-palette"></i> RGB模式';
    toggleBtn.style.backgroundColor = 'CAF';
    toggleBtn.title = '当前：RGB 模式（超分已禁用）';
  } else {
    toggleBtn.innerHTML = '<i class="fa fa-adjust"></i> 灰度模式';
    toggleBtn.style.backgroundColor = '';
    toggleBtn.title = '当前：灰度模式（超分可用）';
  }
}

async function handleFileSelect(e) {
  const file = e.target.files[];
  if (!file) return;

  const cs = window.cornerstone;
  const element = doms.root;
  clearDefaultPlaceholder();

  try {
    // 加载DICOM图像
    const fileId = cornerstoneWADOImageLoader.wadouri.fileManager.add(file);
    const image = await cs.loadImage(`dicomfile://${fileId}`);

    // 根据当前模式设置图像属性
    image.color = isRgbMode;
    image.unsigned = !isRgbMode;
    image.pixelReplication = !isRgbMode;

    // 医疗DICOM标准配置
    const initViewport = cs.getDefaultViewportForImage(element, image);
    initViewport.voi = { windowWidth: , windowCenter:  };
    initViewport.translation = { x: , y:  };
    initViewport.scale = ;

    // 显示图像
    await cs.displayImage(element, image, initViewport);

    // 适配窗口+强制居中
    cs.fitToWindow(element);
    setTimeout(() => {
      const finalVp = cs.getViewport(element);
      finalVp.translation = { x: , y:  };
      cs.setViewport(element, finalVp);
      cs.invalidate(element);
      cs.updateImage(element);
    }, );

    // 更新信息
    window._ctsr = { fileOpened: true, currentImage: image, currentFile: file };
    updateImageInfo(file, image);

  } catch (err) {
    console.error(' 渲染错误详情：', err);
    updateImageError(err);
  }
}

export default { initFileLoader };
