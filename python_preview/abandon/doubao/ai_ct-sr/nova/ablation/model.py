'''
    WaveletUNet 网络结构。（消融实验）
'''
from base.utils.wavelet import DWT_Haar, IWT_Haar
import torch.nn.functional as F
import torch.nn as nn
import sys
import os.path as path

dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__, '../../baselines'))


class Convd(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size, act=True) -> None:
        super(Convd, self).__init__()
        self.layers = [
            nn.Conv2d(in_ch, out_ch, kernel_size=kernel_size,
                      padding=kernel_size // 2),
        ]
        if act:
            self.layers.append(nn.ReLU(inplace=True))
        self.layers = nn.Sequential(*self.layers)     # ← 加 *，否则传 list 不展开

    def forward(self, x):
        return self.layers(x)


class LUMWCNN_ABTEST(nn.Module):
    """3 层 Wavelet-UNet（消融版，灰度 x4）"""

    def __init__(self, in_channels=1, with_upsample=False) -> None:
        super(LUMWCNN_ABTEST, self).__init__()

        self.in_channels = in_channels
        self.with_upsample = with_upsample

        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

        # ===== 编码器（下采样路径） =====
        # 1 → 64 → 64
        self.l_conv1 = nn.Sequential(
            Convd(in_channels, 64, 3),
            Convd(64, 64, 3))
        # DWT 后: 64 → 256
        self.l_conv2 = nn.Sequential(
            Convd(256, 128, 3),
            Convd(128, 128, 3))
        # DWT 后: 128 → 512
        self.l_conv3 = nn.Sequential(
            Convd(512, 256, 3),
            Convd(256, 256, 3))

        # ===== 解码器（上采样路径，命名与 forward 执行顺序反着） =====
        # forward 里第一个执行，为 IWT 准备: 256 → 512（= 128×4）
        self.r_conv3 = nn.Sequential(
            Convd(256, 256, 3),
            Convd(256, 512, 3))
        # IWT 后: 512 → 128，与 x_l2 对齐；再为下次 IWT 准备: 128 → 256
        self.r_conv2 = nn.Sequential(
            Convd(128, 128, 3),
            Convd(128, 256, 3))
        # IWT 后: 256 → 64，与 x_l1 对齐；最后输出 1 通道
        self.r_conv1 = nn.Sequential(
            Convd(64, 64, 3),
            Convd(64, in_channels, 3))

        # 可选上采样（灰度版若需要直接输出 HR）
        if with_upsample:
            self.upsample = nn.Sequential(
                nn.Conv2d(in_channels, in_channels * 4, 3, 1, 1),
                nn.PixelShuffle(2),
                nn.Conv2d(in_channels, in_channels * 4, 3, 1, 1),
                nn.PixelShuffle(2))
        else:
            self.upsample = None

        self.valing = False
        self.pads = []

    # ==================== 工具 ====================
    def print_shape(self, x, desc):
        """调试打印（默认关闭，valing=True 时开启）"""
        if not self.valing:
            return
        print('\n--------------------------------------')
        print(f'\n|-- Tensor: {desc}  /  Shape: {x.shape}')
        print('\n--------------------------------------')

    def wavelet_pad(self, x):
        """DWT 前把 H/W 补到偶数（Haar 要求）"""
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
        """IWT 后裁掉补齐的部分"""
        should_shave_w, should_shave_h = self.pads.pop()
        if should_shave_w:
            x = x[..., :-1]
        if should_shave_h:
            x = x[..., :-1, :]
        return x

    # ==================== forward ====================
    def forward(self, x):
        self.print_shape(x, 'Input')

        # ===== 编码器 =====
        x_l1 = self.l_conv1(x)                       # (B, 64, H, W)
        self.print_shape(x_l1, 'After l_conv1')

        x_l1_pad = self.wavelet_pad(x_l1)
        _x_l1 = self.DWT(x_l1_pad)                   # (B, 256, H/2, W/2)
        self.print_shape(_x_l1, 'DWT l1')

        x_l2 = self.l_conv2(_x_l1)                   # (B, 128, H/2, W/2)
        self.print_shape(x_l2, 'After l_conv2')

        x_l2_pad = self.wavelet_pad(x_l2)
        _x_l2 = self.DWT(x_l2_pad)                   # (B, 512, H/4, W/4)
        self.print_shape(_x_l2, 'DWT l2')

        x_l3 = self.l_conv3(_x_l2)                   # (B, 256, H/4, W/4)
        self.print_shape(x_l3, 'After l_conv3')

        # ===== 解码器 =====
        # 第一轮：r_conv3 → IWT → skip x_l2
        _after_r_conv = self.r_conv3(x_l3)           # (B, 512, H/4, W/4)
        self.print_shape(_after_r_conv, 'After r_conv3')

        lhs = self.IWT(_after_r_conv)                # (B, 128, H/2, W/2)
        self.print_shape(lhs, 'IWT r3')

        lhs_shave = self.wavelet_shave(lhs)
        # 尺寸对齐（DWT/IWT 可能因 pad 有 1 像素误差）
        min_h = min(lhs_shave.shape[-2], x_l2.shape[-2])
        min_w = min(lhs_shave.shape[-1], x_l2.shape[-1])
        lhs_shave = lhs_shave[..., :min_h, :min_w]
        x_l2_aligned = x_l2[..., :min_h, :min_w]

        x_r = lhs_shave + x_l2_aligned
        self.print_shape(x_r, 'x_r = lhs_shave + x_l2')

        # 第二轮：r_conv2 → IWT → skip x_l1
        _after_r_conv = self.r_conv2(x_r)            # (B, 256, H/2, W/2)
        self.print_shape(_after_r_conv, 'After r_conv2')

        _x_r = self.IWT(_after_r_conv)               # (B, 64, H, W)
        self.print_shape(_x_r, 'IWT r2')

        _x_r_shave = self.wavelet_shave(_x_r)
        min_h = min(_x_r_shave.shape[-2], x_l1.shape[-2])
        min_w = min(_x_r_shave.shape[-1], x_l1.shape[-1])
        _x_r_shave = _x_r_shave[..., :min_h, :min_w]
        x_l1_aligned = x_l1[..., :min_h, :min_w]

        x_r = _x_r_shave + x_l1_aligned
        self.print_shape(x_r, 'x_r = IWT + x_l1')

        # 第三轮：r_conv1 → 全局残差
        x_r = self.r_conv1(x_r)                      # (B, 1, H, W)
        min_h = min(x_r.shape[-2], x.shape[-2])
        min_w = min(x_r.shape[-1], x.shape[-1])
        x_r = x_r[..., :min_h, :min_w]
        x_aligned = x[..., :min_h, :min_w]

        x_r = x_r + x_aligned                        # 全局残差

        # 可选上采样
        if self.upsample is not None:
            x_r = self.upsample(x_r)

        return x_r


if __name__ == "__main__":
    import torch
    m = LUMWCNN_ABTEST(in_channels=1, with_upsample=False)
    x = torch.randn(1, 1, 64, 64)
    y = m(x)
    print(f"输入: {x.shape}  →  输出: {y.shape}")
    print(f"参数量: {sum(p.numel() for p in m.parameters())/1e6:.2f}M")
