import torch
import torch.nn as nn
import torch.nn.functional as F


# ===================== 【小波模块：修复填充维度】 =====================

class DWT_Haar(nn.Module):
    def forward(self, x):
        B, C, H, W = x.shape
        assert H % 2 == 0 and W % 2 == 0, f"DWT 输入 {H}x{W} 必须是偶数"
        x = x.reshape(B, C, H // 2, 2, W // 2, 2)
        x = x.permute(0, 1, 3, 5, 2, 4).contiguous()
        return x.view(B, C * 4, H // 2, W // 2)


class IWT_Haar(nn.Module):
    def forward(self, x):
        B, C, H, W = x.shape
        assert C % 4 == 0, f"IWT 输入通道 {C} 必须是 4 的倍数"
        x = x.view(B, C // 4, 2, 2, H, W)
        x = x.permute(0, 1, 4, 2, 5, 3).contiguous()
        return x.view(B, C // 4, H * 2, W * 2)


# ===================== 【卷积模块：推理时关闭 Dropout】 =====================

class Convd(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, kernel_size: int,
                 act: bool = True, dropout: float = 0.0):
        super().__init__()
        layer_list = [nn.Conv2d(in_ch, out_ch, kernel_size,
                                padding=kernel_size // 2)]
        # 推理版：完全关闭 Dropout（训练时保留，推理时删除）
        if act:
            layer_list.append(nn.ReLU(inplace=True))
        self.model = nn.Sequential(*layer_list)

    def forward(self, x):
        return self.model(x)


# ===================== 【主模型：修复残差 + 裁剪逻辑】 =====================

class LUMWCNN_CPU(nn.Module):
    def __init__(self, in_channels=1, scale=4, dropout=0.1):
        super().__init__()
        self.in_channels = in_channels
        self.scale = scale
        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

        # 编码器（通道数来自 ckp）
        self.l_conv1 = nn.Sequential(
            Convd(in_channels, 64, 3),
            Convd(64, 64, 3),
        )
        self.l_conv2 = nn.Sequential(
            Convd(256, 128, 3),   # DWT 后 64*4=256
            Convd(128, 128, 3),
        )
        self.l_conv3 = nn.Sequential(
            Convd(512, 256, 3),   # DWT 后 128*4=512
            Convd(256, 256, 3),
        )

        # 解码器（顺序 r_conv3 → r_conv2 → r_conv1）
        self.r_conv3 = nn.Sequential(
            Convd(256, 256, 3),
            Convd(256, 512, 3),   # 为 IWT 准备 512/4=128 通道
        )
        self.r_conv2 = nn.Sequential(
            Convd(128, 128, 3),
            Convd(128, 256, 3),   # 为 IWT 准备 256/4=64 通道
        )
        self.r_conv1 = nn.Sequential(
            Convd(64, 64, 3),
            Convd(64, in_channels, 3, act=False),
        )

        # 上采样（PixelShuffle ×2 两次 → 4×）
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

    def _align_tensor_size(self, tensor_a, tensor_b):
        min_h = min(tensor_a.shape[2], tensor_b.shape[2])
        min_w = min(tensor_a.shape[3], tensor_b.shape[3])
        return tensor_a[:, :, :min_h, :min_w], tensor_b[:, :, :min_h, :min_w]

    def wavelet_pad(self, x):
        """F.pad 参数顺序：(left, right, top, bottom)"""
        pad_h = 1 if x.shape[-2] % 2 != 0 else 0
        pad_w = 1 if x.shape[-1] % 2 != 0 else 0
        self.pads.append([pad_w, pad_h])
        return F.pad(x, (0, pad_w, 0, pad_h), mode="constant", value=0)

    def wavelet_shave(self, x):
        """裁剪维度顺序：先裁高，再裁宽"""
        if not self.pads:
            return x
        pad_w, pad_h = self.pads.pop()
        if pad_h:
            x = x[..., :-1, :]
        if pad_w:
            x = x[..., :, :-1]
        return x

    def forward(self, x):
        self.pads = []   # 每次前向重置，避免状态污染

        # 通道适配
        if x.shape[1] == 3 and self.in_channels == 1:
            x = torch.mean(x, dim=1, keepdim=True)
        elif x.shape[1] == 1 and self.in_channels == 3:
            x = x.repeat(1, 3, 1, 1)

        # 编码
        x_l1 = self.l_conv1(x)
        x_l1_pad = self.wavelet_pad(x_l1)
        x_l2 = self.l_conv2(self.DWT(x_l1_pad))

        x_l2_pad = self.wavelet_pad(x_l2)
        x_l3 = self.l_conv3(self.DWT(x_l2_pad))

        # 解码 + 残差
        x_r = self.wavelet_shave(self.IWT(self.r_conv3(x_l3)))
        x_r, x_l2 = self._align_tensor_size(x_r, x_l2)
        x_r = x_r + x_l2

        x_r = self.wavelet_shave(self.IWT(self.r_conv2(x_r)))
        x_r, x_l1 = self._align_tensor_size(x_r, x_l1)
        x_r = x_r + x_l1

        x_r = self.r_conv1(x_r)
        x_r, x = self._align_tensor_size(x_r, x)
        x_r = x_r + x

        # 输出
        y = self.upsample(x_r)
        # 先归一化再 clamp，避免负数直接变 0
        y = (y - y.min()) / (y.max() - y.min() + 1e-8)
        return torch.clamp(y, 0., 1.)
