'''
WaveletUNet 网络结构 (CPU) - 优化修复版
修复内容：
. 解决通道不匹配问题，确保各层特征图维度一致
. 修复pad信息存储方式，避免多次调用时的状态污染
. 优化网络层定义，确保上下采样通道匹配
. 清理冗余代码，提高可读性
'''

from utils.wavelet import DWT_Haar, IWT_Haar
import sys
import os.path as path
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Union   导入类型提示所需模块

 导入路径处理
dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__, '../../baselines'))


 修复类名与nn.Convd冲突导致的类型检查错误
class Convd(nn.Module):
    """卷积模块，包含可选的ReLU激活"""

    def __init__(self, in_ch, out_ch, kernel_size, act=True) -> None:
        super(Convd, self).__init__()
         明确指定layers类型为nn.Module的列表，解决类型检查冲突
        layers: List[Union[nn.Convd, nn.ReLU]] = [
            nn.Convd(in_ch, out_ch, kernel_size=kernel_size,
                      padding=kernel_size // ),
        ]
        if act:
            layers.append(nn.ReLU(inplace=True))   现在类型检查器能正确识别
        self.layers = nn.Sequential(layers)

    def forward(self, x):
        return self.layers(x)


class LUMWCNN_CPU(nn.Module):
    def __init__(self) -> None:
        super(LUMWCNN_CPU, self).__init__()

         小波变换组件
        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

         左侧编码器
        self.l_conv = nn.Sequential(
            Convd(, , ),
            Convd(, , )
        )
         DWT后通道变为倍 (->)
        self.l_conv = nn.Sequential(
            Convd(, , ),
            Convd(, , )
        )
         DWT后通道变为倍 (->)
        self.l_conv = nn.Sequential(
            Convd(, , ),
            Convd(, , )
        )

         右侧解码器
        self.r_conv = nn.Sequential(
            Convd(, , ),
            Convd(, , )   输出通道，匹配DWT后的维度
        )
         IWT后通道变为/ (->)
        self.r_conv = nn.Sequential(
            Convd(, , ),
            Convd(, , )   输出通道，匹配DWT后的维度
        )
         IWT后通道变为/ (->)
        self.r_conv = nn.Sequential(
            Convd(, , ),
            Convd(, , , act=False)   输出通道，匹配输入维度
        )

         上采样模块 (最终输出为输入的倍分辨率)
        self.upsample = nn.Sequential(
            Convd(, , ),
            Convd(, , ),   像素洗牌前通道数
            nn.PixelShuffle(),    倍上采样
            Convd(, , ),
            Convd(, , ),
            nn.PixelShuffle()     再倍上采样，总倍
        )

        self.valing = False   验证模式标记

    def forward(self, x):
         局部存储pad信息，避免实例变量污染
        pads = []

         编码器第一层
        x_l = self.l_conv(x)
        self.print_shape(x_l, 'After l_conv')

         小波变换前 padding
        x_l_pad, pad = self.wavelet_pad(x_l)
        pads.append(pad)
        self.print_shape(x_l_pad, 'x_l_pad')

         第一层DWT
        _x_l = self.DWT(x_l_pad)
        self.print_shape(_x_l, 'DWT ')

         编码器第二层
        x_l = self.l_conv(_x_l)
        self.print_shape(x_l, 'After l_conv')

         小波变换前 padding
        x_l_pad, pad = self.wavelet_pad(x_l)
        pads.append(pad)
        self.print_shape(x_l_pad, 'x_l_pad')

         第二层DWT
        _x_l = self.DWT(x_l_pad)
        self.print_shape(_x_l, 'DWT ')

         编码器第三层
        x_l = self.l_conv(_x_l)
        self.print_shape(x_l, 'After l_conv')

         解码器第三层
        _after_r_conv = self.r_conv(x_l)
        self.print_shape(_after_r_conv, 'After r_conv')

         第一层IWT
        lhs = self.IWT(_after_r_conv)
        self.print_shape(lhs, 'IWT ')

         裁剪恢复
        should_shave_w, should_shave_h = pads.pop()
        lhs_shave = self.wavelet_shave(lhs, should_shave_w, should_shave_h)
        self.print_shape(lhs_shave, 'lhs_shave')

         残差连接
        x_r = lhs_shave + x_l
        self.print_shape(x_r, 'x_r = lhs_shave + x_l')

         解码器第二层
        _after_r_conv = self.r_conv(x_r)
        self.print_shape(_after_r_conv, 'After r_conv')

         第二层IWT
        _x_r = self.IWT(_after_r_conv)
        self.print_shape(_x_r, 'IWT _x_r')

         裁剪恢复 + 残差连接
        should_shave_w, should_shave_h = pads.pop()
        x_r = self.wavelet_shave(_x_r, should_shave_w, should_shave_h) + x_l
        self.print_shape(x_r, 'x_r')

         解码器第一层 + 输入残差连接
        x_r = self.r_conv(x_r) + x
        self.print_shape(x_r, 'x_r')

         上采样输出
        y = self.upsample(x_r)
        self.print_shape(y, 'Output')

        return y

    def print_shape(self, x, desc):
        """打印张量形状（验证模式下）"""
        if self.valing:
            print(f'Tensor: {desc}  /  Shape: {x.shape}')

    @staticmethod
    def wavelet_pad(x):
        """小波变换前padding，确保尺寸为偶数"""
         输入形状: BCHW
        should_pad_h = x.shape[-] %  !=    高度是否为奇数
        should_pad_w = x.shape[-] %  !=    宽度是否为奇数
         padding格式: (左, 右, 上, 下)
        padding = ( if should_pad_w else , ,
                    if should_pad_h else , )
        x_padded = F.pad(x, padding, 'constant', )
        return x_padded, (should_pad_w, should_pad_h)

    @staticmethod
    def wavelet_shave(x, should_shave_w, should_shave_h):
        """小波逆变换后裁剪，恢复原始尺寸"""
        if should_shave_w:
            x = x[:, :, :, :]   裁剪宽度
        if should_shave_h:
            x = x[:, :, :, :]   裁剪高度
        return x


if __name__ == "__main__":
    import torch
     测试模型输入输出
    model = LUMWCNN_CPU()
    model.valing = True   开启形状打印
    input_tensor = torch.randn(, , , )   批量，通道，x
    output_tensor = model(input_tensor)
    print(f'\n输入形状: {input_tensor.shape}')
    print(f'输出形状: {output_tensor.shape}')
