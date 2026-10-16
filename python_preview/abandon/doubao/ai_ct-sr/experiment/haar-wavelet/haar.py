import os.path as path
dirname__ = path.dirname(path.abspath(__file__))

from PIL import Image
from matplotlib import pyplot as plt
import numpy as np
import pywt

lena_grayscale = Image.open(
    path.join(dirname__, 'lena-grayscale.bmp')
).convert('L')

# ---------- 2D Haar 小波分解 ----------
# dwt2 返回 (cA, (cH, cV, cD))
#   cA: 近似（LL）
#   cH: 水平细节（LH）
#   cV: 垂直细节（HL）
#   cD: 对角细节（HH）
cA, (cH, cV, cD) = pywt.dwt2(lena_grayscale, 'haar')
flat = [cA, cH, cV, cD]

# ---------- 2×2 网格显示 ----------
pos = 221
def imshow(img):
    global pos
    plt.subplot(pos)
    plt.imshow(img, cmap='gray')
    plt.yticks([])
    plt.xticks([])
    pos += 1

list(map(imshow, flat))
plt.show()

# ---------- 保存每个子带 ----------
# 小波系数是 float，可能包含负数，需要先归一化到 [0, 255]
pos = 221
def imwrite(img):
    global pos
    arr = np.array(img, dtype=np.float32)
    arr = arr - arr.min()
    if arr.max() > 0:
        arr = arr / arr.max() * 255.0
    pil = Image.fromarray(arr.astype(np.uint8)).convert('L')
    pil.save(path.join(dirname__, f'subband_{pos}.bmp'))
    pos += 1

list(map(imwrite, flat))
