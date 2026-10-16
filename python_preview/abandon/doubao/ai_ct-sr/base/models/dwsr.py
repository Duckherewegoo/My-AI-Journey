"""
    DWSR 网络结构。
    Deep Wavelet Super-Resolution baseline (灰度版)
"""
import torch.nn as nn
from base.utils.wavelet import DWT_Haar, IWT_Haar


class Convd(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size, act=True) -> None:
        super().__init__()
        self.layers = [
            nn.Conv2d(in_ch, out_ch, kernel_size=kernel_size,
                      padding=kernel_size // 2),
        ]
        if act:
            self.layers.append(nn.ReLU())
        self.layers = nn.Sequential(*self.layers)   # ← 必须加 * 展开 list

    def forward(self, x):
        return self.layers(x)


class DWSR(nn.Module):
    def __init__(self, n_conv=8, residue_weight=0.1,
                 scale=4, in_channels=1, mid_ch=64):
        super().__init__()
        self.n_conv = n_conv
        self.residue_weight = residue_weight

        self.upsample = nn.Upsample(scale_factor=scale,
                                    mode='bicubic',
                                    align_corners=False)
        self.DWT = DWT_Haar()

        # DWT 后通道自动 ×4
        dwt_ch = in_channels * 4      # = 4

        self.body = nn.Sequential(
            Convd(dwt_ch, mid_ch, kernel_size=5),              # body.0: 4→64, 5×5
            *[Convd(mid_ch, mid_ch, kernel_size=3)
              for _ in range(n_conv)],                          # body.1~8: 64→64, 3×3
            Convd(mid_ch, dwt_ch, kernel_size=3),               # body.9: 64→4, 3×3
        )

        self.IWT = IWT_Haar()

    def forward(self, x):
        # 小波变换+逆变换不改变图像大小，所以要先上采样
        upsampled = self.upsample(x)

        # 小波变换 + 残差跳接
        lrsb = self.DWT(upsampled)
        main = self.body(lrsb)
        srsb = main + lrsb * self.residue_weight   # ← 缺的 * 已补
        out = self.IWT(srsb)

        return out
