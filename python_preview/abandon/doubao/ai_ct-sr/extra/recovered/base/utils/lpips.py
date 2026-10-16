# 反编译源文件: /home/dake/Documents/Projects/Graduction_Projects/codes/base/utils/__pycache__/lpips.cpython-311.pyc
# 生成时间: 2026-09-14 16:06:15.156292
# ============================================================================

# Source Generated with Decompyle++
# File: lpips.cpython-311.pyc (Python 3.11)

'''
    自然图像感知损失计算
'''
from lpips import LPIPS
lpips = LPIPS(net = 'vgg')
lpips.eval()

def calc_lpips(img1, img2):
    return lpips(img1, img2).detach().cpu().squeeze().mean()

