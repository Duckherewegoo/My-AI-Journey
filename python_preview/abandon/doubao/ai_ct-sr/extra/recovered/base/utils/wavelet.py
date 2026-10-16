# 反编译源文件: /home/dake/Documents/Projects/Graduction_Projects/codes/base/utils/__pycache__/wavelet.cpython-311.pyc
# 生成时间: 2026-09-14 16:06:15.165381
# ============================================================================

# Source Generated with Decompyle++
# File: wavelet.cpython-311.pyc (Python 3.11)

'''
    Haar 小波变换
    https://github.com/lpj0/MWCNN_PyTorch/blob/master/model/common.py
'''
import torch
from torch.nn import nn

def _dwt_haar(x):
    x01 = x[(:, :, 0::2, :)] / 2
    x02 = x[(:, :, 1::2, :)] / 2
    x1 = x01[(:, :, :, 0::2)]
    x2 = x02[(:, :, :, 0::2)]
    x3 = x01[(:, :, :, 1::2)]
    x4 = x02[(:, :, :, 1::2)]
    LL = x1 + x2 + x3 + x4
    HL = (-x1 - x2) + x3 + x4
    LH = (-x1 + x2 - x3) + x4
    HH = (x1 - x2 - x3) + x4
    return torch.cat((LL, HL, LH, HH), 1)


def _iwt_haar(x):
    (in_batch, in_channel, in_h, in_w) = x.size()
    out_batch = in_batch
    out_channel = in_channel // 4
    out_h = in_h * 2
    out_w = in_w * 2
    x1 = x[(:, 0:out_channel, :, :)] / 2
    x2 = x[(:, out_channel:out_channel * 2, :, :)] / 2
    x3 = x[(:, out_channel * 2:out_channel * 3, :, :)] / 2
    x4 = x[(:, out_channel * 3:out_channel * 4, :, :)] / 2
    syn = torch.zeros([
        out_batch,
        out_channel,
        out_h,
        out_w]).float()
    syn[(:, :, 0::2, 0::2)] = (x1 - x2 - x3) + x4
    syn[(:, :, 1::2, 0::2)] = (x1 - x2) + x3 - x4
    syn[(:, :, 0::2, 1::2)] = x1 + x2 - x3 - x4
    syn[(:, :, 1::2, 1::2)] = x1 + x2 + x3 + x4
    return syn


class DWT_Haar(nn.Module):
    pass
# WARNING: Decompyle incomplete


class IWT_Haar(nn.Module):
    pass
# WARNING: Decompyle incomplete

