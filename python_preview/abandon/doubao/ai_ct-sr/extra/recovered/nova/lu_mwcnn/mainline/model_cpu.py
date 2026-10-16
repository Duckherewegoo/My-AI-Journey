# 反编译源文件: /home/dake/Documents/Projects/Graduction_Projects/codes/nova/lu_mwcnn/mainline/__pycache__/model_cpu.cpython-311.pyc
# 生成时间: 2026-09-14 16:06:15.183846
# ============================================================================

# Source Generated with Decompyle++
# File: model_cpu.cpython-311.pyc (Python 3.11)

import torch
from torch.nn import nn

functional
<NODE:12> = None

class IWT_Haar(nn.Module):
    
    def forward(self, x):
        (B, C, H, W) = x.shape
        x = x.view(B, C // 4, 2, 2, H, W)
        x = x.permute(0, 1, 4, 2, 5, 3).contiguous()
        return x.view(B, C // 4, H * 2, W * 2)



class Conv2d(nn.Module):
    pass
# WARNING: Decompyle incomplete


class LUMWCNN_CPU(nn.Module):
    pass
# WARNING: Decompyle incomplete

