# 反编译源文件: /home/dake/Documents/Projects/Graduction_Projects/codes/experiment/calc-ct-lpips/__pycache__/modell.cpython-311.pyc
# 生成时间: 2026-09-14 16:06:15.168129
# ============================================================================

# Source Generated with Decompyle++
# File: modell.cpython-311.pyc (Python 3.11)

import torch
from torch.nn import nn

def conv_layer(chann_in, chann_out, k_size, p_size):
    '''卷积层封装（含Conv2d+BatchNorm+ReLU）'''
    layer = nn.Sequential(nn.Conv2d(chann_in, chann_out, kernel_size = k_size, padding = p_size), nn.BatchNorm2d(chann_out), nn.ReLU())
    return layer


def vgg_conv_block(in_list, out_list, k_list, p_list, pooling_k, pooling_s):
    '''VGG风格卷积块（多个卷积层+池化层）'''
    pass
# WARNING: Decompyle incomplete


def vgg_fc_layer(size_in, size_out):
    '''全连接层封装（含Linear+BatchNorm+ReLU）'''
    layer = nn.Sequential(nn.Linear(size_in, size_out), nn.BatchNorm1d(size_out), nn.ReLU())
    return layer


class VGGLite(nn.Module):
    pass
# WARNING: Decompyle incomplete


def get_optimized_model(n_classes, device = (None,)):
    '''获取适配硬件的模型（自动选择RTX 3060 GPU）'''
    pass
# WARNING: Decompyle incomplete


def get_amp_utils():
    '''获取自动混合精度训练工具（节省显存并加速）'''
    GradScaler = GradScaler
    autocast = autocast
    import torch.cuda.amp
    return (GradScaler(), autocast)

if __name__ == '__main__':
    (model, device) = get_optimized_model(n_classes = 10)
    test_input = torch.randn(8, 1, 512, 512).to(device)
    (features, output) = model(test_input)
    print(f'''卷积特征形状：{features.shape}''')
    print(f'''输出形状：{output.shape}''')
    return None
