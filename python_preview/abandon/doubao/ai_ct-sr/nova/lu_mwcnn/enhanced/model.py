'''
WaveletUNet 网络结构 (LUMWCNN)
修复内容：
. 解决通道维度不匹配问题（r_conv输出与输入x通道不一致）
. 移除硬编码的.cuda()，适配自动设备选择
. 优化upsample输入通道匹配
. 修正变量命名（valing -> validating）
. 完善调试打印功能
'''

import torch
import sys
import os.path as path
import torch.nn as nn
import torch.nn.functional as F
from base.utils.wavelet import DWT_Haar, IWT_Haar

 路径处理
dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__, '../../baselines'))


 修改Convd类
class Convd(nn.Module):
    """带激活函数+批归一化的卷积模块"""

    def __init__(self, in_ch, out_ch, kernel_size, act=True) -> None:
        super(Convd, self).__init__()
        layers = [
            nn.Convd(in_ch, out_ch, kernel_size=kernel_size,
                      padding=kernel_size // , bias=False),   批归一化不需要bias
            nn.BatchNormd(out_ch),   新增批归一化
        ]
        if act:
            layers.append(nn.ReLU(inplace=True))
        self.layers = nn.Sequential(layers)

    def forward(self, x):
        return self.layers(x)


class LUMWCNN(nn.Module):
    def __init__(self) -> None:
        super(LUMWCNN, self).__init__()

        self.DWT = DWT_Haar()   小波变换
        self.IWT = IWT_Haar()   小波逆变换
        self.pad_info = {}
         左侧卷积块（下采样路径）
        self.l_conv = nn.Sequential([Convd(, , ), Convd(, , )])
        self.l_conv = nn.Sequential(
            [Convd(, , ), Convd(, , )])   =（DWT后通道×）
        self.l_conv = nn.Sequential(
            [Convd(, , ), Convd(, , )])   =

         右侧卷积块（上采样路径）
        self.r_conv = nn.Sequential(
             输出用于IWT（/=）
            [Convd(, , ), Convd(, , )])
        self.r_conv = nn.Sequential(
             输出用于IWT（/=）
            [Convd(, , ), Convd(, , )])
        self.r_conv = nn.Sequential(
            [Convd(, , ), Convd(, , , act=False)])   输出通道与输入x匹配

         上采样模块（总放大倍数x）

        self.upsample = nn.Sequential(
            Convd(, , ),
            Convd(,   , ),   修正：^  目标通道() = 
            nn.PixelShuffle(),   第一次x上采样（通道→，尺寸×）
            Convd(, , ),
            Convd(,   , ),   同上
            nn.PixelShuffle(),   第二次x上采样
            nn.Convd(, , , padding=, bias=False),   最终输出通道，无激活
            nn.Sigmoid()   强制输出值域[,]，避免全黑
        )

        self.validating = False   调试模式标记
        self.pads = []   记录填充信息

    def forward(self, x):
        self.print_shape(x, 'Input')

         左侧第一层
        x_l = self.l_conv(x)   ->
        self.print_shape(x_l, 'After l_conv')

         小波变换前填充（确保尺寸为偶数）
        x_l_pad = self.wavelet_pad(x_l, 'l')
        self.print_shape(x_l_pad, 'x_l_pad')

         第一次DWT（通道×）
        _x_l = self.DWT(x_l_pad)
        self.print_shape(_x_l, 'After DWT ')

         左侧第二层
        x_l = self.l_conv(_x_l)   ->
        self.print_shape(x_l, 'After l_conv')

        x_l_pad = self.wavelet_pad(x_l, 'l')
        self.print_shape(x_l_pad, 'x_l_pad')

         第二次DWT
        _x_l = self.DWT(x_l_pad)
        self.print_shape(_x_l, 'After DWT ')

         左侧第三层
        x_l = self.l_conv(_x_l)   ->
        self.print_shape(x_l, 'After l_conv')

         右侧第三层
        _after_r_conv = self.r_conv(x_l)   ->
        self.print_shape(_after_r_conv, 'After r_conv')

         第一次IWT（通道÷）
        lhs = self.IWT(_after_r_conv).to(x.device)   适配输入设备
        self.print_shape(lhs, 'After IWT ')

         移除填充部分
        lhs_shave = self.wavelet_shave(lhs, 'l')
        self.print_shape(lhs_shave, 'lhs_shave')

         残差连接
        x_r = lhs_shave + x_l
        self.print_shape(x_r, 'x_r (residual)')

         右侧第二层
        _after_r_conv = self.r_conv(x_r)   ->
        self.print_shape(_after_r_conv, 'After r_conv')

         第二次IWT
        _x_r = self.IWT(_after_r_conv).to(x.device)
        self.print_shape(_x_r, 'After IWT ')

         残差连接
        x_r = self.wavelet_shave(_x_r, 'l') + x_l
        self.print_shape(x_r, 'x_r (residual)')

         右侧第一层（输出通道与输入匹配）
        x_r = .  self.r_conv(x_r) + x
        self.print_shape(x_r, 'x_r (residual)')

         上采样得到最终结果
        y = self.upsample(x_r)
        y = torch.clamp(y, , )
        self.print_shape(y, 'Output')

        return y

    def print_shape(self, x, desc):
        """调试时打印张量形状"""
        if self.validating:
            print(f'[{desc}] Shape: {x.shape}')

     替换wavelet_pad函数
    def wavelet_pad(self, x, key):
        """小波变换前填充，按key记录填充信息"""
        should_pad_h = x.shape[-] %  != 
        should_pad_w = x.shape[-] %  != 
        padding = ( if should_pad_w else , ,
                    if should_pad_h else , )
        self.pad_info[key] = [should_pad_w, should_pad_h]
        return F.pad(x, padding, 'constant', )

     替换wavelet_shave函数
    def wavelet_shave(self, x, key):
        """小波逆变换后移除填充，按key读取填充信息"""
        if key not in self.pad_info:
            return x
        should_shave_w, should_shave_h = self.pad_info.pop(key)
        if should_shave_w:
            x = x[:, :, :, :-]   修正：原代码是:，改为:-（填充的是右侧/下侧，应裁最后一列）
        if should_shave_h:
            x = x[:, :, :-, :]   修正：裁最后一行
        return x


if __name__ == "__main__":
    import torch
     测试网络结构
    model = LUMWCNN()
    input_tensor = torch.randn(, , , )   示例输入 (B, C, H, W)
    output_tensor = model(input_tensor)
    print(f"Input shape: {input_tensor.shape}")
     应输出 (, , , ) 即x上采样
    print(f"Output shape: {output_tensor.shape}")
