"""
DIV2K 多模型 SR 对比图生成器

raw/ 目录下需要预先放好每个模型的 SR 输出，命名：
    {model}-{image_id}.png
例如：
    raw/espcn-0001.png
    raw/edsr-0001.png
    raw/dwsr-0001.png
    raw/lu-0001.png
    raw/gt-0001.png
"""

import os
import os.path as path
dirname__ = path.dirname(path.abspath(__file__))

from PIL import Image
from matplotlib import pyplot as plt

os.makedirs(path.join(dirname__, 'output'), exist_ok=True)

# ---------- 模型列表 ----------
models = ['espcn', 'edsr', 'dwsr', 'lu', 'bicubic', 'gt']
model_labels = {
    'espcn':   'ESPCN',
    'edsr':    'EDSR',
    'dwsr':    'DWSR',
    'lu':      'LUMWCNN',
    'bicubic': 'Bicubic',
    'gt':      'GT',
}

# ---------- 想要对比的 crop ----------
# DIV2K 典型 HR 尺寸 2040×1404，SR 输出同尺寸
# left_top 是 HR 坐标系下的位置
crops = [
    {
        'image_id': '0801',       # DIV2K val 集常用 0801~0900
        'left_top': [400, 300],
        'wh': 128,
    },
    {
        'image_id': '0805',
        'left_top': [800, 500],
        'wh': 128,
    },
    {
        'image_id': '0810',
        'left_top': [600, 700],
        'wh': 128,
    },
]

# ---------- 布局 ----------
n_rows = len(crops)
n_cols = len(models)

# 每个子图 2.5 英寸，比例协调
plt.figure(figsize=(2.5 * n_cols, 2.5 * n_rows))

plt_id = 1
for row_idx, crop in enumerate(crops):
    for col_idx, model in enumerate(models):
        img_path = path.join(dirname__, 'raw',
                             f'{model}-{crop["image_id"]}.png')

        if not os.path.exists(img_path):
            print(f'[跳过] 找不到 {img_path}')
            ax = plt.subplot(n_rows, n_cols, plt_id)
            plt_id += 1
            ax.text(0.5, 0.5, f'{model}\nmissing',
                    ha='center', va='center', fontsize=10, color='gray')
            ax.axis('off')
            continue

        image = Image.open(img_path).convert('RGB')

        x, y = crop['left_top']
        w = crop['wh']
        crop_box = (x, y, x + w, y + w)

        ax = plt.subplot(n_rows, n_cols, plt_id)
        plt_id += 1
        ax.imshow(image.crop(crop_box))
        ax.set_xticks([])
        ax.set_yticks([])
        ax.axis('off')

        # 第一行标模型名
        if row_idx == 0:
            ax.set_title(model_labels.get(model, model.upper()),
                         fontsize=13, pad=6)

        # 第一列标 image_id
        if col_idx == 0:
            ax.text(-0.08, 0.5, crop['image_id'],
                    transform=ax.transAxes,
                    ha='right', va='center',
                    fontsize=11, rotation=90)

plt.tight_layout()
out_path = path.join(dirname__, 'output', 'compare_div2k.png')
plt.savefig(out_path, dpi=200, bbox_inches='tight')
plt.show()
print(f'已保存：{out_path}')
