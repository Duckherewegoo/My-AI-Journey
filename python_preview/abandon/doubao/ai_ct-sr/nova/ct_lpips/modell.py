"""
VGGLite —— CT-LPIPS 的骨干网络
从 checkpoint shape 精确反推
"""
import torch
import torch.nn as nn


class VGGLite(nn.Module):
    """轻量 VGG 变体，输入 (B, 1, 224, 224)，输出 (B, 658)"""

    def __init__(self, num_classes=658):
        super().__init__()

        self.features = nn.Sequential(
            # block1
            nn.Conv2d(1, 64, kernel_size=3, padding=1),      # 0
            nn.ReLU(inplace=True),                           # 1
            nn.MaxPool2d(kernel_size=2, stride=2),           # 2

            # block2
            nn.Conv2d(64, 128, kernel_size=3, padding=1),    # 3
            nn.ReLU(inplace=True),                           # 4
            nn.MaxPool2d(kernel_size=2, stride=2),           # 5

            # block3
            nn.Conv2d(128, 256, kernel_size=3, padding=1),   # 6
            nn.Conv2d(256, 256, kernel_size=3, padding=1),   # 7
            nn.ReLU(inplace=True),                           # 8
            nn.MaxPool2d(kernel_size=2, stride=2),           # 9

            # block4
            nn.Conv2d(256, 512, kernel_size=3, padding=1),   # 10
            nn.Conv2d(512, 512, kernel_size=3, padding=1),   # 11
            nn.ReLU(inplace=True),                           # 12
            nn.MaxPool2d(kernel_size=2, stride=2),           # 13

            # block5
            nn.Conv2d(512, 512, kernel_size=3, padding=1),   # 14
            nn.Conv2d(512, 512, kernel_size=3, padding=1),   # 15
            nn.ReLU(inplace=True),                           # 16
            nn.MaxPool2d(kernel_size=2, stride=2),           # 17
        )

        self.layer5 = nn.Sequential(
            nn.Flatten(),                                    # 0
            nn.Linear(512 * 7 * 7, 512),                     # 1   ← 25088
            nn.ReLU(inplace=True),                           # 2
            nn.Dropout(0.5),                                 # 3
            nn.Linear(512, num_classes),                     # 4   ← 658
        )

    def forward(self, x):
        x = self.features(x)
        return self.layer5(x)


if __name__ == "__main__":
    # 验证：看输出 shape 和参数量
    m = VGGLite(num_classes=658)
    x = torch.randn(2, 1, 224, 224)
    y = m(x)
    print(f"输入: {x.shape}  → 输出: {y.shape}")
    print(f"总参数量: {sum(p.numel() for p in m.parameters()) / 1e6:.2f}M")
