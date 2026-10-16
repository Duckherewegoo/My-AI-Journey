// 医学窗宽窗位控制模块（完整预设版：统一使用doms.js映射）
import { doms, isDomAvailable } from './doms.js';

// ===================== 核心修正：统一全局默认窗宽窗位 =====================
export const DefaultWWWL = { ww: , wl:  };

// ===================== 核心修正：完整CT窗宽窗位预设（医学标准值） =====================
export const windowPresets = [
  // 基础预设
  { name: '默认', ww: , wl:  },  // 使用更通用的默认值
  
  // ===== 头部相关 =====
  { name: '脑窗', ww: , wl:  },           // 脑组织标准窗
  { name: '脑出血', ww: , wl:  },         // 出血检测（原/）
  { name: '脑梗死', ww: , wl:  },          // 新增：窄窗提高病灶检出率
  { name: '垂体窗', ww: , wl:  },         // 新增：垂体及蝶鞍区病变
  { name: '眼眶窗', ww: , wl:  },         // 新增：颌面部眼眶
  { name: '颌面骨窗', ww: , wl:  },     // 新增：颌面部骨骼
  
  // ===== 胸部相关 =====
  { name: '肺窗', ww: , wl: - },        // 更新：肺部标准窗（原/-）
  { name: '纵隔窗', ww: , wl:  },         // 纵隔标准窗（保持不变）
  { name: '胸壁骨窗', ww: , wl:  },     // 新增：胸壁骨骼观察
  
  // ===== 腹部相关 =====
  { name: '腹部窗', ww: , wl:  },         // 腹部标准窗（保持不变）
  { name: '肝窗', ww: , wl:  },           // 更新：肝脏专用窗（原/）
  { name: '胰腺窗', ww: , wl:  },         // 胰腺专用窗（保持不变）
  { name: '脾窗', ww: , wl:  },           // 新增：脾脏专用窗
  
  // ===== 骨骼相关 =====
  { name: '骨窗', ww: , wl:  },         // 更新：标准骨窗（原/）
  { name: '骨细节', ww: , wl:  },       // 更新：骨细节窗（原/）
  { name: '脊柱窗', ww: , wl:  },       // 脊柱专用窗（保持不变）
  { name: '关节窗', ww: , wl:  },       // 新增：关节细节窗
  
  // ===== 软组织相关 =====
  { name: '软组织窗', ww: , wl:  },       // 更新：标准软组织窗（原/）
  { name: '肿瘤窗', ww: , wl:  },         // 肿瘤增强窗（保持不变）
  
  // ===== 颈部相关 =====
  { name: '喉颈部窗', ww: , wl:  },       // 新增：喉颈部、鼻咽、咽喉部
  
  // ===== 其他专用 =====
  { name: '乳腺窗', ww: , wl:  },       // 乳腺专用窗（保持不变）
  { name: '血管窗', ww: , wl:  },        // 更新：血管专用窗（原/）
  { name: '肺结节窗', ww: , wl: - },    // 新增：肺结节检测
  
  // ===== 特殊应用 =====
  { name: '高对比度', ww: , wl:  },       // 高对比度显示（保持不变）
  { name: '低对比度', ww: , wl:  },      // 低对比度显示（保持不变）
  { name: '常规查看', ww: , wl:  },       // 常规查看（保持不变）
  { name: '全范围', ww: , wl:  }          // 查看全部灰度范围（保持不变）
];

// 预设分组（用于UI分类显示）
export const presetCategories = {
  '基础预设': ['默认', '常规查看', '全范围'],
  
  '头部预设': [
    '脑窗', 
    '脑出血', 
    '脑梗死',      // 新增
    '垂体窗',      // 新增
    '眼眶窗',      // 新增
    '颌面骨窗'     // 新增
  ],
  
  '胸部预设': [
    '肺窗', 
    '纵隔窗',
    '胸壁骨窗',    // 新增
    '肺结节窗'     // 新增
  ],
  
  '腹部预设': [
    '腹部窗', 
    '肝窗', 
    '胰腺窗',
    '脾窗'         // 新增
  ],
  
  '骨骼预设': [
    '骨窗', 
    '骨细节', 
    '脊柱窗',
    '关节窗'       // 新增
  ],
  
  '软组织预设': [
    '软组织窗', 
    '肿瘤窗'
  ],
  
  '专用预设': [
    '乳腺窗', 
    '血管窗',
    '喉颈部窗'     // 新增
  ],
  
  '特殊应用': [
    '高对比度', 
    '低对比度'
  ]
};
// 初始化窗宽窗位（主入口）
export function initWWWL() {
  console.log(' 开始初始化窗宽窗位...');
  const { presetWWWL, wwInput, wlInput, applyWWWL, root } = doms;
  console.log(' 窗宽窗位控件状态检查:');
  console.log('  - presetWWWL:', presetWWWL);
  console.log('  - wwInput:', wwInput);
  console.log('  - wlInput:', wlInput);
  console.log('  - applyWWWL:', applyWWWL);
  console.log('  - root:', root);
  
  if (!presetWWWL || !wwInput || !wlInput || !applyWWWL) {
    console.error(' 窗宽窗位控件未加载，缺失的控件:', 
      { presetWWWL: !!presetWWWL, wwInput: !!wwInput, wlInput: !!wlInput, applyWWWL: !!applyWWWL });
    return;
  }
  
  // 填充预设下拉选项
  presetWWWL.innerHTML = '';
  
  // 可选：按分类分组显示预设
  const addPresetOption = (name, ww, wl) => {
    const opt = document.createElement('option');
    opt.value = `${ww},${wl}`;
    opt.textContent = `${name} (WW: ${ww}, WL: ${wl})`;
    presetWWWL.appendChild(opt);
  };
  
  // 添加所有预设选项
  windowPresets.forEach(item => {
    addPresetOption(item.name, item.ww, item.wl);
  });
  
  // 绑定事件
  presetWWWL.addEventListener('change', onPresetChange);
  applyWWWL.addEventListener('click', applyWindowLevel);
  wwInput.addEventListener('keydown', (e) => e.key === 'Enter' && applyWindowLevel());
  wlInput.addEventListener('keydown', (e) => e.key === 'Enter' && applyWindowLevel());
  
  // 初始化显示默认值
  initWWWLDisplay();
  
  console.log(' 窗宽窗位初始化完成，共加载预设:', windowPresets.length, '个');
  console.log(' 可用预设列表:', windowPresets.map(p => `${p.name}: WW=${p.ww}, WL=${p.wl}`));
}

// 预设切换事件
function onPresetChange() {
  const { presetWWWL, wwInput, wlInput } = doms;
  const value = presetWWWL.value;
  if (!value) return;

  const [ww, wl] = value.split(',').map(Number);
  wwInput.value = ww;
  wlInput.value = wl;
  applyWindowLevel();
}

// ===================== 核心：应用窗宽窗位（严格无尺寸修改，防黑屏） =====================
export function applyWindowLevel() {
  const { wwInput, wlInput, root } = doms;
  // 容错：无Cornerstone/无图像元素直接返回
  if (!window.cornerstone || !root) {
    console.warn('️ Cornerstone 或 root 元素未就绪，跳过窗宽窗位应用');
    return;
  }
  
  // 防黑屏核心：获取数值 + 严格合法性校验
  let ww = Number(wwInput.value) || DefaultWWWL.ww;
  let wl = Number(wlInput.value) || DefaultWWWL.wl;
  
  // 强制校验：窗宽必须 > ，否则Cornerstone渲染黑屏
  ww = Math.max(ww, );
  
  // 仅修改VOI（窗宽窗位），不触碰任何图像尺寸/缩放参数
  const viewport = cornerstone.getViewport(root);
  if (viewport) {
    viewport.voi = { windowWidth: ww, windowCenter: wl };
    cornerstone.setViewport(root, viewport);
    console.log(` 应用窗宽窗位：WW=${ww}, WL=${wl}`);
  } else {
    console.warn('️ 无法获取当前视口，跳过窗宽窗位应用');
  }
}

export function syncWWWL(ww = DefaultWWWL.ww, wl = DefaultWWWL.wl) {
  const { wwInput, wlInput, presetWWWL } = doms;
  if (!wwInput || !wlInput || !presetWWWL) return;
  
  // 赋值输入框
  wwInput.value = ww;
  wlInput.value = wl;
  
  // 查找匹配的预设
  const presetValue = `${ww},${wl}`;
  const matchingOption = Array.from(presetWWWL.options).find(
    option => option.value === presetValue
  );
  
  if (matchingOption) {
    presetWWWL.value = presetValue;
  } else {
    // 如果没有完全匹配的预设，选中"默认"预设
    presetWWWL.value = `${DefaultWWWL.ww},${DefaultWWWL.wl}`;
  }
  
  // 同步后自动应用
  applyWindowLevel();
}

// 获取当前有效窗宽窗位
export function getCurrentWindowLevel() {
  const { wwInput, wlInput } = doms;
  let ww = Number(wwInput.value) || DefaultWWWL.ww;
  let wl = Number(wlInput.value) || DefaultWWWL.wl;
  
  // 统一返回合法值
  ww = Math.max(ww, );
  return { ww, wl };
}

// 快速应用预设函数
export function applyPreset(presetName) {
  const preset = windowPresets.find(p => p.name === presetName);
  if (preset) {
    console.log(` 快速应用预设: ${presetName} (WW=${preset.ww}, WL=${preset.wl})`);
    syncWWWL(preset.ww, preset.wl);
    return true;
  } else {
    console.warn(`️ 预设不存在: ${presetName}`);
    return false;
  }
}

// 获取所有预设名称
export function getPresetNames() {
  return windowPresets.map(p => p.name);
}

// 根据预设名称获取窗宽窗位
export function getPresetValues(presetName) {
  const preset = windowPresets.find(p => p.name === presetName);
  return preset ? { ww: preset.ww, wl: preset.wl } : null;
}

// 初始化默认值显示（默认选中「默认」预设）
export function initWWWLDisplay() {
  const { wwInput, wlInput, presetWWWL } = doms;
  if (!wwInput || !wlInput) return;
  
  // 赋值默认值
  wwInput.value = DefaultWWWL.ww;
  wlInput.value = DefaultWWWL.wl;
  
  // 同步下拉框选中
  const defaultPresetValue = `${DefaultWWWL.ww},${DefaultWWWL.wl}`;
  const hasDefaultOption = Array.from(presetWWWL.options).some(
    option => option.value === defaultPresetValue
  );
  
  if (hasDefaultOption) {
    presetWWWL.value = defaultPresetValue;
  } else if (presetWWWL.options.length > ) {
    // 如果"默认"预设不存在，选中第一个预设
    presetWWWL.selectedIndex = ;
  }
}
