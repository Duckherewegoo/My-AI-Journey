"""
    ESPCN 网络结构。（高效亚像素卷积网络，灰度版 x4）
    Efficient Sub-Pixel Convolutional Neural Network
"""
import torch.nn as nn


class Convd(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size, act=True):
        super().__init__()
        self.layers = [
            nn.Conv2d(in_ch, out_ch, kernel_size=kernel_size,
                      padding=kernel_size // 2),
        ]
        if act:
            self.layers.append(nn.ReLU(inplace=True))
        self.layers = nn.Sequential(*self.layers)

    def forward(self, x):
        return self.layers(x)


class ESPCN(nn.Module):
    def __init__(self, in_channels=1, out_channels=1, scale=4):
        super().__init__()

        self.conv1 = Convd(in_channels, 32, 5)                     # 1 → 32, 5×5
        self.conv2 = Convd(32, 32, 3)                              # 32 → 32, 3×3
        self.conv3 = Convd(32, out_channels * (scale ** 2), 3)     # 32 → 16, 3×3
        self.conv4 = Convd(out_channels * (scale ** 2),
                           out_channels * (scale ** 2), 3, False)   # 16 → 16, 3×3, 不激活

        self.ps = nn.PixelShuffle(scale)                           # 16 → 1, 空间 ×4

    def forward(self, x):
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        x = self.conv4(x)
        x = self.ps(x)
        return x
