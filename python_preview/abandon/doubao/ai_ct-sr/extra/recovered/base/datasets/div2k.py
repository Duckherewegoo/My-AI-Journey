# 反编译源文件: /home/dake/Documents/Projects/Graduction_Projects/codes/base/datasets/__pycache__/div2k.cpython-311.pyc
# 生成时间: 2026-09-14 16:06:15.136091
# ============================================================================

# Source Generated with Decompyle++
# File: div2k.cpython-311.pyc (Python 3.11)

'''
    DIV2K 数据集接口（自然图像超分辨率）。
'''
from torchvision.transforms import transforms
from torch.utils.data.dataset import Dataset
from PIL import Image
import os
import numpy as np
from base.utils.transforms import AddGaussianNoise
from torchvision.transforms import InterpolationMode

class DIV2KDataset(Dataset):
    pass
# WARNING: Decompyle incomplete

