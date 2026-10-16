import torch
import torch.nn as nn
import torch.optim as optim
from torch.cuda.amp import GradScaler, autocast


def conv_layer(chann_in, chann_out, k_size, p_size):
    """卷积层封装（Conv2d + BatchNorm + ReLU）"""
    return nn.Sequential(
        nn.Conv2d(chann_in, chann_out, kernel_size=k_size, padding=p_size),
        nn.BatchNorm2d(chann_out),
        nn.ReLU(inplace=True),
    )


def vgg_conv_block(in_list, out_list, k_list, p_list, pooling_k, pooling_s):
    """
    VGG 风格卷积块：多个 Conv+BN+ReLU 后接 MaxPool。

    in_list / out_list / k_list / p_list 都是等长列表，
    表示依次堆叠的卷积层参数。
    """
    layers = []
    for i in range(len(in_list)):
        layers.append(conv_layer(in_list[i], out_list[i], k_list[i], p_list[i]))
    layers.append(nn.MaxPool2d(kernel_size=pooling_k, stride=pooling_s))
    return nn.Sequential(*layers)


def vgg_fc_layer(size_in, size_out):
    """全连接层封装（Linear + BatchNorm1d + ReLU）"""
    return nn.Sequential(
        nn.Linear(size_in, size_out),
        nn.BatchNorm1d(size_out),
        nn.ReLU(inplace=True),
    )


class VGGLite(nn.Module):
    """
    轻量 VGG，用于 CT 图像的感知特征提取。

    输入： (B, 1, H, W)，典型 H=W=512
    输出： (features, output)
        features: 最后的卷积特征 (B, 512, H/16, W/16)
        output:   分类/回归头 (B, n_classes)
    """

    def __init__(self, n_classes=10, in_channels=1):
        super().__init__()
        self.in_channels = in_channels
        self.n_classes = n_classes

        # ---------- 卷积主干 ----------
        # block1: 1  -> 64,   H/2
        self.block1 = vgg_conv_block(
            [in_channels, 64], [64, 64],
            [3, 3], [1, 1], pooling_k=2, pooling_s=2,
        )
        # block2: 64 -> 128,  H/4
        self.block2 = vgg_conv_block(
            [64, 128], [128, 128],
            [3, 3], [1, 1], pooling_k=2, pooling_s=2,
        )
        # block3: 128 -> 256, H/8
        self.block3 = vgg_conv_block(
            [128, 256, 256], [256, 256, 256],
            [3, 3, 3], [1, 1, 1], pooling_k=2, pooling_s=2,
        )
        # block4: 256 -> 512, H/16
        self.block4 = vgg_conv_block(
            [256, 512, 512], [512, 512, 512],
            [3, 3, 3], [1, 1, 1], pooling_k=2, pooling_s=2,
        )

        # ---------- 分类头 ----------
        self.global_pool = nn.AdaptiveAvgPool2d((7, 7))
        self.fc1 = vgg_fc_layer(512 * 7 * 7, 1024)
        self.fc2 = vgg_fc_layer(1024, 512)
        self.fc3 = nn.Linear(512, n_classes)

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.BatchNorm2d) or isinstance(m, nn.BatchNorm1d):
                nn.init.ones_(m.weight)
                nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, 0, 0.01)
                nn.init.zeros_(m.bias)

    def forward(self, x):
        # 特征提取
        x = self.block1(x)
        x = self.block2(x)
        x = self.block3(x)
        features = self.block4(x)          # (B, 512, H/16, W/16)

        # 分类
        x = self.global_pool(features)     # (B, 512, 7, 7)
        x = torch.flatten(x, 1)            # (B, 512*7*7)
        x = self.fc1(x)
        x = self.fc2(x)
        output = self.fc3(x)               # (B, n_classes)

        return features, output


def get_optimized_model(n_classes, device=(None,)):
    """
    获取适配硬件的模型。

    - 自动选择 cuda / cpu
    - 若指定 device 元组，取第一个非 None 的元素
    - 返回 (model, device)
    """
    if device[0] is not None:
        dev = torch.device(device[0])
    else:
        dev = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    model = VGGLite(n_classes=n_classes, in_channels=1).to(dev)

    # 3060 上开启 cudnn benchmark，加快固定输入尺寸的训练
    if dev.type == 'cuda':
        torch.backends.cudnn.benchmark = True
        print(f"Using GPU: {torch.cuda.get_device_name(dev)}")
    else:
        print("Using CPU")

    return model, dev


def get_amp_utils():
    """获取自动混合精度训练工具（节省显存并加速）"""
    import torch.cuda.amp
    return GradScaler(), autocast


if __name__ == '__main__':
    model, device = get_optimized_model(n_classes=10)
    test_input = torch.randn(8, 1, 512, 512).to(device)
    features, output = model(test_input)
    print(f"卷积特征形状：{features.shape}")
    print(f"输出形状：{output.shape}")
