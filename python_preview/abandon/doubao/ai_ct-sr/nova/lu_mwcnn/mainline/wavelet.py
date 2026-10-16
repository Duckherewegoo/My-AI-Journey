"""Haar 小波正/逆变换（真 Haar，带 +/- 组合）"""
import torch
import torch.nn as nn


def _dwt_haar(x):
    """(B, C, H, W) → (B, 4C, H/2, W/2)"""
    x01 = x[:, :, 0::2, :] / 2
    x02 = x[:, :, 1::2, :] / 2
    x1 = x01[:, :, :, 0::2]
    x2 = x02[:, :, :, 0::2]
    x3 = x01[:, :, :, 1::2]
    x4 = x02[:, :, :, 1::2]
    LL = x1 + x2 + x3 + x4
    HL = -x1 - x2 + x3 + x4
    LH = -x1 + x2 - x3 + x4
    HH = x1 - x2 - x3 + x4
    return torch.cat((LL, HL, LH, HH), 1)


def _iwt_haar(x):
    """(B, 4C, H, W) → (B, C, 2H, 2W)"""
    B, C, H, W = x.size()
    oC = C // 4
    x1 = x[:, 0*oC:1*oC, :, :] / 2
    x2 = x[:, 1*oC:2*oC, :, :] / 2
    x3 = x[:, 2*oC:3*oC, :, :] / 2
    x4 = x[:, 3*oC:4*oC, :, :] / 2
    syn = torch.zeros([B, oC, H*2, W*2], dtype=x.dtype, device=x.device)
    syn[:, :, 0::2, 0::2] = x1 - x2 - x3 + x4
    syn[:, :, 1::2, 0::2] = x1 - x2 + x3 - x4
    syn[:, :, 0::2, 1::2] = x1 + x2 - x3 - x4
    syn[:, :, 1::2, 1::2] = x1 + x2 + x3 + x4
    return syn


class DWT_Haar(nn.Module):
    def forward(self, x):
        return _dwt_haar(x)


class IWT_Haar(nn.Module):
    def forward(self, x):
        return _iwt_haar(x)
