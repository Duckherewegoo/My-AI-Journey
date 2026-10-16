'''
    WaveletUNet 网络结构。（消融实验，NO CUDA）
'''
import os.path as path
import sys

dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__, '../../baselines'))

import torch.nn as nn
import torch.nn.functional as F
from utils.wavelet import DWT_Haar, IWT_Haar    # ← 确认路径，可能应为 base.utils.wavelet


class Convd(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size, act=True) -> None:
        super(Convd, self).__init__()
        self.layers = [
            nn.Conv2d(in_ch, out_ch, kernel_size=kernel_size,
                      padding=kernel_size // 2),
        ]
        if act:
            self.layers.append(nn.ReLU(inplace=True))
        self.layers = nn.Sequential(*self.layers)

    def forward(self, x):
        return self.layers(x)


class LUMWCNN_ABTEST(nn.Module):
    """3 层 Wavelet-UNet（消融版，CPU 兼容，灰度 x4）"""

    def __init__(self, in_channels=1) -> None:
        super(LUMWCNN_ABTEST, self).__init__()

        self.in_channels = in_channels

        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

        # ===== 编码器 =====
        self.l_conv1 = nn.Sequential(
            Convd(in_channels, 64, 3),
            Convd(64, 64, 3))
        self.l_conv2 = nn.Sequential(
            Convd(256, 128, 3),       # DWT 后 64×4=256
            Convd(128, 128, 3))
        self.l_conv3 = nn.Sequential(
            Convd(512, 256, 3),       # DWT 后 128×4=512
            Convd(256, 256, 3))

        # ===== 解码器（命名与 forward 执行顺序反着） =====
        self.r_conv3 = nn.Sequential(
            Convd(256, 256, 3),
            Convd(256, 512, 3))       # 为 IWT 准备 → 512
        self.r_conv2 = nn.Sequential(
            Convd(128, 128, 3),
            Convd(128, 256, 3))       # 为 IWT 准备 → 256
        self.r_conv1 = nn.Sequential(
            Convd(64, 64, 3),
            Convd(64, in_channels, 3))

        self.valing = False
        self.pads = []

    def wavelet_pad(self, x):
        """DWT 前把 H/W 补到偶数"""
        should_pad_h = x.shape[-2] % 2 != 0
        should_pad_w = x.shape[-1] % 2 != 0
        padding = (
            1 if should_pad_w else 0,    # left
            1 if should_pad_w else 0,    # right
            1 if should_pad_h else 0,    # top
            1 if should_pad_h else 0,    # bottom
        )
        self.pads.append([should_pad_w, should_pad_h])
        return F.pad(x, padding, 'constant', 0)

    def wavelet_shave(self, x):
        """IWT 后裁掉补齐部分"""
        should_shave_w, should_shave_h = self.pads.pop()
        if should_shave_w:
            x = x[..., :-1]
        if should_shave_h:
            x = x[..., :-1, :]
        return x

    def forward(self, x):
        # ===== 编码器 =====
        x_l1 = self.l_conv1(x)
        x_l2 = self.l_conv2(self.DWT(self.wavelet_pad(x_l1)))
        x_l3 = self.l_conv3(self.DWT(self.wavelet_pad(x_l2)))

        # ===== 解码器 =====
        # 第一轮：r_conv3 → IWT → skip x_l2
        _after = self.r_conv3(x_l3)
        lhs = self.IWT(_after)
        lhs = self.wavelet_shave(lhs)
        min_h = min(lhs.shape[-2], x_l2.shape[-2])
        min_w = min(lhs.shape[-1], x_l2.shape[-1])
        x_r = lhs[..., :min_h, :min_w] + x_l2[..., :min_h, :min_w]

        # 第二轮：r_conv2 → IWT → skip x_l1
        _after = self.r_conv2(x_r)
        _x_r = self.IWT(_after)
        _x_r = self.wavelet_shave(_x_r)
        min_h = min(_x_r.shape[-2], x_l1.shape[-2])
        min_w = min(_x_r.shape[-1], x_l1.shape[-1])
        x_r = _x_r[..., :min_h, :min_w] + x_l1[..., :min_h, :min_w]

        # 第三轮：r_conv1 → 全局残差
        x_r = self.r_conv1(x_r)
        min_h = min(x_r.shape[-2], x.shape[-2])
        min_w = min(x_r.shape[-1], x.shape[-1])
        x_r = x_r[..., :min_h, :min_w] + x[..., :min_h, :min_w]

        return x_r


if __name__ == "__main__":
    print(LUMWCNN_ABTEST())
