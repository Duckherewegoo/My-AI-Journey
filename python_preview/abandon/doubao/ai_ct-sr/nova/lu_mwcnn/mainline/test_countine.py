import os
import torch
from PIL import Image
from tqdm import tqdm
from torch.utils.data import DataLoader, Subset
from torchvision import transforms
import torch.nn as nn
import torch.nn.functional as F
import lpips
from torchmetrics.image import StructuralSimilarityIndexMeasure

 ===================== 【全局配置】固定你的路径 + 写死CT文件夹 =====================
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
 根目录（你的权重总文件夹）
WEIGHT_ROOT = "/run/media/dake/Software/Projects/Graduction_Projects/codes/nova/lu_mwcnn/mainline/continual_ckpt"
 固定【仅允许扫描这个CT权重文件夹】
TARGET_CT_FOLDERS = {"best_luna", "best_deeplesionkey_ct", "best_covid"}
 CT测试集路径
CT_TEST_DIR = "/run/media/dake/Software/Projects/datasets/LUNA/sr_slice_dataset/test"
SCALE = 
 【极速测试】只取前张图，速度极快，足够判断权重质量
TEST_SAMPLE_COUNT = 
 结果保存文件
RESULT_FILE = "ct_best_weights_test_results.txt"

 ===================== 【模型定义】无修改 =====================


class DWT_Haar(nn.Module):
    def forward(self, x):
        B, C, H, W = x.shape
        assert H %  ==  and W %  == , f"输入尺寸{H}x{W}必须是的倍数"
        x = x.reshape(B, C, H // , , W // , )
        x = x.permute(, , , , , ).contiguous()
        return x.view(B, C  , H // , W // )


class IWT_Haar(nn.Module):
    def forward(self, x):
        B, C, H, W = x.shape
        assert C %  == , f"输入通道数{C}必须是的倍数"
        x = x.view(B, C // , , , H, W)
        x = x.permute(, , , , , ).contiguous()
        return x.view(B, C // , H  , W  )


class Convd(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, kernel_size: int, act: bool = True, dropout: float = .):
        super(Convd, self).__init__()
        layer_list = [nn.Convd(in_ch, out_ch, kernel_size, padding=kernel_size // )]
        if dropout > :
            layer_list.append(nn.Dropoutd(dropout))
        if act:
            layer_list.append(nn.ReLU())
        self.model = nn.Sequential(layer_list)

    def forward(self, x): return self.model(x)


class LUMWCNN(nn.Module):
    def __init__(self, in_channels: int = , scale=, dropout: float = .):
        super(LUMWCNN, self).__init__()
        self.in_channels = in_channels
        self.scale = scale
        assert self.in_channels in [, ], "in_channels仅支持/"

        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

        self.l_conv = nn.Sequential(Convd(self.in_channels, , , dropout=dropout), Convd(, , , dropout=dropout))
        self.l_conv = nn.Sequential(Convd(, , , dropout=dropout), Convd(, , , dropout=dropout))
        self.l_conv = nn.Sequential(Convd(, , , dropout=dropout), Convd(, , , dropout=dropout))

        self.r_conv = nn.Sequential(Convd(, , , dropout=dropout), Convd(, , , dropout=dropout))
        self.r_conv = nn.Sequential(Convd(, , , dropout=dropout), Convd(, , , dropout=dropout))
        self.r_conv = nn.Sequential(Convd(, , , dropout=dropout), Convd(, self.in_channels, , dropout=.))

        if self.scale == :
            self.upsample = nn.Sequential(
                nn.Convd(in_channels, in_channels  , , , , groups=), nn.PixelShuffle(),
                nn.Convd(in_channels, in_channels  , , , , groups=), nn.PixelShuffle(),
            )
        self.pads = []

    def _align_tensor_size(self, tensor_a, tensor_b):
        min_h = min(tensor_a.shape[], tensor_b.shape[])
        min_w = min(tensor_a.shape[], tensor_b.shape[])
        return tensor_a[:, :, :min_h, :min_w], tensor_b[:, :, :min_h, :min_w]

    def wavelet_pad(self, x):
        pad_h =  if x.shape[-] %  !=  else 
        pad_w =  if x.shape[-] %  !=  else 
        self.pads.append([pad_w, pad_h])
        return F.pad(x, (, pad_w, , pad_h), "constant", )

    def wavelet_shave(self, x):
        if not self.pads:
            return x
        pad_w, pad_h = self.pads.pop()
        if pad_w:
            x = x[:, :, :, :-pad_w]
        if pad_h:
            x = x[:, :, :-pad_h, :]
        return x

    def forward(self, x):
        x_l = self.l_conv(x)
        x_l_pad = self.wavelet_pad(x_l)
        _x_l = self.DWT(x_l_pad)
        x_l = self.l_conv(_x_l)
        x_l_pad = self.wavelet_pad(x_l)
        _x_l = self.DWT(x_l_pad)
        x_l = self.l_conv(_x_l)

        _after_r_conv = self.r_conv(x_l)
        lhs = self.IWT(_after_r_conv)
        lhs_shave = self.wavelet_shave(lhs)
        lhs_shave, x_l = self._align_tensor_size(lhs_shave, x_l)
        x_r = lhs_shave + x_l

        _after_r_conv = self.r_conv(x_r)
        _x_r = self.IWT(_after_r_conv)
        _x_r_shave = self.wavelet_shave(_x_r)
        _x_r_shave, x_l = self._align_tensor_size(_x_r_shave, x_l)
        x_r = _x_r_shave + x_l

        x_r = self.r_conv(x_r)
        x_r, x = self._align_tensor_size(x_r, x)
        x_r = x_r + x

        y = self.upsample(x_r)
        y = torch.clamp(y, ., .)
        return y

 ===================== 【CT数据集】 =====================


class ResizeIfSmaller(object):
    def __init__(self, min_size): self.min_size = min_size

    def __call__(self, img):
        w, h = img.size
        scale = max(self.min_size / w, self.min_size / h, .)
        new_w = int(w  scale) if int(w  scale) %  ==  else int(w  scale) + 
        new_h = int(h  scale) if int(h  scale) %  ==  else int(h  scale) + 
        if new_w != w or new_h != h:
            img = img.resize((new_w, new_h), Image.BICUBIC)
        return img


class CTDataset(torch.utils.data.Dataset):
    def __init__(self, data_dir):
        self.img_paths = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".png")]
        self.transform = transforms.Compose([ResizeIfSmaller(), transforms.ToTensor()])

    def __getitem__(self, idx):
        img = Image.open(self.img_paths[idx]).convert("L")
        img = self.transform(img)
        C, H, W = img.shape
        new_H = (H // SCALE)  SCALE
        new_W = (W // SCALE)  SCALE
        img = img[:, :new_H, :new_W]
        lr_img = transforms.Resize((new_H // SCALE, new_W // SCALE), Image.BICUBIC)(img)
        return lr_img, img

    def __len__(self): return len(self.img_paths)

 ===================== 【指标计算】 =====================


class MetricCalculator:
    def __init__(self):
        self.lpips_model = lpips.LPIPS(net="vgg").eval().to(DEVICE)
        self.ssim_metric = StructuralSimilarityIndexMeasure(data_range=.).to(DEVICE)

    def calculate(self, sr_img, hr_img):
        sr_img = torch.clamp(sr_img, ., .).to(DEVICE)
        hr_img = torch.clamp(hr_img, ., .).to(DEVICE)
        mse = F.mse_loss(sr_img, hr_img)
        psnr =   torch.log(. / (mse + e-))
        ssim_val = self.ssim_metric(sr_img, hr_img)
        sr_lpips = sr_img.repeat(, , , )
        hr_lpips = hr_img.repeat(, , , )
        sr_lpips = (sr_lpips - .)  
        hr_lpips = (hr_lpips - .)  
        lpips_val = self.lpips_model(sr_lpips, hr_lpips).mean()
        return psnr.item(), ssim_val.item(), lpips_val.item()

 ===================== 【核心修复】精准扫描权重 =====================


def scan_all_weights():
    """仅扫描个指定CT文件夹，仅读取 best 开头的 .pth 文件"""
    weight_files = []
    for folder_name in os.listdir(WEIGHT_ROOT):
        folder_path = os.path.join(WEIGHT_ROOT, folder_name)
         . 只允许个指定CT文件夹
        if not os.path.isdir(folder_path) or folder_name not in TARGET_CT_FOLDERS:
            continue
         . 遍历文件，仅保留 best开头 + .pth结尾
        for file in os.listdir(folder_path):
            if file.startswith("best") and file.endswith(".pth"):
                weight_files.append((folder_name, os.path.join(folder_path, file)))
    print(f" 精准扫描完成：共找到 {len(weight_files)} 个CT最佳权重")
    return weight_files


def test_single_weight(folder_name, weight_path, metric_calc):
    """仅测试CT灰度图，极速模式（张图）"""
    try:
         固定CT灰度图配置
        task = "ct_gray"
        in_channels = 

         加载CT测试集 + 仅取前张（极速）
        test_set = CTDataset(CT_TEST_DIR)
        test_set = Subset(test_set, list(range(min(TEST_SAMPLE_COUNT, len(test_set)))))
        test_loader = DataLoader(test_set, batch_size=, shuffle=False, num_workers=)

         加载模型
        model = LUMWCNN(in_channels=in_channels, scale=SCALE).to(DEVICE)
        checkpoint = torch.load(weight_path, map_location=DEVICE, weights_only=True)
        model.load_state_dict(checkpoint["model_state_dict"] if "model_state_dict" in checkpoint else checkpoint, strict=False)
        model.eval()

         极速推理
        total_psnr, total_ssim, total_lpips, cnt = , , , 
        with torch.no_grad():
            for lr, hr in test_loader:
                lr, hr = lr.to(DEVICE), hr.to(DEVICE)
                sr = model(lr)
                sr, hr = model._align_tensor_size(sr, hr)
                p, s, l = metric_calc.calculate(sr, hr)
                total_psnr += p
                total_ssim += s
                total_lpips += l
                cnt += 

        avg_psnr = round(total_psnr / cnt, )
        avg_ssim = round(total_ssim / cnt, )
        avg_lpips = round(total_lpips / cnt, )
        return True, avg_psnr, avg_ssim, avg_lpips, task

    except Exception as e:
        print(f" 测试失败: {str(e)}")
        return False, ., ., ., None


 ===================== 【主程序】 =====================
if __name__ == "__main__":
    print("="  )
    print(" CT灰度图最佳权重极速测试工具（仅个指定文件夹）")
    print("="  )

    metric_calculator = MetricCalculator()
    all_weights = scan_all_weights()
    results = []

     遍历测试
    for folder, path in all_weights:
        weight_name = os.path.basename(path)
        print(f"\n 正在测试: {folder}/{weight_name}")
        success, psnr, ssim, lpips, task = test_single_weight(folder, path, metric_calculator)

        if success:
            results.append((folder, weight_name, task, psnr, ssim, lpips))
            print(f" 测试成功 | PSNR: {psnr} | SSIM: {ssim} | LPIPS: {lpips}")
        print("-"  )

     保存结果到文本文件
    with open(RESULT_FILE, "w", encoding="utf-") as f:
        f.write("="   + "\n")
        f.write(" CT最佳权重测试结果（极速张图评估）\n")
        f.write("="   + "\n")
        for res in results:
            folder, name, task, p, s, l = res
            f.write(f"[{folder}] {name} | PSNR: {p} | SSIM: {s} | LPIPS: {l}\n")
            f.write("-"   + "\n")

    print(f"\n 结果已保存至：{os.path.abspath(RESULT_FILE)}")
    print("="  )
