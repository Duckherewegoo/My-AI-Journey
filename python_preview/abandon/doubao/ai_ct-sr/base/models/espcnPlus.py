"""
    ESPCN 网络结构 - 优化版（3060 8GB 适配）
    改进点：模块化设计、现代组件、灵活配置、性能优化
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import math
from typing import List, Optional, Union


class SELayer(nn.Module):
    """Squeeze-and-Excitation 注意力模块"""

    def __init__(self, channel, reduction=16):
        super().__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Sequential(
            nn.Linear(channel, channel // reduction, bias=False),
            nn.ReLU(inplace=True),
            nn.Linear(channel // reduction, channel, bias=False),
            nn.Sigmoid()
        )

    def forward(self, x):
        b, c, _, _ = x.size()
        y = self.avg_pool(x).view(b, c)
        y = self.fc(y).view(b, c, 1, 1)
        return x * y.expand_as(x)


class EnhancedConvd(nn.Module):
    """增强卷积模块：Conv + (BN) + (Act) + (SE) + (Dropout)"""

    def __init__(self,
                 in_channels: int,
                 out_channels: int,
                 kernel_size: int = 3,
                 activation: str = 'relu',
                 use_bn: bool = True,
                 use_se: bool = False,
                 dropout: float = 0.0):
        super().__init__()

        assert kernel_size % 2 == 1, "核大小应为奇数以确保对称填充"
        assert activation in ['relu', 'leaky_relu', 'prelu', 'gelu', 'none'], \
            "不支持的激活函数"

        padding = kernel_size // 2

        layers = [
            nn.Conv2d(in_channels, out_channels, kernel_size,
                      padding=padding, bias=not use_bn)
        ]

        if use_bn:
            layers.append(nn.BatchNorm2d(out_channels))

        if activation != 'none':
            if activation == 'relu':
                layers.append(nn.ReLU(inplace=True))
            elif activation == 'leaky_relu':
                layers.append(nn.LeakyReLU(0.1, inplace=True))
            elif activation == 'prelu':
                layers.append(nn.PReLU(num_parameters=out_channels))
            elif activation == 'gelu':
                layers.append(nn.GELU())

        if use_se:
            layers.append(SELayer(out_channels, reduction=16))

        if dropout > 0:
            layers.append(nn.Dropout2d(dropout))

        self.layers = nn.Sequential(*layers)
        self._initialize_weights()

    def _initialize_weights(self):
        for m in self.layers:
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out',
                                        nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

    def forward(self, x):
        return self.layers(x)


class ResidualBlock(nn.Module):
    """残差块"""

    def __init__(self, channels, kernel_size=3, activation='relu'):
        super().__init__()
        self.conv1 = EnhancedConvd(channels, channels, kernel_size, activation)
        self.conv2 = EnhancedConvd(channels, channels, kernel_size,
                                   activation='none')

    def forward(self, x):
        residual = x
        out = self.conv1(x)
        out = self.conv2(out)
        out += residual
        return out


class ESPCN(nn.Module):
    """增强版 ESPCN 超分网络"""

    def __init__(self,
                 scale_factor: int = 4,
                 in_channels: int = 1,
                 base_channels: int = 64,      # ← 3060 8GB 轻松，不用降
                 num_layers: int = 8,
                 use_residual: bool = False,
                 use_attention: bool = False,
                 activation: str = 'relu',
                 dropout: float = 0.0):
        super().__init__()

        self.scale_factor = scale_factor
        self.in_channels = in_channels
        self.base_channels = base_channels
        self.num_layers = num_layers

        assert scale_factor in [2, 3, 4, 8], "缩放因子必须是 2, 3, 4 或 8"

        self.feature_layers = self._build_feature_layers(
            use_residual, use_attention, activation, dropout)

        # 亚像素卷积层
        final_channels = in_channels * (scale_factor ** 2)
        self.final_conv = nn.Conv2d(
            base_channels, final_channels,
            kernel_size=3, padding=1, bias=True)

        self.pixel_shuffle = nn.PixelShuffle(scale_factor)

        # ← 关键修复：SR 输出应该在 [0,1]，不是 [-1,1]
        # 原代码用了 Tanh，会输出负数，导致 PSNR 计算错误
        self.final_activation = nn.Identity()   # 或者 nn.Sigmoid()

        self._initialize_weights()

    def _build_feature_layers(self, use_residual, use_attention,
                              activation, dropout):
        layers = []

        # 第一层
        layers.append(EnhancedConvd(
            self.in_channels, self.base_channels,
            kernel_size=3, activation=activation,
            use_bn=True, use_se=use_attention, dropout=dropout))

        # 中间层
        for i in range(1, self.num_layers - 1):
            if use_residual and i % 2 == 0:
                layers.append(ResidualBlock(
                    self.base_channels, activation=activation))
            else:
                layers.append(EnhancedConvd(
                    self.base_channels, self.base_channels,
                    kernel_size=3, activation=activation,
                    use_bn=True, use_se=use_attention, dropout=dropout))

        return nn.Sequential(*layers)

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out',
                                        nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

        nn.init.normal_(self.final_conv.weight, mean=0.0, std=0.01)
        if self.final_conv.bias is not None:
            nn.init.constant_(self.final_conv.bias, 0)

    def forward(self, x):
        features = self.feature_layers(x)
        out = self.final_conv(features)
        out = self.pixel_shuffle(out)
        out = self.final_activation(out)
        return out

    def get_parameter_count(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class ESPCNPlus(ESPCN):
    """ESPCN 增强版，多尺度特征融合"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # 多尺度池化（2×2 / 4×4）
        self.multi_scale = nn.ModuleList([
            nn.AvgPool2d(2),
            nn.AvgPool2d(4),
        ])

        self.fusion_conv = EnhancedConvd(
            self.base_channels * 3, self.base_channels,
            kernel_size=3, activation='relu')

    def forward(self, x):
        # 浅层特征
        base_features = self.feature_layers[:1](x)

        # 多尺度分支
        scale_features = []
        for pool in self.multi_scale:
            scaled = pool(x)
            feat = self.feature_layers[:1](scaled)
            feat = F.interpolate(feat, size=base_features.shape[2:],
                                 mode='bilinear', align_corners=False)
            scale_features.append(feat)

        # 融合
        fused = torch.cat([base_features] + scale_features, dim=1)
        fused = self.fusion_conv(fused)

        # 深层
        features = self.feature_layers[1:](fused)
        out = self.final_conv(features)
        out = self.pixel_shuffle(out)
        out = self.final_activation(out)
        return out


# ===================== 预定义配置（3060 8GB 友好） =====================
def ESPCN_x2(**kwargs):
    return ESPCN(scale_factor=2, base_channels=64, num_layers=8, **kwargs)

def ESPCN_x3(**kwargs):
    return ESPCN(scale_factor=3, base_channels=64, num_layers=8, **kwargs)

def ESPCN_x4(**kwargs):
    return ESPCN(scale_factor=4, base_channels=64, num_layers=8, **kwargs)

def ESPCN_heavy(**kwargs):
    return ESPCN(scale_factor=4, base_channels=64, num_layers=16,
                 use_residual=True, use_attention=True, **kwargs)

def ESPCN_light(**kwargs):
    return ESPCN(scale_factor=4, base_channels=32, num_layers=6,
                 use_residual=False, use_attention=False, **kwargs)


# ===================== 3060 8GB 推荐训练配置 =====================
TRAIN_CONFIG_3060 = {
    "batch_size": 32,           # 8GB 绰绰有余
    "num_workers": 4,
    "pin_memory": True,
    "persistent_workers": False,
    "use_amp": True,            # 免费加速
    "crop_size": 96,            # 训练 patch 尺寸
    "lr": 1e-3,
    "weight_decay": 1e-4,
    "epochs": 200,
}


if __name__ == '__main__':
    # 显存占用检查
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"设备: {device}")

    for name, model_fn in [
        ("ESPCN-x4", ESPCN_x4),
        ("ESPCN-heavy", ESPCN_heavy),
        ("ESPCN-light", ESPCN_light),
    ]:
        model = model_fn(in_channels=1).to(device)
        params = model.get_parameter_count()

        # 前向 + 反向测显存
        torch.cuda.reset_peak_memory_stats()
        x = torch.randn(TRAIN_CONFIG_3060["batch_size"], 1,
                        TRAIN_CONFIG_3060["crop_size"],
                        TRAIN_CONFIG_3060["crop_size"]).to(device)
        y = model(x)
        loss = y.mean()
        loss.backward()
        peak_mem = torch.cuda.max_memory_allocated() / 1e9

        print(f"[{name}] 参数量={params:,} | "
              f"batch={TRAIN_CONFIG_3060['batch_size']} 峰值显存={peak_mem:.2f}GB | "
              f"{'✅' if peak_mem < 6.5 else '⚠️'}")

        del model, x, y, loss
        torch.cuda.empty_cache()
