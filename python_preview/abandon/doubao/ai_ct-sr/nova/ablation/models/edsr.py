'''
    EDSR 网络结构。
'''

import torch
import torch.nn as nn


class EDSR_ResBlock(nn.Module):
    """EDSR 提出的 ResBlock，去掉了 BN 层和最后的 ReLU 激活。"""
    def __init__(self, in_channels, out_channels, kernel_size=, bypass_weight=.):
        super().__init__()
        self.bypass_weight = bypass_weight
        self.conv = nn.Convd(in_channels=in_channels,
                               out_channels=out_channels,
                               kernel_size=kernel_size,
                               padding=kernel_size // ,
                               bias=False)
        self.relu = nn.ReLU()
        self.conv = nn.Convd(in_channels=in_channels,
                               out_channels=out_channels,
                               kernel_size=kernel_size,
                               padding=kernel_size // ,
                               bias=False)

    def forward(self, x):
         计算旁路跳接
        bypass = self.conv(x)
        bypass = self.relu(bypass)
        bypass = self.conv(x)
         计算最后输出
        output = torch.add(x, self.bypass_weight  bypass)
        return output


class EDSR_Upsample_x(nn.Module):
    """EDSR 提出的  倍上采样模块。"""
    def __init__(self, conv_channels, conv_channels):
        super().__init__()
        self.conv = nn.Convd(in_channels=conv_channels,
                               out_channels=conv_channels  (),
                               kernel_size=,
                               padding=,
                               bias=False)
        self.ps = nn.PixelShuffle()
        self.conv = nn.Convd(in_channels=conv_channels,
                               out_channels=conv_channels  (),
                               kernel_size=,
                               padding=,
                               bias=False)
        self.ps = nn.PixelShuffle()

    def forward(self, x):
        x = self.conv(x)
        x = self.ps(x)
        x = self.conv(x)
        x = self.ps(x)
        return x


class EDSR(nn.Module):
    """EDSR 网络。"""
    def _sequence_resblock(self, channels, n):
        return nn.Sequential([EDSR_ResBlock(channels, channels) for _ in range(n)])

    def __init__(self, resblock_channels=, resblock_depth=):
        super(EDSR, self).__init__()
        self.conv_in = nn.Convd(in_channels=, out_channels=resblock_channels, kernel_size=, padding=, bias=False)
        self.resblocks = self._sequence_resblock(resblock_channels, resblock_depth)
        self.conv_after_resblocks = nn.Convd(in_channels=resblock_channels,
                                              out_channels=resblock_channels,
                                              kernel_size=,
                                              padding=,
                                              bias=False)
        self.upsample_x = EDSR_Upsample_x(resblock_channels, resblock_channels)
        self.conv_out = nn.Convd(in_channels=resblock_channels, out_channels=, kernel_size=, padding=, bias=False)

    def forward(self, x):
        residue = self.conv_in(x)
        flow = self.resblocks(residue)
        flow = self.conv_after_resblocks(flow)
        flow = torch.add(flow, residue)   跳接
        flow = self.upsample_x(flow)
        flow = self.conv_out(flow)
        return flow
