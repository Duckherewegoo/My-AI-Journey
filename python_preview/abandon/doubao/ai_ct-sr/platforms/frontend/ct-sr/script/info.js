// CT图像信息展示模块 - 医学标准版
// 修复：超分次数与超分倍率解耦，符合医学影像系统规范
const MEDICAL_CONFIG = {
  // 医学超分标准倍率：由AI模型决定（固定值，不可通过次数计算）
  DEFAULT_UPSCALE_RATIO: .,    // 倍=原图
  MODEL_UPSCALE_RATIO: .       // 你的超分模型倍率（x/x，根据实际模型修改）
};

// 全局状态：当前图像超分倍率（医学核心参数）
let currentUpscaleRatio = MEDICAL_CONFIG.DEFAULT_UPSCALE_RATIO;

/
  更新图像基础信息
 /
export function updateImageInfo(file, image) {
  console.log(" 更新图像信息:", file, image);
  // 加载成功时清空错误信息
  updateImageError(null);

  // 【核心调试】自动检查DOM是否存在，告诉你问题！
  function checkAndSet(id, value) {
    const dom = document.getElementById(id);
    console.log(` 检查DOM ${id}：`, dom ? "找到 " : "未找到 ");
    if (dom) dom.textContent = value || "N/A";
  }

  try {
    // 这里的ID如果显示，就是你HTML里没有这个ID！
    checkAndSet('info-filename', file.name);
    checkAndSet('info-type', file.type);
    checkAndSet('info-w', image.width);  // 假设 ‘info-w’ 表示宽度
    checkAndSet('info-h', image.height); // 假设 ‘info-h’ 表示高度
    checkAndSet('info-transfer', 'DICOM'); // 可能需要新增一个 `info-format` 元素
    
    console.log(" 信息更新执行完成");
  } catch (err) {
    console.log("️ 无错误");
  }
}
// =====================  简化通用版：DICOM错误提示（适配所有压缩格式） =====================
/
  显示图像加载错误（通用简洁版，兼容所有压缩格式）
  @param {Error|null} err - 错误对象，null=清空错误
 /
export function updateImageError(err) {
  const errorDom = document.getElementById('info-error');
  if (!errorDom) {
    console.warn("️ 页面未找到 info-error 元素");
    if (err) console.error(" DICOM错误：", err);
    return;
  }

  // 清空错误
  if (!err) {
    errorDom.textContent = "";
    errorDom.style.display = "none";
    return;
  }

  //  全容错安全获取错误信息
  const errorMessage = err?.message || String(err) || "未知错误";
  let errorMsg = " 错误：DICOM文件加载失败";

  try {
    // . 无图像数据（固定提示）
    if (errorMessage.includes("does not contain image data")) {
      errorMsg = " 错误：该DICOM文件无有效图像数据";
    }
    // .  统一处理：所有压缩格式解码器缺失（JPEG/JPEG/LZW/RLE 全部通用）
    else if (errorMessage.includes("No decoder for transfer syntax")) {
      errorMsg = " 错误：不支持压缩格式的DICOM文件，请使用未压缩的DICOM文件";
    }
    // . 其他所有错误（兜底）
    else {
      errorMsg = " 错误：DICOM文件损坏或不支持";
    }
  } catch (e) {
    // 终极兜底，永不崩溃
    errorMsg = " 错误：DICOM文件损坏或不支持";
  }

  // 页面红色显示错误
  errorDom.textContent = errorMsg;
  errorDom.style.display = "block";
  errorDom.style.color = "f";
  errorDom.style.fontWeight = "bold";
  errorDom.style.marginTop = "px";
  
  console.error(" 图像加载错误：", errorMsg);
}


/
  更新详细信息
 /
function updateDetailInfo(info) {
  try {
    // 文件大小
    const size = info.fileSize
      ? `文件大小: ${(info.fileSize /  / ).toFixed()} MB`
      : '文件大小: N/A';
    updateElementById('detail-filesize', size);

    // DICOM元数据
    const dicom = info.dicomInfo || {};
    updateElementById('detail-patientid', `患者ID: ${dicom.patientID || 'N/A'}`);
    updateElementById('detail-studyid', `研究ID: ${dicom.studyID || 'N/A'}`);
    updateElementById('detail-modality', `模态: ${dicom.modality || 'N/A'}`);
    updateElementById('detail-institution', `机构: ${dicom.institution || 'N/A'}`);

    // 图像属性
    const stats = info.imageStats || {};
    updateElementById('detail-window', `窗宽/窗位: ${stats.windowWidth || 'N/A'} / ${stats.windowCenter || 'N/A'}`);
    updateElementById('detail-bitdepth', `位深度: ${stats.bitDepth || 'N/A'}`);

  } catch (error) {
    console.error(' 更新详细信息失败:', error);
  }
}

/
  根据ID更新元素文本
 /
function updateElementById(elementId, value) {
  const element = document.getElementById(elementId);
  if (element) {
    element.textContent = value;
  } else {
    console.warn(`️ 元素未找到: ${elementId}`);
  }
}

/
  显示默认信息
 /
function showDefaultInfo() {
  const elements = {
    'info-filename': 'N/A',
    'info-type': 'N/A',
    'info-h': 'N/A',
    'info-w': 'N/A',
    'info-transfer': 'N/A',
    'info-sr-count': '超分次数:  次',
    'info-sr-scale': '超分倍率: .x', // 医学标准术语
    'detail-filesize': '文件大小: N/A',
    'detail-patientid': '患者ID: N/A',
    'detail-studyid': '研究ID: N/A',
    'detail-modality': '模态: N/A',
    'detail-institution': '机构: N/A',
    'detail-window': '窗宽/窗位: N/A / N/A',
    'detail-bitdepth': '位深度: N/A'
  };

  Object.keys(elements).forEach(id => updateElementById(id, elements[id]));
  // 重置错误信息
  updateImageError(null);
}

// =====================  核心修复：医学标准超分信息 =====================
/
  更新超分次数（仅记录操作次数，符合医学规范）
  @param {number} srCount - 超分执行次数
 /
export function updateSRInfo(srCount) {
  const validCount = Number.isInteger(srCount) && srCount >=  ? srCount : ;
  console.log(` 超分执行次数: ${validCount}`);

  try {
    // 仅更新次数，倍率独立管理
    updateElementById('info-sr-count', `超分次数: ${validCount} 次`);
    console.log(' 超分次数更新完成');
  } catch (error) {
    console.error(' 更新超分次数失败:', error);
    updateElementById('info-sr-count', '超分次数:  次');
  }
}

/
  更新超分倍率（医学核心参数，由AI模型决定）
  @param {number} ratio - 超分倍率 ././.
 /
export function setUpscaleRatio(ratio) {
  const validRatios = [., ., .]; // 医学影像标准倍率
  if (!validRatios.includes(ratio)) {
    console.warn(`️ 非标准医学超分倍率: ${ratio}, 重置为.x`);
    ratio = MEDICAL_CONFIG.DEFAULT_UPSCALE_RATIO;
  }

  currentUpscaleRatio = ratio;
  updateElementById('info-sr-scale', `超分倍率: ${ratio.toFixed()}x`);
  console.log(` 医学超分倍率已设置: ${ratio}x`);
}

/
  初始化信息面板
 /
export function initInfoDisplay() {
  console.log(' 初始化信息显示...');
  showDefaultInfo();
  addDetailToggle();
  // 初始化默认超分倍率
  setUpscaleRatio(MEDICAL_CONFIG.DEFAULT_UPSCALE_RATIO);
}

/
  绑定详细信息切换事件
 /
function addDetailToggle() {
  const toggleBtn = document.getElementById('show-more-info');
  const detailPanel = document.getElementById('detail-info');

  if (!toggleBtn || !detailPanel) {
    console.warn('️ 详细信息切换元素未找到');
    return;
  }

  toggleBtn.addEventListener('click', (e) => {
    e.preventDefault();
    const isHidden = detailPanel.style.display === 'none';
    detailPanel.style.display = isHidden ? 'block' : 'none';
    toggleBtn.textContent = isHidden ? '[隐藏详细信息]' : '[显示更多信息]';
  });

  console.log(' 详细信息切换功能已启用');
}
