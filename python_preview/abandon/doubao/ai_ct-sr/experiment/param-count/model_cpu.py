# 反编译源文件: .../param-count/__pycache__/model_cpu.cpython-311.pyc
# 恢复版

import torch
import torch.nn as nn
import torch.nn.functional as F


# ==================== 小波模块 ====================

class DWT_Haar(nn.Module):
    """Haar 小波分解：空间减半，通道 ×4。"""
    def forward(self, x):
        B, C, H, W = x.shape
        assert H % 2 == 0 and W % 2 == 0, f"DWT 输入 {H}x{W} 必须是偶数"
        x = x.reshape(B, C, H // 2, 2, W // 2, 2)
        x = x.permute(0, 1, 3, 5, 2, 4).contiguous()
        return x.view(B, C * 4, H // 2, W // 2)


class IWT_Haar(nn.Module):
    """Haar 小波逆变换：空间翻倍，通道 ÷4。"""
    def forward(self, x):
        B, C, H, W = x.shape
        assert C % 4 == 0, f"IWT 输入通道 {C} 必须是 4 的倍数"
        x = x.view(B, C // 4, 2, 2, H, W)
        x = x.permute(0, 1, 4, 2, 5, 3).contiguous()
        return x.view(B, C // 4, H * 2, W * 2)


# ==================== 卷积模块 ====================

class Conv2d(nn.Module):
    """
    带激活开关的卷积封装。
    反编译里类名就叫 Conv2d，内部是 Conv2d + 可选 ReLU。
    """
    def __init__(self, in_ch: int, out_ch: int, kernel_size: int,
                 act: bool = True) -> None:
        super().__init__()
        layers = [
            nn.Conv2d(in_ch, out_ch, kernel_size,
                      padding=kernel_size // 2, bias=True)
        ]
        if act:
            layers.append(nn.ReLU(inplace=True))
        self.model = nn.Sequential(*layers)

    def forward(self, x):
        return self.model(x)


# ==================== 主模型 ====================

class LUMWCNN_CPU(nn.Module):
    """
    LUMWCNN 的 CPU 版，用于参数计数。

    结构（通道数来自 ckp）：
        编码：l_conv1(1→64→64) → DWT → l_conv2(256→128→128) → DWT → l_conv3(512→256→256)
        解码：r_conv3(256→256→512) → IWT → +x_l2
              r_conv2(128→128→256) → IWT → +x_l1
              r_conv1(64→64→1) → +x
        上采样：PixelShuffle ×2 两次 → 4×
    """

    def __init__(self, in_channels: int = 1, scale: int = 4,
                 dropout: float = 0.0) -> None:
        super().__init__()
        self.in_channels = in_channels
        self.scale = scale
        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

        # 编码器
        self.l_conv1 = nn.Sequential(
            Conv2d(in_channels, 64, 3),
            Conv2d(64, 64, 3),
        )
        self.l_conv2 = nn.Sequential(
            Conv2d(256, 128, 3),   # DWT 后 64*4=256
            Conv2d(128, 128, 3),
        )
        self.l_conv3 = nn.Sequential(
            Conv2d(512, 256, 3),   # DWT 后 128*4=512
            Conv2d(256, 256, 3),
        )

        # 解码器（注意顺序：r_conv3 → r_conv2 → r_conv1）
        self.r_conv3 = nn.Sequential(
            Conv2d(256, 256, 3),
            Conv2d(256, 512, 3),   # IWT 后 512/4=128
        )
        self.r_conv2 = nn.Sequential(
            Conv2d(128, 128, 3),
            Conv2d(128, 256, 3),   # IWT 后 256/4=64
        )
        self.r_conv1 = nn.Sequential(
            Conv2d(64, 64, 3),
            Conv2d(64, in_channels, 3, act=False),
        )

        # 上采样
        if scale == 4:
            self.upsample = nn.Sequential(
                nn.Conv2d(in_channels, in_channels * 4, 3, padding=1),
                nn.PixelShuffle(2),
                nn.Conv2d(in_channels, in_channels * 4, 3, padding=1),
                nn.PixelShuffle(2),
            )
        elif scale == 2:
            self.upsample = nn.Sequential(
                nn.Conv2d(in_channels, in_channels * 4, 3, padding=1),
                nn.PixelShuffle(2),
            )
        else:
            raise ValueError("scale 仅支持 2 或 4")

        self.pads = []

    @staticmethod
    def _align(a, b):
        mh = min(a.shape[2], b.shape[2])
        mw = min(a.shape[3], b.shape[3])
        return a[:, :, :mh, :mw], b[:, :, :mh, :mw]

    def _pad(self, x):
        ph = 1 if x.shape[-2] % 2 else 0
        pw = 1 if x.shape[-1] % 2 else 0
        self.pads.append([pw, ph])
        return F.pad(x, (0, pw, 0, ph), "constant", 0)

    def _shave(self, x):
        if not self.pads:
            return x
        pw, ph = self.pads.pop()
        if pw:
            x = x[:, :, :, :-pw]
        if ph:
            x = x[:, :, :-ph, :]
        return x

    def forward(self, x):
        self.pads = []

        # 通道适配
        if x.shape[1] == 3 and self.in_channels == 1:
            x = torch.mean(x, dim=1, keepdim=True)
        elif x.shape[1] == 1 and self.in_channels == 3:
            x = x.repeat(1, 3, 1, 1)

        # 编码
        x_l1 = self.l_conv1(x)
        x_l2 = self.l_conv2(self.DWT(self._pad(x_l1)))
        x_l3 = self.l_conv3(self.DWT(self._pad(x_l2)))

        # 解码 + 残差
        x_r = self._shave(self.IWT(self.r_conv3(x_l3)))
        x_r, x_l2 = self._align(x_r, x_l2)
        x_r = x_r + x_l2

        x_r = self._shave(self.IWT(self.r_conv2(x_r)))
        x_r, x_l1 = self._align(x_r, x_l1)
        x_r = x_r + x_l1

        x_r = self.r_conv1(x_r)
        x_r, x = self._align(x_r, x)
        x_r = x_r + x

        y = self.upsample(x_r)
        return torch.clamp(y, 0.0, 1.0)


# ==================== 参数计数入口 ====================

if __name__ == "__main__":
    model = LUMWCNN_CPU(in_channels=1, scale=4)

    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)

    print(f"总参数量    : {total:,} ({total/1e6:.3f} M)")
    print(f"可训练参数  : {trainable:,} ({trainable/1e6:.3f} M)")

    print("\n按模块拆分：")
    for name, module in model.named_children():
        n = sum(p.numel() for p in module.parameters())
        if n > 0:
            print(f"  {name:12s}: {n:>10,}  ({n/1e6:.4f} M)")

    # 假数据前向，确认能跑
    dummy = torch.randn(1, 1, 64, 64)
    with torch.no_grad():
        out = model(dummy)
    print(f"\n输入: {tuple(dummy.shape)} → 输出: {tuple(out.shape)}")
