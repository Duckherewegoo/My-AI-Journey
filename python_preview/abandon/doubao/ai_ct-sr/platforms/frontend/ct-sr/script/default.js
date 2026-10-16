import { doms, isDomAvailable } from './doms.js';

let defaultImageLoaded = false;

//  修复：创建独立占位符，不覆盖、不删除Canvas
function createMinimalPlaceholder() {
  if (!isDomAvailable(doms.root)) return;

  //  关键：只新增自己的占位层，不清空innerHTML（保留Cornerstone Canvas）
  const placeholder = document.createElement('div');
  placeholder.id = 'ctsr-placeholder'; // 固定ID
  placeholder.style.cssText = `
    position: absolute;
    top: ;
    left: ;
    width: %;
    height: %;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: aaa;
    color: ;
    font-family: 'Segoe UI', Arial, sans-serif;
    z-index: ; / 浮在Canvas上方 /
  `;

  placeholder.innerHTML = `
    <div style="text-align: center;">
      <div style="margin-bottom: px; color: FF;">
        <i class="fa fa-file-image-o" style="font-size: px;"></i>
      </div>
      <div style="font-size: px; margin-bottom: px; color: ccc;">医学影像系统</div>
      <div style="font-size: px; margin-bottom: px; color: ;">请加载医学影像文件</div>
      <div style="font-size: px; color: ;">只支持 DICOM</div>
    </div>
  `;

  doms.root.appendChild(placeholder);
}

//  修复：只删除自己的占位层，保留Canvas
export function clearDefaultPlaceholder() {
  if (!isDomAvailable(doms.root)) return;
  const placeholder = document.getElementById('ctsr-placeholder');
  if (placeholder) placeholder.remove();
  defaultImageLoaded = false;
  console.log(' 占位图已移除，Canvas 完好保留');
}

export function initDefaultImage() {
  if (defaultImageLoaded) return;
  if (!isDomAvailable(doms.root)) {
    setTimeout(initDefaultImage, );
    return;
  }
  createMinimalPlaceholder();
  defaultImageLoaded = true;
  console.log(' 占位图加载完成（不破坏Canvas）');
}
