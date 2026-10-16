# 反编译源文件: /home/dake/Documents/Projects/Graduction_Projects/codes/base/datasets/__pycache__/deeplesion.cpython-311.pyc
# 生成时间: 2026-09-14 16:06:15.130445
# ============================================================================

# Source Generated with Decompyle++
# File: deeplesion.cpython-311.pyc (Python 3.11)

'''
    DeepLesion 数据集接口（医学图像超分辨率）
'''
import torch
from torchvision.transforms import transforms
from torchvision.transforms import InterpolationMode
from torch.utils.data.dataset import Dataset
from PIL import Image, UnidentifiedImageError
import os
from typing import Tuple, Union

class AddGaussianNoise:
    
    def __init__(self, sigma, prob = (0.1, 1)):
        self.sigma = sigma
        self.prob = prob

    
    def __call__(self, img):
        if torch.rand(1) < self.prob:
            noise = torch.randn_like(img) * self.sigma
            img = img + noise
            img = torch.clamp(img, 0, 1)
        return img



class DeepLesionDataset(Dataset):
    pass
# WARNING: Decompyle incomplete

