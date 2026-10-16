"""LU-MWCNN 主模型（论文版）"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from wavelet import DWT_Haar, IWT_Haar


class Convd(nn.Module):
    """Conv2d + (Dropout) + (ReLU)"""
    def __init__(self, in_ch, out_ch, kernel_size, act=True, dropout=0.1):
        super().__init__()
        layers = [nn.Conv2d(in_ch, out_ch, kernel_size,
                            padding=kernel_size // 2)]
        if dropout > 0.0:
            layers.append(nn.Dropout2d(dropout))
        if act:
            layers.append(nn.ReLU())
        self.model = nn.Sequential(*layers)

    def forward(self, x):
        return self.model(x)


class LUMWCNN(nn.Module):
    """Lite U-Net with Mixed Wavelet Convolution"""

    def __init__(self, in_channels=1, scale=4, dropout=0.1,
                 with_upsample=True):
        super().__init__()
        assert in_channels in (1, 3)
        self.in_channels = in_channels
        self.scale = scale
        self.with_upsample = with_upsample

        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

        # 编码器
        self.l_conv1 = nn.Sequential(
            Convd(in_channels, 64, 3, dropout=dropout),
            Convd(64, 64, 3, dropout=dropout))
        self.l_conv2 = nn.Sequential(
            Convd(256, 128, 3, dropout=dropout),
            Convd(128, 128, 3, dropout=dropout))
        self.l_conv3 = nn.Sequential(
            Convd(512, 256, 3, dropout=dropout),
            Convd(256, 256, 3, dropout=dropout))

        # 解码器
        self.r_conv3 = nn.Sequential(
            Convd(256, 256, 3, dropout=dropout),
            Convd(256, 512, 3, dropout=dropout))
        self.r_conv2 = nn.Sequential(
            Convd(128, 128, 3, dropout=dropout),
            Convd(128, 256, 3, dropout=dropout))
        self.r_conv1 = nn.Sequential(
            Convd(64, 64, 3, dropout=dropout),
            Convd(64, in_channels, 3, dropout=0.0))

        # 输出上采样（灰度版需要）
        if with_upsample:
            self.upsample = nn.Sequential(
                nn.Conv2d(in_channels, in_channels * 4, 3, 1, 1),
                nn.PixelShuffle(2),
                nn.Conv2d(in_channels, in_channels * 4, 3, 1, 1),
                nn.PixelShuffle(2))
        else:
            self.upsample = None

        self.pads = []

    def _align_tensor_size(self, a, b):
        h = min(a.shape[2], b.shape[2])
        w = min(a.shape[3], b.shape[3])
        return a[:, :, :h, :w], b[:, :, :h, :w]

    def wavelet_pad(self, x):
        ph = 1 if x.shape[-2] % 2 != 0 else 0
        pw = 1 if x.shape[-1] % 2 != 0 else 0
        self.pads.append([pw, ph])
        return F.pad(x, (0, pw, 0, ph), mode="constant", value=0)

    def wavelet_shave(self, x):
        if not self.pads:
            return x
        pw, ph = self.pads.pop()
        if ph:
            x = x[..., :-1, :]
        if pw:
            x = x[..., :-1]
        return x

    def forward(self, x):
        x_l1 = self.l_conv1(x)
        x_l2 = self.l_conv2(self.DWT(self.wavelet_pad(x_l1)))
        x_l3 = self.l_conv3(self.DWT(self.wavelet_pad(x_l2)))

        x_r3 = self.wavelet_shave(self.IWT(self.r_conv3(x_l3)))
        x_r3, x_l2 = self._align_tensor_size(x_r3, x_l2)
        x_r3 = x_r3 + x_l2

        x_r2 = self.wavelet_shave(self.IWT(self.r_conv2(x_r3)))
        x_r2, x_l1 = self._align_tensor_size(x_r2, x_l1)
        x_r2 = x_r2 + x_l1

        x_r1 = self.r_conv1(x_r2)
        x_r1, x = self._align_tensor_size(x_r1, x)
        x_r1 = x_r1 + x

        y = self.upsample(x_r1) if self.upsample is not None else x_r1
        y = (y - y.min()) / (y.max() - y.min() + 1e-8)
        return torch.clamp(y, 0.0, 1.0)
