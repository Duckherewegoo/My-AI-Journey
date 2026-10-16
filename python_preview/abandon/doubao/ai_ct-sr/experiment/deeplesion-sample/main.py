"""
DeepLesion 多模型 SR 对比图生成器（豪华版）

功能：
    1. 多窗位切换：肺窗 / 纵隔窗 / 骨窗 / 全窗
    2. 每行一个模型，每列一个视角（窗位图 / 残差热力图 / 放大细节）
    3. 每张子图标注 PSNR / SSIM
    4. 支持病灶 bbox 标注（可选）
    5. 输出一张大图，直接进论文

raw/ 目录约定：
    {model}-{image_id}.png    SR 输出（灰度，512×512）
    gt-{image_id}.png          GT 标签（灰度，512×512）
"""

import os
import os.path as path
dirname__ = path.dirname(path.abspath(__file__))

import numpy as np
from PIL import Image
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

os.makedirs(path.join(dirname__, 'output'), exist_ok=True)

# ==================== 配置 ====================

models = ['bicubic', 'espcn', 'edsr', 'dwsr', 'lu']
model_labels = {
    'bicubic': 'Bicubic',
    'espcn':   'ESPCN',
    'edsr':    'EDSR',
    'dwsr':    'DWSR',
    'lu':      'LUMWCNN',
}

# 窗宽窗位（WW/WL，CT 常用）
WINDOWS = {
    'lung':   {'ww': 1500, 'wl': -600},   # 肺窗：看肺实质、结节
    'medi':   {'ww': 350,  'wl': 50},     # 纵隔窗：看软组织、淋巴结
    'bone':   {'ww': 2000, 'wl': 400},    # 骨窗：看骨质破坏
}

# 要对比的 crop
crops = [
    {
        'image_id': '0023_01',
        'left_top': [180, 180],
        'wh': 128,
        'window': 'lung',
        'lesion_box': None,               # (x, y, w, h) 相对 crop 的坐标，None 则不画
    },
    {
        'image_id': '0045_02',
        'left_top': [220, 200],
        'wh': 128,
        'window': 'medi',
        'lesion_box': [40, 40, 40, 40],
    },
    {
        'image_id': '0078_03',
        'left_top': [150, 250],
        'wh': 128,
        'window': 'bone',
        'lesion_box': None,
    },
]

# 每行显示哪些视角
VIEWS = ['sr', 'residual', 'zoom']    # SR 图 / 残差热力图 / 4× 放大

# ==================== 工具函数 ====================

def apply_window(img_np, ww, wl):
    """
    应用 CT 窗宽窗位。
    img_np: 假设是 [0, 255] 的 uint8，映射回 HU 后重新加窗。
    注意：如果你的 png 已经是 HU 归一化后的，改一下映射。
    """
    # 假设 png 是从 HU 线性映射到 [0,255] 的，反推回 HU
    # HU = pixel / 255 * (HU_max - HU_min) + HU_min
    HU_MIN, HU_MAX = -1024.0, 3071.0
    hu = img_np.astype(np.float32) / 255.0 * (HU_MAX - HU_MIN) + HU_MIN

    lo = wl - ww / 2
    hi = wl + ww / 2
    hu = np.clip(hu, lo, hi)
    out = (hu - lo) / (hi - lo) * 255.0
    return out.astype(np.uint8)


def compute_metrics(sr, gt):
    """sr/gt 都是 [0,1] 的 float32。"""
    psnr = peak_signal_noise_ratio(gt, sr, data_range=1.0)
    h, w = gt.shape
    ws = 11 if (h >= 11 and w >= 11) else (7 if h >= 7 else 3)
    ssim = structural_similarity(gt, sr, data_range=1.0, win_size=ws)
    return psnr, ssim


def make_residual_map(sr, gt):
    """残差热力图：|SR - GT|，用 jet colormap 着色。"""
    diff = np.abs(sr - gt)
    # 归一化到 [0,1]
    if diff.max() > 0:
        diff = diff / diff.max()
    return diff


def load_gray(path_):
    return np.array(Image.open(path_).convert('L'))


# ==================== 主流程 ====================

n_crops = len(crops)
n_models = len(models)
n_views = len(VIEWS)

# 布局：每个 crop 占 n_models 行 × n_views 列，crop 之间空一行
# 总行数 = n_crops * (n_models + 1)
row_heights = []
for _ in range(n_crops):
    row_heights.extend([1.0] * n_models)
    row_heights.append(0.15)   # 间隔

total_rows = len(row_heights)
fig_h = sum(row_heights) * 2.2
fig_w = n_views * 2.5
fig = plt.figure(figsize=(fig_w, fig_h))

gs = fig.add_gridspec(total_rows, n_views,
                      height_ratios=row_heights,
                      hspace=0.05, wspace=0.05)

# 逐 crop 绘制
row_cursor = 0
for crop in crops:
    image_id = crop['image_id']
    x, y = crop['left_top']
    w = crop['wh']

    # 加载 GT 和所有模型 SR
    gt_path = path.join(dirname__, 'raw', f'gt-{image_id}.png')
    if not os.path.exists(gt_path):
        print(f'[跳过 crop] 找不到 GT：{gt_path}')
        row_cursor += n_models + 1
        continue

    gt_full = load_gray(gt_path)

    # 应用窗宽窗位
    win = WINDOWS[crop['window']]
    gt_win = apply_window(gt_full, win['ww'], win['wl'])

    # 裁 crop
    gt_crop = gt_win[y:y + w, x:x + w]

    # 每行一个模型
    for m_idx, model in enumerate(models):
        sr_path = path.join(dirname__, 'raw', f'{model}-{image_id}.png')
        if not os.path.exists(sr_path):
            print(f'[跳过] 找不到 {sr_path}')
            row_cursor += 1
            continue

        sr_full = load_gray(sr_path)
        sr_win = apply_window(sr_full, win['ww'], win['wl'])
        sr_crop = sr_win[y:y + w, x:x + w]

        # 计算指标（在 [0,1] 上算）
        sr_f = sr_crop.astype(np.float32) / 255.0
        gt_f = gt_crop.astype(np.float32) / 255.0
        psnr, ssim = compute_metrics(sr_f, gt_f)

        # ---- 视角 1：SR 图 ----
        ax1 = fig.add_subplot(gs[row_cursor, 0])
        ax1.imshow(sr_crop, cmap='gray', vmin=0, vmax=255)
        ax1.set_xticks([]); ax1.set_yticks([])
        for s in ax1.spines.values():
            s.set_visible(False)

        # 模型名 + 指标
        ax1.set_title(f'{model_labels.get(model, model)}\n'
                      f'PSNR={psnr:.2f}  SSIM={ssim:.4f}',
                      fontsize=9, pad=4)

        # 画病灶框
        if crop['lesion_box'] is not None:
            bx, by, bw, bh = crop['lesion_box']
            ax1.add_patch(Rectangle((bx, by), bw, bh,
                                    linewidth=1.5, edgecolor='red',
                                    facecolor='none'))

        # ---- 视角 2：残差热力图 ----
        ax2 = fig.add_subplot(gs[row_cursor, 1])
        resid = make_residual_map(sr_f, gt_f)
        im = ax2.imshow(resid, cmap='jet', vmin=0, vmax=1)
        ax2.set_xticks([]); ax2.set_yticks([])
        for s in ax2.spines.values():
            s.set_visible(False)
        if m_idx == 0:
            ax2.set_title('残差热力图', fontsize=9, pad=4)

        # ---- 视角 3：4× 放大中心区域 ----
        ax3 = fig.add_subplot(gs[row_cursor, 2])
        cx, cy = w // 2, w // 2
        zoom_half = 16
        zoom = sr_crop[cy - zoom_half:cy + zoom_half,
                       cx - zoom_half:cx + zoom_half]
        ax3.imshow(zoom, cmap='gray', vmin=0, vmax=255,
                   interpolation='nearest')
        ax3.set_xticks([]); ax3.set_yticks([])
        for s in ax3.spines.values():
            s.set_visible(False)
        if m_idx == 0:
            ax3.set_title('4× 放大中心', fontsize=9, pad=4)

        row_cursor += 1

    # 每个 crop 之间空行
    row_cursor += 1

# 标题
fig.suptitle('DeepLesion SR 多模型对比（窗宽窗位 + 残差 + 放大）',
             fontsize=14, y=0.995)

# 保存
out_path = path.join(dirname__, 'output', 'compare_deeplesion.png')
plt.savefig(out_path, dpi=200, bbox_inches='tight')
plt.show()
print(f'已保存：{out_path}')
