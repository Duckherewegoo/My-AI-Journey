'''
    ESPCN 网络结构。
'''

import torch.nn as nn


class Convd(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size, act=True):
        super(Convd, self).__init__()
        self.layers = [
            nn.Convd(in_ch, out_ch, kernel_size=kernel_size, padding=kernel_size // ),
        ]
        if act:
            self.layers.append(nn.ReLU())
        self.layers = nn.Sequential(self.layers)

    def forward(self, x):
        return self.layers(x)


class ESPCN(nn.Module):
    def __init__(self):
        super(ESPCN, self).__init__()

        self.conv = Convd(, , )
        self.conv = Convd(, , )
        self.conv = Convd(, , )
        self.conv = Convd(,   (), , False)   放大倍率为，最后一层不激活

        self.ps = nn.PixelShuffle()

    def forward(self, x):
        x = self.conv(x)
        x = self.conv(x)
        x = self.conv(x)
        x = self.conv(x)
        x = self.ps(x)

        return x
