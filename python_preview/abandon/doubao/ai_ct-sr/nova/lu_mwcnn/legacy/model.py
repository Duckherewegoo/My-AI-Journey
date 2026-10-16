'''
    WaveletUNet 网络结构。
'''

import os.path as path

dirname__ = path.dirname(path.abspath(__file__))
import sys

sys.path.append(path.join(dirname__, '../../baselines'))

import torch.nn as nn
import torch.nn.functional as F
from utils.wavelet import DWT_Haar, IWT_Haar


class Convd(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size, act=True) -> None:
        super(Convd, self).__init__()
        self.layers = [
            nn.Convd(in_ch, out_ch, kernel_size=kernel_size, padding=kernel_size // ),
        ]
        if act:
            self.layers.append(nn.ReLU())
        self.layers = nn.Sequential(self.layers)

    def forward(self, x):
        return self.layers(x)


class LUMWCNN(nn.Module):
    def __init__(self) -> None:
        super(LUMWCNN, self).__init__()

        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

        self.l_conv = nn.Sequential([Convd(, , ), Convd(, , )])
         DWT,  -> 
        self.l_conv = nn.Sequential([Convd(, , ), Convd(, , )])
         DWT,  -> 
        self.l_conv = nn.Sequential([Convd(, , ), Convd(, , )])
         === HALF, ch =  ===
        self.r_conv = nn.Sequential([Convd(, , ), Convd(, , )])   ->
         DWT,  -> 
        self.r_conv = nn.Sequential([Convd(, , ), Convd(, , )])   ->
         DWT,  -> 
        self.r_conv = nn.Sequential([Convd(, , ), Convd(, , )])   ->

        self.upsample = nn.Sequential([
            Convd(, , ),
            Convd(, , ),   r=
            nn.PixelShuffle(),
            Convd(, , ),
            Convd(, , ),   r=
            nn.PixelShuffle()
        ])

        self.valing = False
        self.pads = []

    def forward(self, x):
        self.print_shape(x, 'Input')

        x_l = self.l_conv(x)   ->
        self.print_shape(x_l, 'After l_conv')

        x_l_pad = self.wavelet_pad(x_l)
        self.print_shape(x_l_pad, 'x_l_pad')

        _x_l = self.DWT(x_l_pad)
        self.print_shape(_x_l, 'DWT ')

        x_l = self.l_conv(_x_l)   ->
        self.print_shape(x_l, 'After l_conv')

        x_l_pad = self.wavelet_pad(x_l)
        self.print_shape(x_l_pad, 'x_l_pad')

        _x_l = self.DWT(x_l_pad)
        self.print_shape(_x_l, 'DWT ')

        x_l = self.l_conv(_x_l)   ->
        self.print_shape(x_l, 'After l_conv')

        _after_r_conv = self.r_conv(x_l)
        self.print_shape(_after_r_conv, 'After r_conv')

        lhs = self.IWT(_after_r_conv).cuda()
        self.print_shape(lhs, 'IWT ')

        lhs_shave = self.wavelet_shave(lhs)
        self.print_shape(lhs_shave, 'lhs_shave')

        x_r = lhs_shave + x_l
        self.print_shape(x_r, 'x_r = lhs_shave + x_l')

        _after_r_conv = self.r_conv(x_r)
        self.print_shape(_after_r_conv, 'After r_conv')

        _x_r = self.IWT(_after_r_conv).cuda()
        self.print_shape(_x_r, 'IWT _x_r')

        x_r = self.wavelet_shave(_x_r) + x_l
        self.print_shape(x_r, 'x_r')

        x_r = self.r_conv(x_r) + x

        y = self.upsample(x_r)

        return y

    def print_shape(self, x, desc):
        return
         if not self.valing:
             return
         return
         print('\n--------------------------------------')
         print('\n|-- Tensor: {}  /  Shape: {}'.format(desc, x.shape))
         print('\n--------------------------------------')

    def wavelet_pad(self, x):
         BCHW
        should_pad_h = x.shape[-] %  != 
        should_pad_w = x.shape[-] %  != 
        padding = ( if should_pad_w else , ,  if should_pad_h else , )   lrtb
        self.pads.append([should_pad_w, should_pad_h])
        return F.pad(x, padding, 'constant', )

    def wavelet_shave(self, x):
        should_shave_w, should_shave_h = self.pads.pop()
        if should_shave_w:
            x = x[:, :, :, :]
        if should_shave_h:
            x = x[:, :, :, :]
        return x


if __name__ == "__main__":
    print(LUMWCNN())
