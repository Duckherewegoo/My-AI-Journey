# 反编译源文件: /home/dake/Documents/Projects/Graduction_Projects/codes/base/utils/__pycache__/collate_fn.cpython-311.pyc
# 生成时间: 2026-09-14 16:06:15.152187
# ============================================================================

# Source Generated with Decompyle++
# File: collate_fn.cpython-311.pyc (Python 3.11)

import torch
from torch.utils.data.dataloader import default_collate

def deeplesion_collate_fn(batch):
    '''
    自定义DataLoader拼接函数：
    1. 自动适配train（2个值）/val/test（3个值）
    2. 过滤None值，确保只拼接张量
    '''
    lr_batch = []
    hr_batch = []
    filename_batch = []
    has_filename = False
# WARNING: Decompyle incomplete

