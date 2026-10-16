"""
    WaveletUNet 网络结构。（消融实验）
    3 层编码器 + 3 层解码器 + Haar 小波变换替代池化/上采样
"""

from base.utils.wavelet import DWT_Haar, IWT_Haar
import torch.nn.functional as F
import torch.nn as nn
import sys
import os.path as path

dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__, '../../baselines'))


class Convd(nn.Module):
    """Conv2d + 可选 ReLU 的封装，padding 自动保持空间尺寸"""
    def __init__(self, in_ch, out_ch, kernel_size, act=True) -> None:
        super(Convd, self).__init__()
        self.layers = [
            nn.Conv2d(in_ch, out_ch,
                      kernel_size=kernel_size,
                      padding=kernel_size // 2),
        ]
        if act:
            self.layers.append(nn.ReLU())
        self.layers = nn.Sequential(*self.layers)

    def forward(self, x):
        return self.layers(x)


class LUMWCNN_ABTEST(nn.Module):
    """消融实验版：3 层 Wavelet-UNet"""

    def __init__(self) -> None:
        super(LUMWCNN_ABTEST, self).__init__()

        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

        # ===== 编码器（下采样路径）=====
        # 输入 3 通道 (RGB)，第 1 层输出 16 通道
        self.l_conv1 = nn.Sequential(
            Convd(3, 16, 3), Convd(16, 16, 3))
        # DWT 后: 16 -> 64 通道
        self.l_conv2 = nn.Sequential(
            Convd(64, 32, 3), Convd(32, 32, 3))
        # DWT 后: 32 -> 128 通道
        self.l_conv3 = nn.Sequential(
            Convd(128, 64, 3), Convd(64, 64, 3))

        # ===== 解码器（上采样路径，对称结构）=====
        # 为 IWT 做准备: 64 -> 128 通道
        self.r_conv1 = nn.Sequential(
            Convd(64, 128, 3), Convd(128, 128, 3))
        # IWT 后: 128 -> 32 通道
        self.r_conv2 = nn.Sequential(
            Convd(32, 64, 3), Convd(64, 64, 3))
        # IWT 后: 64 -> 16 通道，最后输出 3 通道
        self.r_conv3 = nn.Sequential(
            Convd(16, 3, 3))

        self.valing = False
        self.pads = []

    def forward(self, x):
        self.print_shape(x, 'Input')

        # ===== 编码器 =====
        x_l1 = self.l_conv1(x)                     # 3 -> 16
        self.print_shape(x_l1, 'After l_conv1')

        x_l1_pad = self.wavelet_pad(x_l1)
        x_l2 = self.l_conv2(self.DWT(x_l1_pad))    # 16 -> 64 -> 32
        self.print_shape(x_l2, 'After l_conv2')

        x_l2_pad = self.wavelet_pad(x_l2)
        x_l3 = self.l_conv3(self.DWT(x_l2_pad))    # 32 -> 128 -> 64
        self.print_shape(x_l3, 'After l_conv3')

        # ===== 解码器（含 skip connection）=====
        _after_r_conv = self.r_conv1(x_l3)         # 64 -> 128
        self.print_shape(_after_r_conv, 'After r_conv1')

        lhs = self.IWT(_after_r_conv)              # 128 -> 32
        self.print_shape(lhs, 'IWT lhs')

        lhs_shave = self.wavelet_shave(lhs)
        x_r = lhs_shave + x_l2                     # skip from x_l2
        self.print_shape(x_r, 'x_r = lhs_shave + x_l2')

        _after_r_conv = self.r_conv2(x_r)          # 32 -> 64
        _x_r = self.IWT(_after_r_conv)             # 64 -> 16
        self.print_shape(_x_r, 'IWT _x_r')

        x_r = self.wavelet_shave(_x_r) + x_l1      # skip from x_l1
        self.print_shape(x_r, 'x_r after skip2')

        x_r = self.r_conv3(x_r) + x                # 16 -> 3，全局残差

        return x_r

    def print_shape(self, x, desc):
        """调试打印（默认关闭）"""
        if not self.valing:
            return
        print('\n--------------------------------------')
        print('\n|-- Tensor: {}  /  Shape: {}'.format(desc, x.shape))
        print('\n--------------------------------------')

    def wavelet_pad(self, x):
        """DWT 前把 H, W 填充到偶数（Haar 要求）"""
        # 检查 H, W 是否为偶数
        should_pad_h = x.shape[-2] % 2 != 0
        should_pad_w = x.shape[-1] % 2 != 0
        # 左右上下各填 1 或 0
        padding = (
            1 if should_pad_w else 0,   # left
            1 if should_pad_w else 0,   # right
            1 if should_pad_h else 0,   # top
            1 if should_pad_h else 0,   # bottom
        )
        self.pads.append([should_pad_w, should_pad_h])
        return F.pad(x, padding, 'constant', 0)

    def wavelet_shave(self, x):
        """IWT 后把填充去掉，恢复原始尺寸"""
        should_shave_w, should_shave_h = self.pads.pop()
        if should_shave_w:
            x = x[:, :, :, :-1]
        if should_shave_h:
            x = x[:, :, :-1, :]
        return x


if __name__ == "__main__":
    print(LUMWCNN_ABTEST())
