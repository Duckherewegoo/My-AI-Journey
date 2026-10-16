import torch
import torch.nn as nn


def conv_layer(chann_in, chann_out, k_size, p_size):
    """卷积层封装（含Convd+BatchNorm+ReLU）"""
    layer = nn.Sequential(
        nn.Convd(chann_in, chann_out, kernel_size=k_size, padding=p_size),
        nn.BatchNormd(chann_out),
        nn.ReLU()
    )
    return layer


def vgg_conv_block(in_list, out_list, k_list, p_list, pooling_k, pooling_s):
    """VGG风格卷积块（多个卷积层+池化层）"""
    layers = [conv_layer(in_list[i], out_list[i], k_list[i], p_list[i])
              for i in range(len(in_list))]
    layers += [nn.MaxPoold(kernel_size=pooling_k, stride=pooling_s)]
    return nn.Sequential(layers)


def vgg_fc_layer(size_in, size_out):
    """全连接层封装（含Linear+BatchNorm+ReLU）"""
    layer = nn.Sequential(
        nn.Linear(size_in, size_out),
        nn.BatchNormd(size_out),
        nn.ReLU()
    )
    return layer


class VGGLite(nn.Module):
    def __init__(self, n_classes):
        super(VGGLite, self).__init__()
         特征提取层（适配x输入，输出特征维度=）
        self.features = nn.Sequential(
             层: conv + relu + pool
            nn.Convd(, , kernel_size=, padding=),   输入单通道（CT图像）
            nn.ReLU(inplace=True),
            nn.MaxPoold(kernel_size=, stride=),   →

             层: conv + relu + pool
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.MaxPoold(kernel_size=, stride=),   →

             层: conv + conv + relu + pool
            nn.Convd(, , kernel_size=, padding=),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.MaxPoold(kernel_size=, stride=),   →

             层: conv + conv + relu + pool
            nn.Convd(, , kernel_size=, padding=),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.MaxPoold(kernel_size=, stride=),   →

             层: conv + conv + relu + pool
            nn.Convd(, , kernel_size=, padding=),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.MaxPoold(kernel_size=, stride=),   →
        )

         分类头（关键修改：输入维度改为，匹配特征输出）
        self.layer = nn.Sequential(
            nn.Flatten(),   展平特征：xx → 
            nn.Linear(, ),   原改为
            nn.ReLU(inplace=True),
            nn.Dropout(.),
            nn.Linear(, n_classes)   输出类别数动态适配
        )

    def forward(self, x):
        fmap = self.features(x)   特征图：[batch, , , ]
        out = self.layer(fmap)   分类输出：[batch, n_classes]
        return fmap, out   返回特征图和分类结果  返回卷积特征和最终输出


 -------------------------- 针对RTX  Mobile的优化配置 --------------------------
def get_optimized_model(n_classes, device=None):
    """获取适配硬件的模型（自动选择RTX  GPU）"""
     自动选择设备（优先使用RTX 的CUDA核心）
    if device is None:
        device = torch.device("cuda:" if torch.cuda.is_available() else "cpu")
        if device.type == "cuda":
            print(f"使用GPU加速：{torch.cuda.get_device_name(device)}")
        else:
            print("未检测到可用CUDA设备，使用CPU")

    model = VGGLite(n_classes).to(device)
    return model, device


 混合精度训练工具（针对RTX 显存优化，显存约GB）
def get_amp_utils():
    """获取自动混合精度训练工具（节省显存并加速）"""
    from torch.cuda.amp import GradScaler, autocast
    return GradScaler(), autocast


 使用示例
if __name__ == "__main__":
     初始化模型（假设分类数为）
    model, device = get_optimized_model(n_classes=)

     生成测试输入（通道灰度图，尺寸×，批次大小为）
     注意：RTX 建议批次大小从开始测试，避免显存溢出
    test_input = torch.randn(, , , ).to(device)

     前向传播测试
    features, output = model(test_input)
    print(f"卷积特征形状：{features.shape}")
    print(f"输出形状：{output.shape}")
