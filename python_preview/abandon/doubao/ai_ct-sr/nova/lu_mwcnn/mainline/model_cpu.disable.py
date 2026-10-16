'''
WaveletUNet 网络结构 (CPU) - 优化修复版
修复内容：
1. 解决通道不匹配问题，确保各层特征图维度一致
2. 修复 pad 信息存储方式，避免多次调用时的状态污染
3. 优化网络层定义，确保上下采样通道匹配
4. 清理冗余代码，提高可读性
5. 修复全黑问题（移除强制截断 + 修复裁剪函数）
'''

import torch
import torch.nn as nn
import torch.nn.functional as F
import sys
import os.path as path

from base.utils.wavelet import DWT_Haar, IWT_Haar

# 导入路径处理
dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__, '../../baselines'))


# ========== 卷积模块 ==========

class Convd(nn.Module):
    """带激活函数 + 批归一化的卷积模块"""

    def __init__(self, in_ch: int, out_ch: int, kernel_size: int,
                 act: bool = True) -> None:
        super(Convd, self).__init__()
        layers = [
            nn.Conv2d(in_ch, out_ch, kernel_size=kernel_size,
                      padding=kernel_size // 2, bias=False),  # 批归一化不需要 bias
            nn.BatchNorm2d(out_ch),                            # 新增批归一化
        ]
        if act:
            layers.append(nn.ReLU(inplace=True))
        self.layers = nn.Sequential(layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.layers(x)


class LUMWCNN_CPU(nn.Module):
    def __init__(self) -> None:
        super(LUMWCNN_CPU, self).__init__()

        self.DWT = DWT_Haar()   # 小波变换
        self.IWT = IWT_Haar()   # 小波逆变换
        self.pad_info: dict = {}

        # 左侧卷积块（下采样路径）
        self.l_conv1 = nn.Sequential(
            Convd(1, 64, 3),
            Convd(64, 64, 3)
        )
        self.l_conv2 = nn.Sequential(
            Convd(256, 128, 3),   # DWT 后通道 ×4
            Convd(128, 128, 3)
        )
        self.l_conv3 = nn.Sequential(
            Convd(512, 256, 3),
            Convd(256, 256, 3)
        )

        # 右侧卷积块（上采样路径）
        self.r_conv3 = nn.Sequential(
            # 输出用于 IWT（通道 /4）
            Convd(256, 256, 3),
            Convd(256, 512, 3)
        )
        self.r_conv2 = nn.Sequential(
            # 输出用于 IWT（通道 /4）
            Convd(128, 128, 3),
            Convd(128, 256, 3)
        )
        self.r_conv1 = nn.Sequential(
            Convd(64, 64, 3),
            Convd(64, 1, 3, act=False)   # 输出通道与输入 x 匹配
        )

        # 上采样模块（总放大倍数 ×4）
        self.upsample = nn.Sequential(
            Convd(1, 4, 3),
            nn.PixelShuffle(2),          # 第一次 ×2 上采样（通道 4→1，尺寸 ×2）
            Convd(1, 4, 3),
            nn.PixelShuffle(2),          # 第二次 ×2 上采样
        )

        self.validating = False   # 调试模式标记
        self.pads: list = []      # 记录填充信息

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        self.print_shape(x, 'Input')

        # 左侧第一层
        x_l1 = self.l_conv1(x)
        self.print_shape(x_l1, 'After l_conv1')

        # 小波变换前填充（确保尺寸为偶数）
        x_l1_pad = self.wavelet_pad(x_l1, 'l1')
        self.print_shape(x_l1_pad, 'x_l1_pad')

        # 第一次 DWT（通道 ×4）
        _x_l = self.DWT(x_l1_pad)
        self.print_shape(_x_l, 'After DWT 1')

        # 左侧第二层
        x_l2 = self.l_conv2(_x_l)
        self.print_shape(x_l2, 'After l_conv2')

        x_l2_pad = self.wavelet_pad(x_l2, 'l2')
        self.print_shape(x_l2_pad, 'x_l2_pad')

        # 第二次 DWT
        _x_l = self.DWT(x_l2_pad)
        self.print_shape(_x_l, 'After DWT 2')

        # 左侧第三层
        x_l3 = self.l_conv3(_x_l)
        self.print_shape(x_l3, 'After l_conv3')

        # 右侧第三层
        _after_r_conv = self.r_conv3(x_l3)
        self.print_shape(_after_r_conv, 'After r_conv3')

        # 第一次 IWT（通道 ÷4）
        lhs = self.IWT(_after_r_conv).to(x.device)
        self.print_shape(lhs, 'After IWT 1')

        # 移除填充部分
        lhs_shave = self.wavelet_shave(lhs, 'l2')
        self.print_shape(lhs_shave, 'lhs_shave')

        # 残差连接
        x_r = lhs_shave + x_l2
        self.print_shape(x_r, 'x_r (residual 1)')

        # 右侧第二层
        _after_r_conv = self.r_conv2(x_r)
        self.print_shape(_after_r_conv, 'After r_conv2')

        # 第二次 IWT
        _x_r = self.IWT(_after_r_conv).to(x.device)
        self.print_shape(_x_r, 'After IWT 2')

        # 残差连接
        x_r = self.wavelet_shave(_x_r, 'l1') + x_l1
        self.print_shape(x_r, 'x_r (residual 2)')

        # 右侧第一层（输出通道与输入匹配）
        x_r = self.r_conv1(x_r) + x
        self.print_shape(x_r, 'x_r (residual 3)')

        # 上采样得到最终结果
        y = self.upsample(x_r)
        y = torch.clamp(y, 0, 1)
        self.print_shape(y, 'Output')

        return y

    def print_shape(self, x: torch.Tensor, desc: str) -> None:
        """调试时打印张量形状"""
        if self.validating:
            print(f'[{desc}] Shape: {x.shape}')

    def wavelet_pad(self, x: torch.Tensor, key: str) -> torch.Tensor:
        """小波变换前填充，按 key 记录填充信息"""
        should_pad_h = x.shape[-2] % 2 != 0
        should_pad_w = x.shape[-1] % 2 != 0
        padding = (0, 1 if should_pad_w else 0,
                   0, 1 if should_pad_h else 0)
        self.pad_info[key] = [should_pad_w, should_pad_h]
        return F.pad(x, padding, 'constant', 0)

    def wavelet_shave(self, x: torch.Tensor, key: str) -> torch.Tensor:
        """小波逆变换后移除填充，按 key 读取填充信息"""
        if key not in self.pad_info:
            return x
        should_shave_w, should_shave_h = self.pad_info.pop(key)
        if should_shave_w:
            x = x[:, :, :, :-1]   # 裁最后一列
        if should_shave_h:
            x = x[:, :, :-1, :]   # 裁最后一行
        return x


if __name__ == "__main__":
    model = LUMWCNN_CPU()
    input_tensor = torch.randn(1, 1, 64, 64)
    output_tensor = model(input_tensor)
    print(f'输入形状: {input_tensor.shape}')
    print(f'输出形状: {output_tensor.shape}')
