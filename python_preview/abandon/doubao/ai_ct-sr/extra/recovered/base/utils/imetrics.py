# 反编译源文件: /home/dake/Documents/Projects/Graduction_Projects/codes/base/utils/__pycache__/imetrics.cpython-311.pyc
# 生成时间: 2026-09-14 16:06:15.154341
# ============================================================================

# Source Generated with Decompyle++
# File: imetrics.cpython-311.pyc (Python 3.11)

import torch
import numpy as np
from skimage.metrics import structural_similarity, peak_signal_noise_ratio

def calc_ssim_torch(img1, img2):
    '''
    修复SSIM计算的窗口尺寸问题：
    1. 动态调整win_size，确保不超过图像最小尺寸
    2. 显式指定通道维度，避免维度误判
    3. 尺寸检查，小于3x3时直接返回0（避免极端情况）
    '''
    img1_np = img1.detach().cpu().numpy()
    img2_np = img2.detach().cpu().numpy()
    if img1_np.ndim == 4:
        img1_np = img1_np.squeeze(0)
        img2_np = img2_np.squeeze(0)
    if img1_np.shape[0] == 1:
        img1_np = img1_np.squeeze(0)
        img2_np = img2_np.squeeze(0)
        channel_axis = None
    else:
        channel_axis = 0
    min_size = min(img1_np.shape[-2], img1_np.shape[-1])
    if min_size < 3:
        return 0
    win_size = None(7, min_size)
    if win_size % 2 == 0:
        win_size -= 1
    ssim = structural_similarity(img1_np, img2_np, data_range = 1, win_size = win_size, channel_axis = channel_axis, gaussian_weights = True, sigma = 1.5, use_sample_covariance = False)
    return ssim


def calc_psnr_torch(img1, img2):
    '''计算PSNR，添加尺寸检查'''
    if img1.shape != img2.shape:
        min_h = min(img1.shape[-2], img2.shape[-2])
        min_w = min(img1.shape[-1], img2.shape[-1])
        img1 = img1[(..., :min_h, :min_w)]
        img2 = img2[(..., :min_h, :min_w)]
    mse = torch.mean((img1 - img2) ** 2)
    if mse == 0:
        return float('inf')
    max_pixel = None
    psnr = 20 * torch.log10(max_pixel / torch.sqrt(mse))
    return psnr.item()


def calc_psnr(img1, img2):
    '''计算 PSNR。参数为 np.array，范围在 [0, 255] 或 [0, 1]'''
    return peak_signal_noise_ratio(img1, img2)


def calc_ssim(img1, img2):
    '''计算 SSIM。参数为 np.array，范围在 [0, 255] 或 [0, 1]'''
    return structural_similarity(img1, img2)

