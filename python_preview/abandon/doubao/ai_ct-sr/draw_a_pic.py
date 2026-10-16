import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch
import numpy as np

# 设置中文字体支持
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# 创建图形和坐标轴
fig, ax = plt.subplots(1, 1, figsize=(18, 11))
ax.set_xlim(0, 18)
ax.set_ylim(0, 11)
ax.axis('off')

# ==================== 绘制阶段背景框 ====================

# 阶段一：浅层特征提取 (浅蓝色)
rect = patches.Rectangle((0.3, 2.2), 5.4, 8.0, linewidth=1.5,
                         facecolor='#DEF0F8', edgecolor='#9BC8ED', alpha=0.7)
ax.add_patch(rect)
ax.text(3.0, 10.0, '阶段一：浅层特征提取', fontsize=14, ha='center', weight='bold')

# 阶段二：深层特征映射 (浅黄色)
rect = patches.Rectangle((5.7, 2.2), 6.6, 8.0, linewidth=1.5,
                         facecolor='#FFFACD', edgecolor='#F5D76E', alpha=0.6)
ax.add_patch(rect)
ax.text(9.0, 10.0, '阶段二：深层特征映射', fontsize=14, ha='center', weight='bold')

# 阶段三：高分辨率重建 (浅绿色)
rect = patches.Rectangle((12.3, 2.2), 5.4, 8.0, linewidth=1.5,
                         facecolor='#E8F8E8', edgecolor='#8BC34A', alpha=0.6)
ax.add_patch(rect)
ax.text(15.0, 10.0, '阶段三：高分辨率重建', fontsize=14, ha='center', weight='bold')

# ==================== 绘制输入图像 ====================

input_img = patches.Rectangle((0.7, 6.5), 2.0, 2.0, linewidth=1.5,
                              facecolor='white', edgecolor='black')
ax.add_patch(input_img)
ax.text(1.7, 7.5, '输入\n低分辨率\nCT图像', fontsize=9, ha='center', va='center')

# ==================== 绘制浅层特征提取模块 ====================

# 轻量化小波卷积 (上)
lw_conv1 = FancyBboxPatch((2.9, 7.3), 1.6, 1.2, boxstyle="round,pad=0.05",
                          facecolor='#A8D8EA', edgecolor='black', linewidth=1.0)
ax.add_patch(lw_conv1)
ax.text(3.7, 7.9, '轻量化\n小波卷积', fontsize=8.5, ha='center', va='center')

# 轻量化小波卷积 (下)
lw_conv2 = FancyBboxPatch((2.9, 5.0), 1.6, 1.2, boxstyle="round,pad=0.05",
                          facecolor='#A8D8EA', edgecolor='black', linewidth=1.0)
ax.add_patch(lw_conv2)
ax.text(3.7, 5.6, '轻量化\n小波卷积', fontsize=8.5, ha='center', va='center')

# DWT 分解模块
dwt_box = FancyBboxPatch((4.7, 5.2), 1.0, 1.2, boxstyle="round,pad=0.05",
                         facecolor='#F7B7C7', edgecolor='black', linewidth=1.0)
ax.add_patch(dwt_box)
ax.text(5.2, 5.8, 'DWT\n分解', fontsize=8.5, ha='center', va='center')

# ==================== 绘制深层特征映射模块 ====================

# 深层卷积 (下)
deep_conv1 = FancyBboxPatch((7.3, 3.3), 1.4, 1.1, boxstyle="round,pad=0.05",
                            facecolor='#FFD966', edgecolor='black', linewidth=1.0)
ax.add_patch(deep_conv1)
ax.text(8.0, 3.85, '深层\n卷积', fontsize=8.5, ha='center', va='center')

# 标准卷积 (中)
deep_conv2 = FancyBboxPatch((7.3, 5.1), 1.4, 1.1, boxstyle="round,pad=0.05",
                            facecolor='#FFD966', edgecolor='black', linewidth=1.0)
ax.add_patch(deep_conv2)
ax.text(8.0, 5.65, '标准\n卷积', fontsize=8.5, ha='center', va='center')

# 标准卷积 (上)
deep_conv3 = FancyBboxPatch((7.3, 6.9), 1.4, 1.1, boxstyle="round,pad=0.05",
                            facecolor='#FFD966', edgecolor='black', linewidth=1.0)
ax.add_patch(deep_conv3)
ax.text(8.0, 7.45, '标准\n卷积', fontsize=8.5, ha='center', va='center')

# 残差连接标签
ax.text(8.0, 6.55, '残差连接', fontsize=8, ha='center', color='red', weight='bold')

# ==================== 绘制高分辨率重建模块 ====================

# 重建卷积
recon_conv = FancyBboxPatch((13.1, 6.5), 1.6, 1.3, boxstyle="round,pad=0.05",
                            facecolor='#A8E6A8', edgecolor='black', linewidth=1.0)
ax.add_patch(recon_conv)
ax.text(13.9, 7.15, '重建\n卷积', fontsize=8.5, ha='center', va='center')

# Pixel Shuffle ×2
upsample_box = FancyBboxPatch((13.1, 4.6), 1.6, 1.3, boxstyle="round,pad=0.05",
                              facecolor='#7DD87D', edgecolor='black', linewidth=1.0)
ax.add_patch(upsample_box)
ax.text(13.9, 5.25, 'Pixel\nShuffle\n×2', fontsize=8.5, ha='center', va='center')

# ==================== 绘制输出图像 ====================

output_img = patches.Rectangle((15.5, 6.5), 2.0, 2.0, linewidth=1.5,
                               facecolor='white', edgecolor='black')
ax.add_patch(output_img)
ax.text(16.5, 7.5, '输出\n高分辨率\nCT图像', fontsize=9, ha='center', va='center')

# ==================== 绘制连接箭头 ====================

# 输入到第一个小波卷积
ax.annotate('', xy=(2.9, 7.9), xytext=(2.7, 7.5),
            arrowprops=dict(arrowstyle="->", lw=1.5, color='black'))

# 小波卷积 (上) -> 小波卷积 (下)
ax.annotate('', xy=(3.7, 6.2), xytext=(3.7, 7.3),
            arrowprops=dict(arrowstyle="->", lw=1.5, color='black'))

# 小波卷积 (下) -> DWT
ax.annotate('', xy=(4.7, 5.8), xytext=(4.5, 5.6),
            arrowprops=dict(arrowstyle="->", lw=1.5, color='black'))

# DWT -> 深层卷积 (下)
ax.annotate('', xy=(7.3, 3.85), xytext=(5.7, 5.8),
            arrowprops=dict(arrowstyle="->", lw=1.5, color='black'))

# 深层卷积 (下) -> 标准卷积 (中)
ax.annotate('', xy=(8.0, 5.1), xytext=(8.0, 4.4),
            arrowprops=dict(arrowstyle="->", lw=1.5, color='black'))

# 标准卷积 (中) -> 标准卷积 (上)
ax.annotate('', xy=(8.0, 6.9), xytext=(8.0, 6.2),
            arrowprops=dict(arrowstyle="->", lw=1.5, color='black'))

# 标准卷积 (上) -> 重建卷积
ax.annotate('', xy=(13.1, 7.15), xytext=(8.7, 7.45),
            arrowprops=dict(arrowstyle="->", lw=1.5, color='black'))

# 重建卷积 -> Pixel Shuffle
ax.annotate('', xy=(13.9, 5.9), xytext=(13.9, 6.5),
            arrowprops=dict(arrowstyle="->", lw=1.5, color='black'))

# Pixel Shuffle -> 输出
ax.annotate('', xy=(15.5, 7.5), xytext=(14.7, 5.25),
            arrowprops=dict(arrowstyle="->", lw=1.5, color='black'))

# ==================== 绘制残差连接 (红色虚线弧) ====================

# 上方残差弧：从输入区域绕过顶部到重建卷积
residual_arc1 = patches.FancyArrowPatch((2.5, 8.3), (13.1, 7.5),
                                        connectionstyle="arc3,rad=-0.25",
                                        arrowstyle="->", lw=2.0,
                                        color='red', alpha=0.8,
                                        linestyle='--')
ax.add_patch(residual_arc1)

# 下方残差弧：从浅层卷积到重建
residual_arc2 = patches.FancyArrowPatch((3.0, 4.9), (13.5, 5.0),
                                        connectionstyle="arc3,rad=0.25",
                                        arrowstyle="->", lw=2.0,
                                        color='red', alpha=0.8,
                                        linestyle='--')
ax.add_patch(residual_arc2)

# ==================== 添加图例 ====================

# 图例色块
legend_items = [
    ('#A8D8EA', '轻量化小波卷积'),
    ('#F7B7C7', 'DWT分解'),
    ('#FFD966', '标准卷积'),
    ('#A8E6A8', '重建模块'),
]

legend_x_start = 6.0
legend_y = 1.4
box_w, box_h = 0.35, 0.22

# 第一行：4个色块
for i, (color, label) in enumerate(legend_items):
    x = legend_x_start + i * 1.6
    rect = patches.Rectangle((x, legend_y), box_w, box_h,
                             facecolor=color, edgecolor='black', linewidth=0.8)
    ax.add_patch(rect)
    ax.text(x + box_w + 0.1, legend_y + box_h / 2, label,
            fontsize=8.5, va='center')

# 第二行：箭头说明
# 黑色实线箭头
ax.annotate('', xy=(6.3, 0.8), xytext=(5.9, 0.8),
            arrowprops=dict(arrowstyle="->", lw=1.5, color='black'))
ax.text(6.5, 0.8, '主要数据流', fontsize=8.5, va='center')

# 红色虚线箭头
ax.annotate('', xy=(10.0, 0.8), xytext=(9.6, 0.8),
            arrowprops=dict(arrowstyle="->", lw=2.0, color='red',
                            linestyle='--', alpha=0.8))
ax.text(10.2, 0.8, '残差连接', fontsize=8.5, va='center')

# ==================== 添加标题 ====================

ax.text(9.0, 10.8, 'LUMWCNN-CPU 医学影像超分辨率重建模型架构图',
        fontsize=17, ha='center', weight='bold')

ax.text(9.0, 10.35,
        '(浅层特征提取 → 深层特征映射 → 高分辨率重建)',
        fontsize=11, ha='center', style='italic', color='#555555')

# ==================== 保存图像 ====================

model_architecture = 'model_architecture.png'
plt.tight_layout()
plt.savefig(model_architecture, dpi=200, bbox_inches='tight')
print(model_architecture)
plt.show()
