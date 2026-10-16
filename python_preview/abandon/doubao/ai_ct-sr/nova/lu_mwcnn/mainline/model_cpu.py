import torch
import torch.nn as nn
import torch.nn.functional as F


# ===================== 【小波模块】 =====================

class DWT_Haar(nn.Module):
    """Haar 小波分解：空间尺寸减半，通道数变为 4 倍。"""
    def forward(self, x):
        B, C, H, W = x.shape
        x = x.reshape(B, C, H // 2, 2, W // 2, 2)
        x = x.permute(0, 1, 3, 5, 2, 4).contiguous()
        return x.view(B, C * 4, H // 2, W // 2)


class IWT_Haar(nn.Module):
    """Haar 小波逆变换：空间尺寸翻倍，通道数变为 1/4。"""
    def forward(self, x):
        B, C, H, W = x.shape
        x = x.view(B, C // 4, 2, 2, H, W)
        x = x.permute(0, 1, 4, 2, 5, 3).contiguous()
        return x.view(B, C // 4, H * 2, W * 2)


# ===================== 【卷积模块】 =====================

class Convd(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, kernel_size: int,
                 act: bool = True, dropout: float = 0.0):
        super().__init__()
        layer_list = [
            nn.Conv2d(in_ch, out_ch, kernel_size, padding=kernel_size // 2)
        ]
        if act:
            layer_list.append(nn.ReLU(inplace=True))
        if dropout > 0:
            layer_list.append(nn.Dropout(dropout))
        self.model = nn.Sequential(layer_list)

    def forward(self, x):
        return self.model(x)


# ===================== 【主模型】 =====================

class LUMWCNN_CPU(nn.Module):
    def __init__(self, in_channels=1, scale=4, dropout=0.1):
        """
        Args:
            in_channels: 输入通道数，医学 CT 通常为 1。
            scale: 放大倍数，两个 PixelShuffle(2) 实现 4 倍。
            dropout: r_conv3 最后一个卷积后的 dropout 概率。
        """
        super().__init__()
        self.in_channels = in_channels
        self.scale = scale
        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

        # 按照 ckp 中的顺序定义模块
        # 编码器
        self.l_conv1 = nn.Sequential(
            Convd(1, 64, 3),
            Convd(64, 64, 3)
        )
        self.l_conv2 = nn.Sequential(
            Convd(256, 128, 3),   # DWT 后 64*4=256
            Convd(128, 128, 3)
        )
        self.l_conv3 = nn.Sequential(
            Convd(512, 256, 3),   # DWT 后 128*4=512
            Convd(256, 256, 3)
        )

        # 解码器：注意顺序是 r_conv3, r_conv2, r_conv1
        self.r_conv3 = nn.Sequential(
            Convd(256, 256, 3),
            Convd(256, 512, 3, dropout=dropout)
        )
        self.r_conv2 = nn.Sequential(
            Convd(128, 128, 3),
            Convd(128, 256, 3)
        )
        self.r_conv1 = nn.Sequential(
            Convd(64, 64, 3),
            Convd(64, 1, 3)
        )

        # 上采样
        self.upsample = nn.Sequential(
            Convd(1, 4, 3),
            nn.PixelShuffle(2),
            Convd(1, 4, 3),
            nn.PixelShuffle(2)
        )

        self.pads = []

    def _align_tensor_size(self, tensor_a, tensor_b):
        min_h = min(tensor_a.shape[2], tensor_b.shape[2])
        min_w = min(tensor_a.shape[3], tensor_b.shape[3])
        return (tensor_a[:, :, :min_h, :min_w],
                tensor_b[:, :, :min_h, :min_w])

    def wavelet_pad(self, x):
        pad_h = 1 if x.shape[-2] % 2 != 0 else 0
        pad_w = 1 if x.shape[-1] % 2 != 0 else 0
        self.pads.append([pad_w, pad_h])
        return F.pad(x, (0, pad_w, 0, pad_h), mode="constant", value=0)

    def wavelet_shave(self, x):
        if not self.pads:
            return x
        pad_w, pad_h = self.pads.pop()
        if pad_h:
            x = x[..., :-1, :]
        if pad_w:
            x = x[..., :, :-1]
        return x

    def forward(self, x):
        identity = x

        # ---------- 编码 ----------
        x_l1 = self.l_conv1(x)                     # (B, 64, H, W)
        x_l1_pad = self.wavelet_pad(x_l1)
        x_l2 = self.l_conv2(self.DWT(x_l1_pad))    # (B, 128, H/2, W/2)
        x_l2_pad = self.wavelet_pad(x_l2)
        x_l3 = self.l_conv3(self.DWT(x_l2_pad))    # (B, 256, H/4, W/4)

        # ---------- 解码 ----------
        # 第一步：从 x_l3 到与 x_l2 融合
        x_r = self.r_conv3(x_l3)                   # (B, 512, H/4, W/4)
        x_r = self.IWT(x_r)                        # (B, 128, H/2, W/2)
        x_r = self.wavelet_shave(x_r)
        x_r, x_l2 = self._align_tensor_size(x_r, x_l2)
        x_r = x_r + x_l2

        # 第二步：从融合后到与 x_l1 融合
        x_r = self.r_conv2(x_r)                    # (B, 256, H/2, W/2)
        x_r = self.IWT(x_r)                        # (B, 64, H, W)
        x_r = self.wavelet_shave(x_r)
        x_r, x_l1 = self._align_tensor_size(x_r, x_l1)
        x_r = x_r + x_l1

        # 第三步：输出层卷积 + 残差连接
        x_r = self.r_conv1(x_r)                    # (B, 1, H, W)
        x_r, identity = self._align_tensor_size(x_r, identity)
        x_r = x_r + identity

        # ---------- 上采样 ----------
        y = self.upsample(x_r)                     # (B, 1, 4H, 4W)

        # 归一化并截断
        y = (y - y.min()) / (y.max() - y.min() + 1e-8)
        return torch.clamp(y, 0., 1.)
