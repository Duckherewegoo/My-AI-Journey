"""
    EDSR 网络结构。（增强深度残差网络，灰度版 x4）
"""
import torch
import torch.nn as nn


class EDSR_ResBlock(nn.Module):
    """EDSR 提出的 ResBlock：Conv-ReLU-Conv，去掉 BN，最后不加激活"""

    def __init__(self, in_channels, out_channels,
                 kernel_size=3, bypass_weight=1.0):
        super().__init__()
        self.bypass_weight = bypass_weight
        self.conv1 = nn.Conv2d(in_channels=in_channels,
                               out_channels=out_channels,
                               kernel_size=kernel_size,
                               padding=kernel_size // 2,
                               bias=False)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = nn.Conv2d(in_channels=in_channels,
                               out_channels=out_channels,
                               kernel_size=kernel_size,
                               padding=kernel_size // 2,
                               bias=False)

    def forward(self, x):
        bypass = self.conv1(x)
        bypass = self.relu(bypass)
        bypass = self.conv2(bypass)
        output = torch.add(x, self.bypass_weight * bypass)
        return output


class EDSR_Upsample_4x(nn.Module):
    """EDSR 提出的 4 倍上采样模块：两次 Conv + PixelShuffle(2)"""

    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels=in_channels,
                               out_channels=out_channels * (2 ** 2),   # 64 → 256
                               kernel_size=3,
                               padding=1,
                               bias=False)
        self.ps1 = nn.PixelShuffle(2)
        self.conv2 = nn.Conv2d(in_channels=out_channels,
                               out_channels=out_channels * (2 ** 2),   # 64 → 256
                               kernel_size=3,
                               padding=1,
                               bias=False)
        self.ps2 = nn.PixelShuffle(2)

    def forward(self, x):
        x = self.conv1(x)
        x = self.ps1(x)
        x = self.conv2(x)
        x = self.ps2(x)
        return x


class EDSR(nn.Module):
    """EDSR 网络（单尺度 x4，灰度）"""

    def _sequence_resblock(self, channels, n):
        return nn.Sequential(
            *[EDSR_ResBlock(channels, channels) for _ in range(n)]
        )

    def __init__(self, resblock_channels=64, resblock_depth=16,
                 in_channels=1, out_channels=1):
        super().__init__()
        self.conv_in = nn.Conv2d(in_channels=in_channels,
                                 out_channels=resblock_channels,
                                 kernel_size=3, padding=1, bias=False)
        self.resblocks = self._sequence_resblock(resblock_channels, resblock_depth)
        self.conv_after_resblocks = nn.Conv2d(in_channels=resblock_channels,
                                              out_channels=resblock_channels,
                                              kernel_size=3, padding=1, bias=False)
        self.upsample_4x = EDSR_Upsample_4x(resblock_channels, resblock_channels)
        self.conv_out = nn.Conv2d(in_channels=resblock_channels,
                                  out_channels=out_channels,
                                  kernel_size=3, padding=1, bias=False)

    def forward(self, x):
        residue = self.conv_in(x)
        flow = self.resblocks(residue)
        flow = self.conv_after_resblocks(flow)
        flow = torch.add(flow, residue)      # 全局跳接
        flow = self.upsample_4x(flow)
        flow = self.conv_out(flow)
        return flow
