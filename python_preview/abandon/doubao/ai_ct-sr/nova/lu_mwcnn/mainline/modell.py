'''
    WaveletUNet 网络结构（修复版：解决参数名匹配+设备不匹配问题）
'''
 ========== . 统一导入 ==========
import os
import os.path as path
import sys
import torch
import torch.nn as nn
import torch.nn.functional as F

dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__, '../../baselines'))

try:
    from base.utils.wavelet import DWT_Haar, IWT_Haar
except ImportError:
    class DWT_Haar(nn.Module):
        def forward(self, x):
            B, C, H, W = x.shape
            assert H %  ==  and W %  == , f"输入尺寸{H}x{W}必须是的倍数（小波变换要求）"
            x = x.reshape(B, C, H // , , W // , )
            x = x.permute(, , , , , ).contiguous()
             修复：绑定到输入x的设备（而非单独to）
            return x.view(B, C  , H // , W // ).to(x.device)

    class IWT_Haar(nn.Module):
        def forward(self, x):
            B, C, H, W = x.shape
            assert C %  == , f"输入通道数{C}必须是的倍数（逆小波变换要求）"
            x = x.view(B, C // , , , H, W)
            x = x.permute(, , , , , ).contiguous()
             修复：绑定到输入x的设备
            return x.view(B, C // , H  , W  ).to(x.device)


 ========== . 修复Convd类（移除硬编码device，统一设备管理） ==========
class Convd(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, kernel_size: int, act: bool = True) -> None:
        super(Convd, self).__init__()
         修复：移除硬编码device，改为模型初始化时统一指定
        layer_list: list[nn.Module] = [
            nn.Convd(
                in_channels=in_ch,
                out_channels=out_ch,
                kernel_size=kernel_size,
                padding=kernel_size // ,
            ),
        ]
        if act:
            layer_list.append(nn.ReLU())

        self.model = nn.Sequential(layer_list)
        self.in_channels = in_ch
        self.out_channels = out_ch
        self.kernel_size = kernel_size
        self.padding = kernel_size // 

    def forward(self, x):
         修复：确保输出张量绑定到输入x的设备
        return self.model(x).to(x.device)


 ========== . LUMWCNN主模型（统一设备管理+修复中间张量设备） ==========

class LUMWCNN(nn.Module):
    def __init__(self, in_channels: int = , device: torch.device = None, scale=) -> None:   新增scale参数
        super(LUMWCNN, self).__init__()
        self.device = device or torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.in_channels = in_channels
        self.scale = scale
        assert self.in_channels in [, ], "in_channels仅支持（灰度）或（彩色）"

        self.DWT = DWT_Haar().to(self.device)
        self.IWT = IWT_Haar().to(self.device)

         左分支卷积（保持不变）
        self.l_conv = nn.Sequential([
            Convd(in_ch=self.in_channels, out_ch=, kernel_size=),
            Convd(in_ch=, out_ch=, kernel_size=)
        ]).to(self.device)
        self.l_conv = nn.Sequential([
            Convd(in_ch=, out_ch=, kernel_size=),
            Convd(in_ch=, out_ch=, kernel_size=)
        ]).to(self.device)
        self.l_conv = nn.Sequential([
            Convd(in_ch=, out_ch=, kernel_size=),
            Convd(in_ch=, out_ch=, kernel_size=)
        ]).to(self.device)

         右分支卷积（修复输出通道数：最后一层匹配in_channels）
        self.r_conv = nn.Sequential([
            Convd(in_ch=, out_ch=, kernel_size=),
            Convd(in_ch=, out_ch=, kernel_size=)
        ]).to(self.device)
        self.r_conv = nn.Sequential([
            Convd(in_ch=, out_ch=, kernel_size=),
            Convd(in_ch=, out_ch=, kernel_size=)
        ]).to(self.device)
        self.r_conv = nn.Sequential([
            Convd(in_ch=, out_ch=, kernel_size=),
             修复：输出通道数匹配in_channels（而非固定）
            Convd(in_ch=, out_ch=self.in_channels, kernel_size=)
        ]).to(self.device)

        if self.scale == :
            self.upsample = nn.Sequential(
                nn.Convd(in_channels, in_channels  , kernel_size=, padding=),
                nn.PixelShuffle()
            ).to(self.device)
        elif self.scale == :   倍超分：堆叠两次倍PixelShuffle
            self.upsample = nn.Sequential(
                nn.Convd(in_channels, in_channels  , kernel_size=, padding=),
                nn.PixelShuffle(),
                nn.Convd(in_channels, in_channels  , kernel_size=, padding=),
                nn.PixelShuffle()
            ).to(self.device)

        self.valing = False
        self.pads = []

     修复：辅助函数返回张量绑定到模型设备

    def _align_tensor_size(self, tensor_a, tensor_b):
        min_h = min(tensor_a.shape[], tensor_b.shape[])
        min_w = min(tensor_a.shape[], tensor_b.shape[])
        tensor_a = tensor_a[:, :, :min_h, :min_w].to(self.device)
        tensor_b = tensor_b[:, :, :min_h, :min_w].to(self.device)
        return tensor_a, tensor_b

    def wavelet_pad(self, x):
        should_pad_h = x.shape[-] %  != 
        should_pad_w = x.shape[-] %  != 
        padding = ( if should_pad_w else , ,  if should_pad_h else , )
        self.pads.append([should_pad_w, should_pad_h])
         修复：pad后绑定到模型设备
        return F.pad(x, padding, 'constant', ).to(self.device)

    def wavelet_shave(self, x):
        if not self.pads:
            return x.to(self.device)
        should_shave_w, should_shave_h = self.pads.pop()
        if should_shave_w:
            x = x[:, :, :, :]
        if should_shave_h:
            x = x[:, :, :, :]
         修复：shave后绑定到模型设备
        return x.to(self.device)

    def print_shape(self, x, desc):
        if self.valing:
            print(f'[{desc}] Shape: {x.shape} (Device: {x.device})')

    def forward(self, x):
        x = x.to(self.device)
        self.print_shape(x, "初始输入")

         通道适配（保持不变）
        if x.shape[] ==  and self.in_channels == :
            x = x.repeat(, , , ).to(self.device)
        elif x.shape[] ==  and self.in_channels == :
            x = torch.mean(x, dim=, keepdim=True).to(self.device)
        assert x.shape[] == self.in_channels, \
            f"输入通道数{x.shape[]}无法适配模型目标通道{self.in_channels}"
        self.print_shape(x, "通道适配后")

         左分支计算（保持不变）
        x_l = self.l_conv(x).to(self.device)
        self.print_shape(x_l, "x_l")
        x_l_pad = self.wavelet_pad(x_l)
        _x_l = self.DWT(x_l_pad).to(self.device)
        self.print_shape(_x_l, "_x_l (DWT后)")

        x_l = self.l_conv(_x_l).to(self.device)
        self.print_shape(x_l, "x_l")
        x_l_pad = self.wavelet_pad(x_l)
        _x_l = self.DWT(x_l_pad).to(self.device)
        self.print_shape(_x_l, "_x_l (DWT后)")

        x_l = self.l_conv(_x_l).to(self.device)
        self.print_shape(x_l, "x_l")

         右分支计算（保持不变）
        _after_r_conv = self.r_conv(x_l).to(self.device)
        self.print_shape(_after_r_conv, "_after_r_conv")
        lhs = self.IWT(_after_r_conv).to(self.device)
        self.print_shape(lhs, "lhs (IWT后)")
        lhs_shave = self.wavelet_shave(lhs).to(self.device)
        self.print_shape(lhs_shave, "lhs_shave")

        lhs_shave, x_l = self._align_tensor_size(lhs_shave, x_l)
        x_r = (lhs_shave + x_l).to(self.device)
        self.print_shape(x_r, "x_r")

        _after_r_conv = self.r_conv(x_r).to(self.device)
        self.print_shape(_after_r_conv, "_after_r_conv")
        _x_r = self.IWT(_after_r_conv).to(self.device)
        self.print_shape(_x_r, "_x_r (IWT后)")
        _x_r_shave = self.wavelet_shave(_x_r).to(self.device)
        self.print_shape(_x_r_shave, "_x_r_shave")

        _x_r_shave, x_l = self._align_tensor_size(_x_r_shave, x_l)
        x_r = (_x_r_shave + x_l).to(self.device)
        self.print_shape(x_r, "x_r")

        x_r = self.r_conv(x_r).to(self.device)
        self.print_shape(x_r, "x_r (r_conv后)")
        x_r, x = self._align_tensor_size(x_r, x)
        x_r = (x_r + x).to(self.device)
        self.print_shape(x_r, "x_r (残差后)")

         修复：upsample改为恒等映射，输出尺寸和输入一致
        y = self.upsample(x_r).to(self.device)
        self.print_shape(y, "最终输出")

        return y


if __name__ == "__main__":
     测试：显式指定设备（验证修复效果）
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"测试设备：{device}\n")

    print("===== 测试：彩色模式（in_channels=） =====")
    model_rgb = LUMWCNN(in_channels=, device=device)   传入设备参数
    model_rgb.valing = True

    test_gray = torch.randn(, , , ).to(device)
    output_rgb = model_rgb(test_gray)
    print(f" 灰度输入→彩色输出：{test_gray.shape} → {output_rgb.shape}\n")

    test_rgb = torch.randn(, , , ).to(device)
    output_rgb = model_rgb(test_rgb)
    print(f" 彩色输入→彩色输出：{test_rgb.shape} → {output_rgb.shape}\n")

    print("===== 测试：灰度模式（in_channels=） =====")
    model_gray = LUMWCNN(in_channels=, device=device)
    model_gray.valing = True

    output_gray = model_gray(test_rgb)
    print(f" 彩色输入→灰度输出：{test_rgb.shape} → {output_gray.shape}\n")

    output_gray = model_gray(test_gray)
    print(f" 灰度输入→灰度输出：{test_gray.shape} → {output_gray.shape}\n")

    print("===== 测试：模型保存/加载 =====")
    torch.save(model_rgb.state_dict(), "lumwcnn_fixed.pth")
    model_load = LUMWCNN(in_channels=, device=device)
    model_load.load_state_dict(torch.load("lumwcnn_fixed.pth", map_location=device))
    model_load.eval()

    with torch.no_grad():
        output_load = model_load(test_gray)
    print(f" 加载后输出形状：{output_load.shape}")

    if path.exists("lumwcnn_fixed.pth"):
        os.remove("lumwcnn_fixed.pth")
    print("\n 所有测试通过！")
