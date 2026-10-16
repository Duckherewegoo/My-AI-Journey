# 反编译源文件: /home/dake/Documents/Projects/Graduction_Projects/codes/base/datasets/__pycache__/deeplesions.cpython-311.pyc
# 生成时间: 2026-09-14 16:06:15.133457
# ============================================================================

# Source Generated with Decompyle++
# File: deeplesions.cpython-311.pyc (Python 3.11)

'''
    DeepLesion 数据集接口（医学图像超分辨率）
    修复点：统一所有阶段返回格式，解决val/test解包错误
    增强版特性：
    1. 统一返回格式：(y_lr, y_hr, filename)（train阶段filename=None）
    2. 适配train/val/test三阶段无缝切换
    3. 增强数据校验与异常兜底
'''
import torch
from torchvision.transforms import transforms
from torch.utils.data.dataset import Dataset
from PIL import Image, ImageEnhance
import os
import numpy as np
import logging
import torch
from torchvision import transforms
from torchvision.transforms import InterpolationMode
from typing import List, Optional, cast, Any
logging.basicConfig(level = logging.INFO)
logger = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')

class DeepLesionDataset(Dataset):
    pass
# WARNING: Decompyle incomplete


class AddGaussianNoise(object):
    
    def __init__(self, std = (0.01,)):
        self.std = std

    
    def __call__(self, img):
        if self.std <= 0:
            return img
        img_np = None.array(img).astype(np.float32)
        noise = np.random.normal(0, self.std, img_np.shape)
        img_np = img_np + noise
        img_np = np.clip(img_np, 0, 255).astype(np.uint8)
        return Image.fromarray(img_np)

    
    def __repr__(self):
        return self.__class__.__name__ + '(std={0})'.format(self.std)


