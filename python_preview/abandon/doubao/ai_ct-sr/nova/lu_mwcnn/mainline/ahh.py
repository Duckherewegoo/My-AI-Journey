import torch.nn.functional as F
import torch.nn as nn
import os
import shutil
import numpy as np
import torch
import torchvision.transforms as transforms
import pydicom
from PIL import Image
import lpips
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

# ---------------------- 配置参数 ----------------------
# FIXME: 占位符，改成你的检查点根目录
CKPT_SOURCE_DIR = "./continual_ckpt/luna/"

# 分类结果父目录（自动创建 the/good、the/ugly、the/bad）
CLASSIFY_ROOT_DIR = "./the"

# FIXME: 占位符，改为你实际的测试集路径
TEST_HR_DICOM_DIR = "/home/dake/Downloads/f-main/"                                  # 高分辨率 CT DICOM（标签）
TEST_HR_IMAGE_DIR = "/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/test/HR/"  # 高分辨率普通图像（标签）

# 模型参数（与 LUMWCNN 保持一致）
MODEL_IN_CHANNELS = 1       # CT 图像为单通道
MODEL_SCALE = 4             # 超分放大倍数
DROPOUT_RATE = 0.1          # FIXME: 需确认，参考训练脚本

# 分类阈值（FIXME: 可根据任务需求调整）
CLASSIFY_THRESHOLDS = {
    "good": {
        "psnr_min": 30.0,       # PSNR ≥ 30
        "ssim_min": 0.9,        # SSIM ≥ 0.9
        "lpips_max": 0.1,       # LPIPS ≤ 0.1
    },
    "ugly": {
        "psnr_min": 25.0,       # 25 ≤ PSNR < 30
        "psnr_max": 30.0,
        "ssim_min": 0.7,        # 0.7 ≤ SSIM < 0.9
        "ssim_max": 0.9,
        "lpips_min": 0.1,       # 0.1 < LPIPS ≤ 0.3
        "lpips_max": 0.3,
    },
    "bad": {
        "psnr_max": 25.0,       # PSNR < 25
        "ssim_max": 0.7,        # SSIM < 0.7
        "lpips_min": 0.3,       # LPIPS > 0.3
    }
}

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ---------------------- 复现训练时的图像处理类 ----------------------

class ResizeIfSmaller(object):
    """将图像缩放到最小尺寸（保证尺寸为 SCALE 的倍数）"""

    def __init__(self, min_size):
        self.min_size = min_size

    def __call__(self, img):
        w, h = img.size
        scale = max(self.min_size / w, self.min_size / h, 1.0)
        new_w = int(w * scale)
        new_h = int(h * scale)
        # 保证尺寸能被超分倍数整除，方便生成 LR
        new_w = new_w if (new_w % 2 == 0 and new_w % MODEL_SCALE == 0) else new_w + (MODEL_SCALE - new_w % MODEL_SCALE)
        new_h = new_h if (new_h % 2 == 0 and new_h % MODEL_SCALE == 0) else new_h + (MODEL_SCALE - new_h % MODEL_SCALE)
        if new_w != w or new_h != h:
            img = img.resize((new_w, new_h), Image.BICUBIC)
        return img


class CTEnhanceTransform:
    """CT 影像专用数据增强：旋转 + 平移 + 归一化 + 高斯噪声（评估阶段关闭随机增强）"""

    def __init__(self, rotate_range=15, translate_range=0.1, noise_std=0.01, eval_mode=False):
        self.rotate_range = rotate_range
        self.translate_range = translate_range
        self.noise_std = noise_std
        self.eval_mode = eval_mode   # 评估模式：关闭随机旋转/平移/噪声

    def __call__(self, img):
        # 评估模式：关闭随机旋转
        angle = 0.0 if self.eval_mode else np.random.uniform(-self.rotate_range, self.rotate_range)
        img = img.rotate(angle, resample=Image.BICUBIC, fillcolor=0)

        # 评估模式：关闭随机平移
        w, h = img.size
        dx = 0 if self.eval_mode else int(np.random.uniform(-self.translate_range, self.translate_range) * w)
        dy = 0 if self.eval_mode else int(np.random.uniform(-self.translate_range, self.translate_range) * h)
        img = Image.fromarray(np.roll(np.array(img), (dy, dx), axis=(0, 1)))

        # CT 值归一化：[-1024, 3071] → [0, 1]
        img_np = np.array(img, dtype=np.float32)
        img_np = (img_np - (-1024)) / (3071 - (-1024))
        img_np = np.clip(img_np, 0., 1.)
        img = Image.fromarray((img_np * 255).astype(np.uint8))

        # 评估模式：关闭高斯噪声
        if not self.eval_mode and np.random.rand() < 0.5:
            img_np = np.array(img, dtype=np.float32) / 255.
            noise = np.random.normal(0, self.noise_std, img_np.shape)
            img_np = np.clip(img_np + noise, 0, 1)
            img = Image.fromarray((img_np * 255).astype(np.uint8))

        return img


def generate_lr_from_hr(hr_img, min_size=128):
    """
    按训练逻辑从 HR 图像生成 LR 图像
    步骤：ResizeIfSmaller → CTEnhanceTransform（评估模式）→ 下采样（与超分倍数匹配）
    """
    eval_transform = transforms.Compose([
        ResizeIfSmaller(min_size),
        CTEnhanceTransform(eval_mode=True),
        transforms.ToTensor(),
    ])

    hr_tensor = eval_transform(hr_img).to(DEVICE)
    hr_h, hr_w = hr_tensor.shape[1], hr_tensor.shape[2]

    # 下采样生成 LR（HR / scale）
    lr_h, lr_w = hr_h // MODEL_SCALE, hr_w // MODEL_SCALE
    lr_tensor = transforms.Resize((lr_h, lr_w), interpolation=Image.BICUBIC)(hr_tensor)

    lr_pil = transforms.ToPILImage()(lr_tensor.detach().cpu())
    return lr_tensor, hr_tensor, lr_pil


# ---------------------- LUMWCNN 模型定义 ----------------------

class DWT_Haar(nn.Module):
    """哈尔小波变换（下采样）"""

    def forward(self, x):
        B, C, H, W = x.shape
        assert H % 2 == 0 and W % 2 == 0, f"输入尺寸{H}x{W}必须是2的倍数"
        x = x.reshape(B, C, H // 2, 2, W // 2, 2)
        x = x.permute(0, 1, 3, 5, 2, 4).contiguous()
        return x.view(B, C * 4, H // 2, W // 2)


class IWT_Haar(nn.Module):
    """哈尔小波逆变换（上采样）"""

    def forward(self, x):
        B, C, H, W = x.shape
        assert C % 4 == 0, f"输入通道数{C}必须是4的倍数"
        x = x.view(B, C // 4, 2, 2, H, W)
        x = x.permute(0, 1, 4, 2, 5, 3).contiguous()
        return x.view(B, C // 4, H * 2, W * 2)


class Convd(nn.Module):
    """带 Dropout 和 ReLU 的卷积模块"""

    def __init__(self, in_ch: int, out_ch: int, kernel_size: int,
                 act: bool = True, dropout: float = 0.0) -> None:
        super(Convd, self).__init__()
        layer_list = [nn.Conv2d(in_ch, out_ch, kernel_size, padding=kernel_size // 2)]
        if dropout > 0:
            layer_list.append(nn.Dropout2d(dropout))   # FIXME: 原代码写 Dropoutd，可能是 Dropout2d
        if act:
            layer_list.append(nn.ReLU())
        self.model = nn.Sequential(*layer_list)

    def forward(self, x):
        return self.model(x)


class LUMWCNN(nn.Module):
    """LUMWCNN 主模型：基于小波变换的超分网络（通道数来自 ckp）"""

    def __init__(self, in_channels: int = 1, device=None, scale=4, dropout: float = 0.0) -> None:
        super(LUMWCNN, self).__init__()
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.in_channels = in_channels
        self.scale = scale
        assert self.in_channels in [1, 3], "in_channels 仅支持 1/3"

        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

        # 左侧编码路径（通道数来自 ckp）
        self.l_conv1 = nn.Sequential(
            Convd(self.in_channels, 64, 3, dropout=dropout),
            Convd(64, 64, 3, dropout=dropout),
        )
        self.l_conv2 = nn.Sequential(
            Convd(256, 128, 3, dropout=dropout),    # DWT 后 64*4=256
            Convd(128, 128, 3, dropout=dropout),
        )
        self.l_conv3 = nn.Sequential(
            Convd(512, 256, 3, dropout=dropout),    # DWT 后 128*4=512
            Convd(256, 256, 3, dropout=dropout),
        )

        # 右侧解码路径（通道数来自 ckp）
        self.r_conv3 = nn.Sequential(
            Convd(256, 256, 3, dropout=dropout),
            Convd(256, 512, 3, dropout=dropout),
        )
        self.r_conv2 = nn.Sequential(
            Convd(128, 128, 3, dropout=dropout),
            Convd(128, 256, 3, dropout=dropout),
        )
        self.r_conv1 = nn.Sequential(
            Convd(64, 64, 3, dropout=dropout),
            Convd(64, self.in_channels, 3, dropout=0.0),
        )

        # 上采样（PixelShuffle）
        if self.scale == 2:
            self.upsample = nn.Sequential(
                nn.Conv2d(in_channels, in_channels * 4, 3, padding=1, groups=1),
                nn.PixelShuffle(2),
            )
        elif self.scale == 4:
            self.upsample = nn.Sequential(
                nn.Conv2d(in_channels, in_channels * 4, 3, padding=1, groups=1),
                nn.PixelShuffle(2),
                nn.Conv2d(in_channels, in_channels * 4, 3, padding=1, groups=1),
                nn.PixelShuffle(2),
            )
        else:
            raise ValueError("scale 仅支持 2 或 4")

        self.pads = []

    def _align_tensor_size(self, tensor_a, tensor_b):
        min_h = min(tensor_a.shape[2], tensor_b.shape[2])
        min_w = min(tensor_a.shape[3], tensor_b.shape[3])
        return tensor_a[:, :, :min_h, :min_w], tensor_b[:, :, :min_h, :min_w]

    def wavelet_pad(self, x):
        pad_h = 1 if x.shape[-2] % 2 != 0 else 0
        pad_w = 1 if x.shape[-1] % 2 != 0 else 0
        self.pads.append([pad_w, pad_h])
        return F.pad(x, (0, pad_w, 0, pad_h), "constant", 0)

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
        x = x.to(self.device)
        self.pads = []   # 每次推理重置 padding 记录

        # 通道适配
        if x.shape[1] == 3 and self.in_channels == 1:
            x = torch.mean(x, dim=1, keepdim=True)
        elif x.shape[1] == 1 and self.in_channels == 3:
            x = x.repeat(1, 3, 1, 1)

        # 编码
        x_l1 = self.l_conv1(x)
        x_l2 = self.l_conv2(self.DWT(self.wavelet_pad(x_l1)))
        x_l3 = self.l_conv3(self.DWT(self.wavelet_pad(x_l2)))

        # 解码 + 残差
        x_r = self.wavelet_shave(self.IWT(self.r_conv3(x_l3)))
        x_r, x_l2 = self._align_tensor_size(x_r, x_l2)
        x_r = x_r + x_l2

        x_r = self.wavelet_shave(self.IWT(self.r_conv2(x_r)))
        x_r, x_l1 = self._align_tensor_size(x_r, x_l1)
        x_r = x_r + x_l1

        x_r = self.r_conv1(x_r)
        x_r, x = self._align_tensor_size(x_r, x)
        x_r = x_r + x

        y = self.upsample(x_r)
        y = torch.clamp(y, 0., 1.)
        return y


# ---------------------- 工具函数 ----------------------

def load_dicom_to_pil(dicom_path):
    """加载 DICOM 文件并转为 PIL 图像"""
    dicom_data = pydicom.dcmread(dicom_path)
    img_np = dicom_data.pixel_array.astype(np.uint16)   # 保留原始 CT 值
    img_pil = Image.fromarray(img_np).convert('L')
    return img_pil


def load_image_to_pil(image_path):
    """加载普通图像（bmp/png 等）并转为 PIL 灰度图"""
    return Image.open(image_path).convert('L')


def calculate_metrics(sr_tensor, hr_tensor, lpips_model):
    """计算真实评估指标：PSNR、SSIM、LPIPS"""
    sr_np = sr_tensor.detach().cpu().squeeze().numpy()
    hr_np = hr_tensor.detach().cpu().squeeze().numpy()

    # 对齐尺寸
    min_h = min(sr_np.shape[0], hr_np.shape[0])
    min_w = min(sr_np.shape[1], hr_np.shape[1])
    sr_np = sr_np[:min_h, :min_w]
    hr_np = hr_np[:min_h, :min_w]

    # PSNR
    psnr = peak_signal_noise_ratio(hr_np, sr_np, data_range=1.0)

    # SSIM（win_size=11，要求图像至少 11x11）
    ssim = structural_similarity(hr_np, sr_np, data_range=1.0, win_size=11)

    # LPIPS：输入归一化到 [-1, 1]，并增加 batch 维度
    sr_lpips = (sr_tensor.unsqueeze(0) * 2) - 1
    hr_lpips = (hr_tensor.unsqueeze(0) * 2) - 1
    lpips_score = lpips_model(sr_lpips, hr_lpips).detach().cpu().item()

    return {"psnr": psnr, "ssim": ssim, "lpips": lpips_score}


# ---------------------- 核心逻辑 ----------------------

def classify_ckpts():
    # 1. 创建分类目录
    good_dir = os.path.join(CLASSIFY_ROOT_DIR, "good")
    ugly_dir = os.path.join(CLASSIFY_ROOT_DIR, "ugly")
    bad_dir = os.path.join(CLASSIFY_ROOT_DIR, "bad")
    for dir_path in [good_dir, ugly_dir, bad_dir]:
        os.makedirs(dir_path, exist_ok=True)

    # 2. 收集所有检查点
    ckpt_files = [f for f in os.listdir(CKPT_SOURCE_DIR) if f.endswith(".pth")]
    if not ckpt_files:
        print(f"错误：在 {CKPT_SOURCE_DIR} 中未找到任何 .pth 检查点文件")
        return

    # 3. 初始化 LPIPS
    lpips_model = lpips.LPIPS(net='alex').to(DEVICE)
    lpips_model.eval()

    classify_report = {"good": [], "ugly": [], "bad": []}

    for ckpt_file in ckpt_files:
        ckpt_path = os.path.join(CKPT_SOURCE_DIR, ckpt_file)
        print(f"\n正在处理检查点：{ckpt_file}")

        try:
            # 加载检查点和模型
            checkpoint = torch.load(ckpt_path, map_location=DEVICE)
            model = LUMWCNN(
                in_channels=MODEL_IN_CHANNELS,
                device=DEVICE,
                scale=MODEL_SCALE,
                dropout=DROPOUT_RATE,
            )
            model.load_state_dict(checkpoint["model_state_dict"])
            model.to(DEVICE)
            model.eval()

            metrics_list = []

            # ① 处理 DICOM 测试集
            if os.path.exists(TEST_HR_DICOM_DIR):
                dicom_files = [f for f in os.listdir(TEST_HR_DICOM_DIR) if f.endswith(".dcm")]
                for dicom_file in dicom_files:
                    dicom_path = os.path.join(TEST_HR_DICOM_DIR, dicom_file)
                    hr_pil = load_dicom_to_pil(dicom_path)
                    lr_tensor, hr_tensor, _ = generate_lr_from_hr(hr_pil)
                    with torch.no_grad():
                        sr_tensor = model(lr_tensor.unsqueeze(0)).squeeze(0)
                    metrics = calculate_metrics(sr_tensor, hr_tensor, lpips_model)
                    metrics_list.append(metrics)

            # ② 处理普通图像测试集
            if os.path.exists(TEST_HR_IMAGE_DIR):
                hr_image_files = [
                    f for f in os.listdir(TEST_HR_IMAGE_DIR)
                    if f.lower().endswith((".bmp", ".png", ".jpg", ".jpeg"))
                ]
                for hr_image_file in hr_image_files:
                    hr_image_path = os.path.join(TEST_HR_IMAGE_DIR, hr_image_file)
                    hr_pil = load_image_to_pil(hr_image_path)
                    lr_tensor, hr_tensor, _ = generate_lr_from_hr(hr_pil)
                    with torch.no_grad():
                        sr_tensor = model(lr_tensor.unsqueeze(0)).squeeze(0)
                    metrics = calculate_metrics(sr_tensor, hr_tensor, lpips_model)
                    metrics_list.append(metrics)

            if not metrics_list:
                print(f"警告：{ckpt_file} 无有效测试样本，归类为 bad")
                shutil.copy(ckpt_path, bad_dir)
                classify_report["bad"].append({"ckpt": ckpt_file, "reason": "无有效测试样本"})
                continue

            avg_metrics = {
                "psnr": float(np.mean([m["psnr"] for m in metrics_list])),
                "ssim": float(np.mean([m["ssim"] for m in metrics_list])),
                "lpips": float(np.mean([m["lpips"] for m in metrics_list])),
            }
            print(f"平均指标：PSNR={avg_metrics['psnr']:.2f}, SSIM={avg_metrics['ssim']:.4f}, LPIPS={avg_metrics['lpips']:.4f}")

            thresholds = CLASSIFY_THRESHOLDS
            ckpt_info = {"ckpt": ckpt_file, "metrics": avg_metrics}

            if (avg_metrics["psnr"] >= thresholds["good"]["psnr_min"] and
                avg_metrics["ssim"] >= thresholds["good"]["ssim_min"] and
                avg_metrics["lpips"] <= thresholds["good"]["lpips_max"]):
                shutil.copy(ckpt_path, good_dir)
                classify_report["good"].append(ckpt_info)
            elif (avg_metrics["psnr"] >= thresholds["ugly"]["psnr_min"] and
                  avg_metrics["psnr"] < thresholds["ugly"]["psnr_max"] and
                  avg_metrics["ssim"] >= thresholds["ugly"]["ssim_min"] and
                  avg_metrics["ssim"] < thresholds["ugly"]["ssim_max"] and
                  avg_metrics["lpips"] > thresholds["ugly"]["lpips_min"] and
                  avg_metrics["lpips"] <= thresholds["ugly"]["lpips_max"]):
                shutil.copy(ckpt_path, ugly_dir)
                classify_report["ugly"].append(ckpt_info)
            else:
                shutil.copy(ckpt_path, bad_dir)
                classify_report["bad"].append(ckpt_info)

        except Exception as e:
            print(f"错误：处理 {ckpt_file} 失败，归类为 bad，错误信息：{str(e)}")
            shutil.copy(ckpt_path, bad_dir)
            classify_report["bad"].append({"ckpt": ckpt_file, "reason": f"处理失败：{str(e)}"})
            continue

    # 打印分类报告
    print("\n" + "=" * 60)
    print("分类完成！汇总报告：")
    print(f"good（可胜任）：{len(classify_report['good'])} 个检查点")
    for item in classify_report['good']:
        m = item['metrics']
        print(f"  - {item['ckpt']}：PSNR={m['psnr']:.2f}, SSIM={m['ssim']:.4f}, LPIPS={m['lpips']:.4f}")

    print(f"\nugly（不完全胜任）：{len(classify_report['ugly'])} 个检查点")
    for item in classify_report['ugly']:
        m = item['metrics']
        print(f"  - {item['ckpt']}：PSNR={m['psnr']:.2f}, SSIM={m['ssim']:.4f}, LPIPS={m['lpips']:.4f}")

    print(f"\nbad（完全不能胜任）：{len(classify_report['bad'])} 个检查点")
    for item in classify_report['bad']:
        print(f"  - {item['ckpt']}：{item.get('reason', '指标不达标')}")
    print("=" * 60)


if __name__ == "__main__":
    classify_ckpts()
