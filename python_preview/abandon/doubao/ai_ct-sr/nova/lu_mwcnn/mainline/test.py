import os
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from PIL import Image
from tqdm import tqdm
from skimage.metrics import peak_signal_noise_ratio as psnr
from skimage.metrics import structural_similarity as ssim

 ===================== 【% 匹配你的训练模型】 =====================
from base.utils.wavelet import DWT_Haar, IWT_Haar


class Convd(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, kernel_size: int, act: bool = True) -> None:
        super(Convd, self).__init__()
        layers = [
            nn.Convd(in_ch, out_ch, kernel_size, padding=kernel_size // , bias=False),
            nn.BatchNormd(out_ch),
        ]
        if act:
            layers.append(nn.ReLU(inplace=True))
        self.layers = nn.Sequential(layers)

    def forward(self, x): return self.layers(x)


class LUMWCNN(nn.Module):
    def __init__(self) -> None:
        super(LUMWCNN, self).__init__()
        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()
        self.pad_info = {}

        self.l_conv = nn.Sequential(Convd(, , ), Convd(, , ))
        self.l_conv = nn.Sequential(Convd(, , ), Convd(, , ))
        self.l_conv = nn.Sequential(Convd(, , ), Convd(, , ))

        self.r_conv = nn.Sequential(Convd(, , ), Convd(, , ))
        self.r_conv = nn.Sequential(Convd(, , ), Convd(, , ))
        self.r_conv = nn.Sequential(Convd(, , ), Convd(, , , act=False))

        self.upsample = nn.Sequential(
            Convd(, , ), Convd(,   , ), nn.PixelShuffle(),
            Convd(, , ), Convd(,   , ), nn.PixelShuffle(),
            nn.Convd(, , , padding=, bias=False), nn.Sigmoid()
        )

    def forward(self, x):
        x_l = self.l_conv(x)
        x_l_pad = self.wavelet_pad(x_l, 'l')
        _x_l = self.DWT(x_l_pad)
        x_l = self.l_conv(_x_l)
        x_l_pad = self.wavelet_pad(x_l, 'l')
        _x_l = self.DWT(x_l_pad)
        x_l = self.l_conv(_x_l)

        _after_r_conv = self.r_conv(x_l)
        lhs = self.IWT(_after_r_conv)
        lhs_shave = self.wavelet_shave(lhs, 'l')
        x_r = lhs_shave + x_l

        _after_r_conv = self.r_conv(x_r)
        _x_r = self.IWT(_after_r_conv)
        x_r = self.wavelet_shave(_x_r, 'l') + x_l

        x_r = .  self.r_conv(x_r) + x
        y = self.upsample(x_r)
        return torch.clamp(y, , )

    def wavelet_pad(self, x, key):
        pad_h = x.shape[-] %  != 
        pad_w = x.shape[-] %  != 
        self.pad_info[key] = [pad_w, pad_h]
        return F.pad(x, ( if pad_w else , ,  if pad_h else , ))

    def wavelet_shave(self, x, key):
        if key not in self.pad_info:
            return x
        w, h = self.pad_info.pop(key)
        if w:
            x = x[:, :, :, :-]
        if h:
            x = x[:, :, :-, :]
        return x


 ===================== 路径配置 =====================
DEVICE = torch.device("cpu")
WEIGHT_PATH = "/run/media/dake/Software/Projects/Graduction_Projects/codes/nova/lu_mwcnn/mainline/output_deeplesion/goat/best_luna_ct_psnr_epoch_.pth"
TEST_ROOT = "/home/dake/Documents/Project/datasets/LUNA/sr_slice_dataset/test"
SCALE = 
TEST_NUM =    只测张！

 ===================== 预处理 =====================


def preprocess(img_path):
    img = Image.open(img_path).convert("L")
    return torch.from_numpy(np.array(img)).float().unsqueeze().unsqueeze() / .


 ===================== 加载模型 =====================
model = LUMWCNN().to(DEVICE)
model.load_state_dict(torch.load(WEIGHT_PATH, map_location=DEVICE))
model.eval()
print(" 模型+权重加载成功！\n")

 ===================== 测试前张图片 =====================
hr_dir = os.path.join(TEST_ROOT, "HR") if os.path.exists(os.path.join(TEST_ROOT, "HR")) else TEST_ROOT
img_list = sorted([f for f in os.listdir(hr_dir) if f.endswith((".png", ".jpg"))])[:TEST_NUM]

psnr_list = []
ssim_list = []

with torch.no_grad():
    for name in tqdm(img_list, desc=f"测试前{TEST_NUM}张CT"):
         读取高清图 → 生成低清图 → 超分
        hr = preprocess(os.path.join(hr_dir, name)).to(DEVICE)
        lr = F.interpolate(hr, scale_factor= / SCALE, mode="bicubic")
        sr = model(lr)

         计算指标
        sr = (sr.squeeze().cpu().numpy()  ).astype(np.uint)
        hr = (hr.squeeze().cpu().numpy()  ).astype(np.uint)
        psnr_list.append(psnr(hr, sr, data_range=))
        ssim_list.append(ssim(hr, sr, data_range=))

 ===================== 输出结果 =====================
print("\n" + "="  )
print(f" 前{TEST_NUM}张 CT 测试结果")
print(f"平均 PSNR: {np.mean(psnr_list):.f} dB")
print(f"平均 SSIM: {np.mean(ssim_list):.f}")
print("="  )

if np.mean(psnr_list) >=  and np.mean(ssim_list) >= .:
    print(" 权重质量：合格/优秀，可直接用于医学系统！")
else:
    print("️  权重质量：一般")
