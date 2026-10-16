'''
WaveletUNet 网络结构 (CPU) - 优化修复版
修复内容：
. 解决通道不匹配问题，确保各层特征图维度一致
. 修复pad信息存储方式，避免多次调用时的状态污染
. 优化网络层定义，确保上下采样通道匹配
. 清理冗余代码，提高可读性
'''

import torch
from base.utils.wavelet import DWT_Haar, IWT_Haar
import sys
import os.path as path
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Union   导入类型提示所需模块

 导入路径处理
dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__, '../../baselines'))


 修复类名与nn.Convd冲突导致的类型检查错误

 ========== 卷积模块 ==========

class Convd(nn.Module):
    """带Dropout和ReLU的卷积模块"""

    def __init__(
        self,
        in_ch: int,
        out_ch: int,
        kernel_size: int,
        act: bool = True,
        dropout: float = .,
    ) -> None:
        super(Convd, self).__init__()
        layer_list = [
            nn.Convd(in_ch, out_ch, kernel_size, padding=kernel_size // )
        ]   原代码padding正确，保留
        if dropout > :
            layer_list.append(nn.Dropoutd(dropout))
        if act:
            layer_list.append(nn.ReLU())
        self.model = nn.Sequential(layer_list)

    def forward(self, x):
        return self.model(x)


class LUMWCNN_CPU(nn.Module):
    """LUMWCNN主模型：基于小波变换的超分网络（修复版）"""

    def __init__(
        self, in_channels: int = , device=None, scale=, dropout: float = .
    ) -> None:
        super(LUMWCNN_CPU, self).__init__()
        self.device = device
        self.in_channels = in_channels
        self.scale = scale
        assert self.in_channels in [, ], "in_channels仅支持/"

         小波变换层
        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

         左侧编码路径
        self.l_conv = nn.Sequential(
            Convd(self.in_channels, , , dropout=dropout),
            Convd(, , , dropout=dropout),
        )
        self.l_conv = nn.Sequential(
            Convd(, , , dropout=dropout),     =
            Convd(, , , dropout=dropout),
        )
        self.l_conv = nn.Sequential(
            Convd(, , , dropout=dropout),     =
            Convd(, , , dropout=dropout),
        )

         右侧解码路径
        self.r_conv = nn.Sequential(
            Convd(, , , dropout=dropout), Convd(, , , dropout=dropout)
        )
        self.r_conv = nn.Sequential(
            Convd(, , , dropout=dropout), Convd(, , , dropout=dropout)
        )
        self.r_conv = nn.Sequential(
            Convd(, , , dropout=dropout),
            Convd(, self.in_channels, , dropout=.),
        )

         上采样模块（PixelShuffle）【关键修复：移除groups参数或设为】
        if self.scale == :
            self.upsample = nn.Sequential(
                nn.Convd(
                    in_channels, in_channels  , , , padding=, groups=
                ),   明确设置groups=
                nn.PixelShuffle(),
            )
        elif self.scale == :
            self.upsample = nn.Sequential(
                nn.Convd(
                    in_channels, in_channels  , , , padding=, groups=
                ),   明确设置groups=
                nn.PixelShuffle(),
                nn.Convd(
                    in_channels, in_channels  , , , padding=, groups=
                ),   明确设置groups=
                nn.PixelShuffle(),
            )

        self.pads = []   记录小波变换的padding信息

    def _align_tensor_size(self, tensor_a, tensor_b):
        """对齐两个张量的尺寸（取最小高宽）"""
        min_h = min(tensor_a.shape[], tensor_b.shape[])
        min_w = min(tensor_a.shape[], tensor_b.shape[])
        return tensor_a[:, :, :min_h, :min_w], tensor_b[:, :, :min_h, :min_w]

    def forward(self, x):
        x = x.to(self.device)
        self.pads = []   清空pads列表

         通道数适配（→ 或 →）—— 原逻辑正确，保留
        if x.shape[] ==  and self.in_channels == :
            x = x.repeat(, , , )
        elif x.shape[] ==  and self.in_channels == :
            x = torch.mean(x, dim=, keepdim=True)

         编码路径（原逻辑正确，保留）
        x_l = self.l_conv(x)
        x_l_pad = self.wavelet_pad(self, x_l)
        _x_l = self.DWT(x_l_pad)
        x_l = self.l_conv(_x_l)
        x_l_pad = self.wavelet_pad(self, x_l)
        _x_l = self.DWT(x_l_pad)
        x_l = self.l_conv(_x_l)

         解码路径（带残差连接）—— 原逻辑正确，保留
        _after_r_conv = self.r_conv(x_l)
        lhs = self.IWT(_after_r_conv)
        lhs_shave = self.wavelet_shave(self, lhs)
        lhs_shave, x_l = self._align_tensor_size(lhs_shave, x_l)
        x_r = lhs_shave + x_l

        _after_r_conv = self.r_conv(x_r)
        _x_r = self.IWT(_after_r_conv)
        _x_r_shave = self.wavelet_shave(self, _x_r)
        _x_r_shave, x_l = self._align_tensor_size(_x_r_shave, x_l)
        x_r = _x_r_shave + x_l

        x_r = self.r_conv(x_r)
        x_r, x = self._align_tensor_size(x_r, x)
        x_r = x_r + x

         上采样+值域约束（关键：保证输出在[,]）
        y = self.upsample(x_r)
        y = torch.clamp(y, ., .)
        return y

    def print_shape(self, x, desc):
        """打印张量形状（验证模式下）"""
        if self.valing:
            print(f'Tensor: {desc}  /  Shape: {x.shape}')

    @staticmethod
    def wavelet_pad(self, x):
        """小波变换前的padding（保证尺寸为的倍数）【修改：修复padding方向】"""
        pad_h =  if x.shape[-] %  !=  else 
        pad_w =  if x.shape[-] %  !=  else 
        self.pads.append([pad_w, pad_h])
         F.pad参数：(left, right, top, bottom) → 改为右侧/底部padding，匹配shave逻辑
        return F.pad(x, (, pad_w, , pad_h), "constant", )

    @staticmethod
    def wavelet_shave(self, x):
        """小波逆变换后的去padding【修改：修复shave方向】"""
        if not self.pads:
            return x
        pad_w, pad_h = self.pads.pop()
         去掉右侧pad_w列、底部pad_h行（对应padding的位置）
        if pad_w:
            x = x[:, :, :, :-pad_w]
        if pad_h:
            x = x[:, :, :-pad_h, :]
        return x


if __name__ == "__main__":
     测试模型输入输出
    model = LUMWCNN_CPU()
    model.valing = True   开启形状打印
    input_tensor = torch.randn(, , , )   批量，通道，x
    output_tensor = model(input_tensor)
    print(f'\n输入形状: {input_tensor.shape}')
    print(f'输出形状: {output_tensor.shape}')
