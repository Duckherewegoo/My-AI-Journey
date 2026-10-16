"""
magic_inherit_train.py —— LU-MWCNN 连续学习训练脚本（LoRA 微调版）

关键改动：
  1. 模型从 wavelet.py / model.py / loss.py 导入
  2. 从预训练 ckp 微调（不再从头训）
  3. 加入 LoRA for Conv2d —— 冻结原卷积，只训低秩旁路
  4. 针对 RTX 3060 8GB Laptop 做了显存优化（AMP + 梯度累积）
  5. upsample 模块保持完整训练（新任务可能需要它）
"""

import os
import sys
import time
import gc
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader, Subset
from torchvision import transforms
import numpy as np
from tqdm import tqdm
from PIL import Image
import os.path as path
from torch.utils.tensorboard.writer import SummaryWriter
import lpips
import warnings
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts
from torchmetrics.image import StructuralSimilarityIndexMeasure

# ====== 本项目的模块 ======
from wavelet import DWT_Haar, IWT_Haar
from model import Convd, LUMWCNN
from loss import JointLoss

warnings.filterwarnings("ignore")


# ==============================================================================
# 1. 全局配置
# ==============================================================================
DEEPLESION_CKPT = "./output_deeplesion/goat/best_luna16_ct_psnr_epoch_56.pth"
DIV2K_CKPT = "./output_div2k/div2k_resume_ckpt/div2k_rgb_epoch_500.pth"

LUNA16_DATA_DIR = r"../datasets/LUNA16/sr_slice_dataset/"
VOC2012_DATA_DIR = r"../datasets/VOC2012/sr_split/"
COVID_DATA_DIR = r"../datasets/COVID-19CT/COVID19-CT-Images/"
DIV2K_DATA_DIR = r"../datasets/DIV2K_HR/"
DEEPLESION_DATA_DIR = r"../datasets/DeepLesion/deeplesion_category_split/lung/"
DEEPLESION_KEY_DATA_DIR = r"../datasets/DeepLesion_Key_slices/"

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
SCALE = 4
BATCH_SIZE = 2                    # ← 从 4 降到 2（3060 8GB）
GRAD_ACCUM_STEPS = 2              # ← 梯度累积 2 步，等效 batch 4
LR = 1e-4                         # ← LoRA 用大 LR（比全量微调的 5e-6 大 20 倍）
WEIGHT_DECAY = 1e-4
EPOCHS = 1000
FREEZE_BACKBONE_EPOCHS = 0        # ← LoRA 已经冻结 backbone，不需要额外冻结期
EARLY_STOPPING_PATIENCE = 30
EARLY_STOPPING_MIN_DELTA = 1e-4
NUM_WORKERS = 2                   # ← 降到 2（laptop 上够用）
PREFETCH_FACTOR = 2

# ====== LoRA 配置 ======
LORA_RANK = 4                     # LoRA 秩，4~8 都可
LORA_ALPHA = 8.0                  # 缩放因子，一般 = 2×rank
LORA_DROPOUT = 0.0                # LoRA 层内的 dropout（一般 0）

CHECKPOINT_DIR = "./continual_ckpt_lora"
OUTPUT_DETAIL_DIR = "./output_detail"
TB_LOG_DIR = "./tb_logs"
TEST_OUTPUT_DIR = "./test_output"

for d in [CHECKPOINT_DIR, OUTPUT_DETAIL_DIR, TB_LOG_DIR, TEST_OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)


# ==============================================================================
# 2. LoRA for Conv2d
# ==============================================================================
class LoRAConv2d(nn.Module):
    """
    给冻结的 Conv2d 加低秩旁路。
      y = conv(x) + (alpha/r) * B(A(x))
      A: 1x1 conv, in_ch -> r
      B: 1x1 conv, r -> out_ch，零初始化
    """

    def __init__(self, base_conv: nn.Conv2d, rank=LORA_RANK,
                 alpha=LORA_ALPHA, dropout=LORA_DROPOUT):
        super().__init__()
        self.base_conv = base_conv
        for p in self.base_conv.parameters():
            p.requires_grad = False    # 冻结原卷积

        self.rank = rank
        self.scale = alpha / rank
        in_ch = base_conv.in_channels
        out_ch = base_conv.out_channels

        self.lora_A = nn.Conv2d(in_ch, rank, kernel_size=1,
                                stride=1, padding=0, bias=False)
        self.lora_B = nn.Conv2d(rank, out_ch, kernel_size=1,
                                stride=1, padding=0, bias=False)
        nn.init.kaiming_uniform_(self.lora_A.weight, a=np.sqrt(5))
        nn.init.zeros_(self.lora_B.weight)   # 零初始化 B → 初始输出 = 原模型

        if dropout > 0.0:
            self.lora_dropout = nn.Dropout2d(dropout)
        else:
            self.lora_dropout = nn.Identity()

    def forward(self, x):
        base = self.base_conv(x)
        lora = self.lora_B(self.lora_A(self.lora_dropout(x))) * self.scale
        return base + lora

    def merge(self):
        """推理时可以把 LoRA 合并进原卷积，减少计算量"""
        with torch.no_grad():
            delta_w = self.lora_B.weight @ self.lora_A.weight  # (out, in, 1, 1)
            delta_w = F.pad(delta_w, (1, 1, 1, 1))             # 3x3
            self.base_conv.weight.data += delta_w * self.scale
        return self.base_conv


def inject_lora_to_model(model: nn.Module, skip_prefixes=("upsample",)):
    """
    遍历模型，把每个 Conv2d 替换成 LoRAConv2d。
    - skip_prefixes 里的模块保持完整训练（不套 LoRA）
    - 其他所有 Conv2d → LoRAConv2d
    """
    def _replace(module, prefix=""):
        for name, child in module.named_children():
            full_name = f"{prefix}.{name}" if prefix else name
            if any(full_name.startswith(p) for p in skip_prefixes):
                # upsample 保持完整训练
                for p in child.parameters():
                    p.requires_grad = True
                print(f"  [完整训练] {full_name}")
                continue
            if isinstance(child, nn.Conv2d):
                setattr(module, name, LoRAConv2d(child))
                print(f"  [LoRA 注入] {full_name}  {child.in_channels}->{child.out_channels}")
            else:
                _replace(child, full_name)

    _replace(model)
    return model


def count_trainable(model):
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return total, trainable


# ==============================================================================
# 3. 工具类
# ==============================================================================
class Logger:
    def __init__(self, log_file):
        self.terminal = sys.stdout
        self.log = open(log_file, "a", encoding="utf-8")
        self.flush()

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()


class EarlyStopping:
    def __init__(self, patience=EARLY_STOPPING_PATIENCE,
                 min_delta=EARLY_STOPPING_MIN_DELTA, verbose=True):
        self.patience = patience
        self.min_delta = min_delta
        self.verbose = verbose
        self.counter = 0
        self.best_psnr = -float("inf")
        self.best_ssim = -float("inf")
        self.best_lpips = float("inf")
        self.early_stop = False

    def reset_counter(self):
        self.counter = 0
        if self.verbose:
            print("🔄 早停计数器已重置")

    def __call__(self, psnr, ssim, lpips_val):
        psnr_improved = psnr > (self.best_psnr + self.min_delta)
        ssim_improved = ssim > (self.best_ssim + self.min_delta)
        lpips_improved = lpips_val < (self.best_lpips - self.min_delta)
        any_improved = psnr_improved or ssim_improved or lpips_improved

        if psnr_improved: self.best_psnr = psnr
        if ssim_improved: self.best_ssim = ssim
        if lpips_improved: self.best_lpips = lpips_val

        if any_improved:
            self.counter = 0
        else:
            self.counter += 1
            if self.verbose:
                print(f"⏱️ EarlyStopping: {self.counter}/{self.patience} | "
                      f"PSNR={self.best_psnr:.2f} SSIM={self.best_ssim:.4f} LPIPS={self.best_lpips:.4f}")
            if self.counter >= self.patience:
                self.early_stop = True
                if self.verbose:
                    print("⚠️ Early stopping triggered!")
        return self.early_stop


class TBLogger:
    def __init__(self, log_dir=TB_LOG_DIR):
        self.log_dir = log_dir
        self.writers = {}
        self.lpips_model = lpips.LPIPS(net="vgg").eval().to(DEVICE)
        for p in self.lpips_model.parameters():
            p.requires_grad = False
        self.ssim_metric = StructuralSimilarityIndexMeasure(
            kernel_size=11, sigma=1.5, data_range=1.0, k1=0.01, k2=0.03
        ).to(DEVICE)

    def get_writer(self, dataset_type):
        if dataset_type not in self.writers:
            self.writers[dataset_type] = SummaryWriter(
                log_dir=os.path.join(self.log_dir, dataset_type))
        return self.writers[dataset_type]

    @torch.no_grad()
    def calculate_metrics(self, sr_img, hr_img):
        sr_img = sr_img.float().to(DEVICE)
        hr_img = hr_img.float().to(DEVICE)
        B, C, H, W = sr_img.shape

        if hr_img.shape[1] != C:
            if hr_img.shape[1] == 1 and C == 3:
                hr_img = hr_img.repeat(1, 3, 1, 1)
            elif hr_img.shape[1] == 3 and C == 1:
                hr_img = (0.299 * hr_img[:, 0:1] +
                          0.587 * hr_img[:, 1:2] +
                          0.114 * hr_img[:, 2:3])
            else:
                raise ValueError(f"通道不匹配: HR={hr_img.shape[1]}, SR={C}")

        sr_img = torch.clamp(sr_img, 0.0, 1.0).float()
        hr_img = torch.clamp(hr_img, 0.0, 1.0).float()

        if sr_img.shape != hr_img.shape:
            if sr_img.shape[2:] != hr_img.shape[2:]:
                hr_img = F.interpolate(hr_img, size=sr_img.shape[2:],
                                       mode="bilinear", align_corners=False)

        mse = F.mse_loss(sr_img, hr_img)
        psnr = 10 * torch.log10(1.0 / (mse + 1e-8))
        ssim_val = self.ssim_metric(sr_img, hr_img)

        if sr_img.shape[1] == 1:
            sr_l = sr_img.repeat(1, 3, 1, 1)
            hr_l = hr_img.repeat(1, 3, 1, 1)
        else:
            sr_l, hr_l = sr_img, hr_img
        sr_l = torch.clamp((sr_l - 0.5) * 2, -1.0, 1.0)
        hr_l = torch.clamp((hr_l - 0.5) * 2, -1.0, 1.0)
        lpips_val = self.lpips_model(sr_l, hr_l).mean()

        return psnr.item(), ssim_val.item(), lpips_val.item()

    def log_epoch_metrics(self, dataset_type, epoch, loss, psnr, ssim, lpips_val, lr):
        w = self.get_writer(dataset_type)
        w.add_scalar("train/epoch_loss", loss, epoch)
        w.add_scalar("train/epoch_psnr", psnr, epoch)
        w.add_scalar("train/epoch_ssim", ssim, epoch)
        w.add_scalar("train/epoch_lpips", lpips_val, epoch)
        w.add_scalar("train/lr", lr, epoch)

    def log_weights(self, dataset_type, model, epoch):
        w = self.get_writer(dataset_type)
        for name, param in model.named_parameters():
            if param.requires_grad:    # 只记 LoRA 层，避免日志爆炸
                w.add_histogram(f"weights/{name}", param, epoch)
                if param.grad is not None:
                    w.add_histogram(f"grads/{name}", param.grad, epoch)

    def close_all(self):
        for w in self.writers.values():
            w.close()


# ==============================================================================
# 4. 数据（保持原样，仅加显存友好选项）
# ==============================================================================
class CTEnhanceTransform:
    def __init__(self, rotate_range=15, translate_range=0.1, noise_std=0.01):
        self.rotate_range = rotate_range
        self.translate_range = translate_range
        self.noise_std = noise_std

    def __call__(self, img):
        angle = np.random.uniform(-self.rotate_range, self.rotate_range)
        img = img.rotate(angle, resample=Image.BICUBIC, fillcolor=0)

        w, h = img.size
        dx = int(np.random.uniform(-self.translate_range, self.translate_range) * w)
        dy = int(np.random.uniform(-self.translate_range, self.translate_range) * h)
        img = Image.fromarray(np.roll(np.array(img), (dy, dx), axis=(0, 1)))

        img_np = np.array(img, dtype=np.float32)
        img_np = (img_np - (-1024)) / (400 - (-1024))
        img_np = np.clip(img_np, 0.0, 1.0)
        img = Image.fromarray((img_np * 255).astype(np.uint8))

        if np.random.rand() < 0.5:
            img_np = np.array(img, dtype=np.float32) / 255.0
            noise = np.random.normal(0, self.noise_std, img_np.shape)
            img_np = np.clip(img_np + noise, 0, 1)
            img = Image.fromarray((img_np * 255).astype(np.uint8))
        return img


class ResizeIfSmaller:
    def __init__(self, min_size):
        self.min_size = min_size

    def __call__(self, img):
        w, h = img.size
        scale = max(self.min_size / w, self.min_size / h, 1.0)
        new_w = int(w * scale); new_h = int(h * scale)
        new_w = new_w if new_w % 2 == 0 else new_w + 1
        new_h = new_h if new_h % 2 == 0 else new_h + 1
        if new_w != w or new_h != h:
            img = img.resize((new_w, new_h), Image.BICUBIC)
        return img


class CTDataset(torch.utils.data.Dataset):
    def __init__(self, data_dir, transform=None, is_test=False, dataset_name="CT"):
        self.img_paths = [os.path.join(data_dir, f)
                          for f in os.listdir(data_dir) if f.endswith(".png")]
        self.transform = transform
        self.is_test = is_test
        self.dataset_name = dataset_name
        print(f"📁 {dataset_name}: {len(self.img_paths)} 张 (test={is_test})")

    def __getitem__(self, idx):
        img = Image.open(self.img_paths[idx]).convert("L")
        if self.transform:
            img = self.transform(img)
        C, H, W = img.shape
        new_H = (H // SCALE) * SCALE
        new_W = (W // SCALE) * SCALE
        img = img[:, :new_H, :new_W]
        lr_img = transforms.Resize(
            (new_H // SCALE, new_W // SCALE), Image.BICUBIC)(img)
        return lr_img, img

    def __len__(self):
        return len(self.img_paths)


class DIV2KDataset(torch.utils.data.Dataset):
    def __init__(self, data_dir, transform=None, is_test=False):
        self.img_paths = [os.path.join(data_dir, f)
                          for f in os.listdir(data_dir) if f.endswith(".png")]
        self.transform = transform
        self.is_test = is_test
        print(f"📁 DIV2K: {len(self.img_paths)} 张 (test={is_test})")

    def __getitem__(self, idx):
        img = Image.open(self.img_paths[idx]).convert("RGB")
        if self.transform:
            img = self.transform(img)
        C, H, W = img.shape
        new_H = (H // SCALE) * SCALE
        new_W = (W // SCALE) * SCALE
        img = img[:, :new_H, :new_W]
        lr_img = transforms.Resize(
            (new_H // SCALE, new_W // SCALE), Image.BICUBIC)(img)
        return lr_img, img

    def __len__(self):
        return len(self.img_paths)


class VOC2012Dataset(torch.utils.data.Dataset):
    def __init__(self, data_dir, transform=None, is_test=False):
        self.img_paths = [os.path.join(data_dir, f)
                          for f in os.listdir(data_dir)
                          if f.endswith((".jpg", ".png"))]
        self.transform = transform
        self.is_test = is_test
        print(f"📁 VOC2012: {len(self.img_paths)} 张 (test={is_test})")

    def __getitem__(self, idx):
        img = Image.open(self.img_paths[idx]).convert("RGB")
        if self.transform:
            img = self.transform(img)
        C, H, W = img.shape
        new_H = (H // SCALE) * SCALE
        new_W = (W // SCALE) * SCALE
        img = img[:, :new_H, :new_W]
        lr_img = transforms.Resize(
            (new_H // SCALE, new_W // SCALE), Image.BICUBIC)(img)
        return lr_img, img

    def __len__(self):
        return len(self.img_paths)


ct_transform = transforms.Compose([
    ResizeIfSmaller(128),
    CTEnhanceTransform(rotate_range=15, translate_range=0.1, noise_std=0.01),
    transforms.RandomCrop(128),
    transforms.ToTensor(),
])
ct_test_transform = transforms.Compose([
    ResizeIfSmaller(128),
    transforms.ToTensor(),
])
rgb_transform = transforms.Compose([
    ResizeIfSmaller(256),
    transforms.RandomCrop(256),
    transforms.RandomHorizontalFlip(p=0.5),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])
rgb_test_transform = transforms.Compose([
    ResizeIfSmaller(256),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def load_datasets(luna_sample_ratio=0.2):
    print("🔄 加载训练数据集...")
    sets = {
        "luna16_ct": CTDataset(os.path.join(LUNA16_DATA_DIR, "train"),
                               ct_transform, dataset_name="LUNA16"),
        "deeplesion_ct": CTDataset(os.path.join(DEEPLESION_DATA_DIR, "train"),
                                   ct_transform, dataset_name="DEEPLESION"),
        "deeplesionkey_ct": CTDataset(os.path.join(DEEPLESION_KEY_DATA_DIR, "train/HR"),
                                      ct_transform, dataset_name="DEEPLESION_KEY"),
        "covid_ct": CTDataset(os.path.join(COVID_DATA_DIR, "postive"),
                              ct_transform, dataset_name="COVID"),
        "div2k_rgb": DIV2KDataset(os.path.join(DIV2K_DATA_DIR, "train"), rgb_transform),
        "voc2012_rgb": VOC2012Dataset(os.path.join(VOC2012_DATA_DIR, "train/img"),
                                      rgb_transform),
    }

    def make_loader(ds):
        return DataLoader(ds, batch_size=BATCH_SIZE, shuffle=True,
                          num_workers=NUM_WORKERS, pin_memory=True,
                          persistent_workers=False,   # ← laptop 上关掉省内存
                          prefetch_factor=PREFETCH_FACTOR,
                          drop_last=True)

    return {k: make_loader(v) for k, v in sets.items()}


def load_test_datasets(sample_ratio=1.0):
    print("🔄 加载测试数据集...")
    sets = {
        "luna16_ct": CTDataset(os.path.join(LUNA16_DATA_DIR, "test"),
                               ct_test_transform, is_test=True, dataset_name="LUNA16"),
        "covid_ct": CTDataset(os.path.join(COVID_DATA_DIR, "test"),
                              ct_test_transform, is_test=True, dataset_name="COVID"),
        "div2k_rgb": DIV2KDataset(os.path.join(DIV2K_DATA_DIR, "test"),
                                  rgb_test_transform, is_test=True),
        "voc2012_rgb": VOC2012Dataset(os.path.join(VOC2012_DATA_DIR, "test/img"),
                                      rgb_test_transform, is_test=True),
    }

    def make_loader(ds):
        return DataLoader(ds, batch_size=1, shuffle=False,
                          num_workers=NUM_WORKERS, pin_memory=True,
                          persistent_workers=False,
                          prefetch_factor=PREFETCH_FACTOR)

    return {k: make_loader(v) for k, v in sets.items()}


# ==============================================================================
# 5. 检查点工具
# ==============================================================================
def get_dataset_checkpoint_dir(dataset_type):
    d = os.path.join(CHECKPOINT_DIR, dataset_type)
    os.makedirs(d, exist_ok=True)
    return d


def get_best_checkpoint_dir(dataset_type):
    d = os.path.join(CHECKPOINT_DIR, f"best_{dataset_type}")
    os.makedirs(d, exist_ok=True)
    return d


def get_emergency_checkpoint_dir():
    d = os.path.join(CHECKPOINT_DIR, "emergency")
    os.makedirs(d, exist_ok=True)
    return d


def load_pretrained_weights(model, pretrain_ckpt, in_channels):
    """加载预训练权重（LoRA 注入后，原卷积权重从 ckp 加载）"""
    if pretrain_ckpt is None or not os.path.exists(pretrain_ckpt):
        print(f"⚠️ 预训练权重不存在，跳过: {pretrain_ckpt}")
        return model

    print(f"📥 加载预训练权重: {pretrain_ckpt}")
    checkpoint = torch.load(pretrain_ckpt, map_location="cpu", weights_only=False)
    pretrain_dict = checkpoint.get("model_state_dict", checkpoint)
    pretrain_dict = {k.replace("module.", ""): v for k, v in pretrain_dict.items()}

    model_dict = model.state_dict()
    new_dict = {}
    matched = 0
    for k, v in pretrain_dict.items():
        if isinstance(v, torch.Tensor) and k in model_dict and model_dict[k].shape == v.shape:
            new_dict[k] = v
            matched += 1
    model_dict.update(new_dict)
    model.load_state_dict(model_dict, strict=False)
    print(f"✅ 匹配 {matched} 层 / 共 {len(model_dict)} 层")
    return model


def save_checkpoint(model, optimizer, scheduler, epoch, best_loss,
                    best_psnr, best_ssim, best_lpips, dataset_type):
    dataset_dir = get_dataset_checkpoint_dir(dataset_type)
    ckpt_path = os.path.join(dataset_dir, f"{dataset_type}_epoch_{epoch}.pth")
    torch.save({
        "epoch": epoch,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict(),
        "best_loss": best_loss, "best_psnr": best_psnr,
        "best_ssim": best_ssim, "best_lpips": best_lpips,
    }, ckpt_path)

    files = sorted(
        [f for f in os.listdir(dataset_dir)
         if f.startswith(f"{dataset_type}_epoch_") and f.endswith(".pth")],
        key=lambda f: int(f.replace(f"{dataset_type}_epoch_", "").replace(".pth", "")))
    if len(files) > 5:
        for old in files[:-5]:
            os.remove(os.path.join(dataset_dir, old))
    print(f"💾 断点已保存: {ckpt_path}")


def load_checkpoint(model, optimizer, scheduler, dataset_type):
    dataset_dir = get_dataset_checkpoint_dir(dataset_type)
    ckpt_files = [f for f in os.listdir(dataset_dir)
                  if f.startswith(f"{dataset_type}_epoch_") and f.endswith(".pth")]
    default = (model, optimizer, scheduler, 0, float("inf"), 0.0, 0.0, float("inf"))
    if not ckpt_files:
        return default

    parsed = []
    for f in ckpt_files:
        try:
            n = int(f.replace(f"{dataset_type}_epoch_", "").replace(".pth", ""))
            parsed.append((n, f))
        except ValueError:
            continue
    if not parsed:
        return default
    parsed.sort(key=lambda x: x[0])
    epoch_n, latest = parsed[-1]
    ckpt = torch.load(os.path.join(dataset_dir, latest),
                      map_location=DEVICE, weights_only=False)

    model_dict = model.state_dict()
    for k, v in ckpt["model_state_dict"].items():
        if k in model_dict and model_dict[k].shape == v.shape:
            model_dict[k] = v
    model.load_state_dict(model_dict, strict=False)

    if "optimizer_state_dict" in ckpt:
        try:
            optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        except Exception as e:
            print(f"⚠️ 优化器恢复失败: {e}")

    if "scheduler_state_dict" in ckpt:
        try:
            scheduler.load_state_dict(ckpt["scheduler_state_dict"])
        except Exception:
            pass

    return (model, optimizer, scheduler,
            ckpt.get("epoch", 0),
            ckpt.get("best_loss", float("inf")),
            ckpt.get("best_psnr", 0.0),
            ckpt.get("best_ssim", 0.0),
            ckpt.get("best_lpips", float("inf")))


# ==============================================================================
# 6. 训练
# ==============================================================================
def train_continual(model, train_loader, pretrain_ckpt, dataset_type, tb_logger):
    log_file = os.path.join(OUTPUT_DETAIL_DIR, f"{dataset_type}_train_log.txt")
    logger = Logger(log_file)
    sys.stdout = logger

    expected_channels = 1 if "ct" in dataset_type else 3
    best_dir = get_best_checkpoint_dir(dataset_type)
    emergency_dir = get_emergency_checkpoint_dir()
    emergency_path = os.path.join(emergency_dir, f"{dataset_type}_emergency.pth")

    completed_epoch = 0
    best_loss, best_psnr, best_ssim, best_lpips = float("inf"), 0.0, 0.0, float("inf")
    current_train_epoch = 0

    try:
        print(f"\n{'='*60}\n🚀 数据集: {dataset_type}\n{'='*60}")

        # 1. 重建模型（保证通道数正确）
        model = LUMWCNN(
            in_channels=expected_channels,
            scale=SCALE,
            dropout=0.1,
            with_upsample=(expected_channels == 1),   # 灰度带 upsample，RGB 不带
        ).to(DEVICE)

        # 2. 先加载预训练权重，再注入 LoRA
        model = load_pretrained_weights(model, pretrain_ckpt, expected_channels)

        print(f"\n🔧 注入 LoRA (rank={LORA_RANK}, alpha={LORA_ALPHA})...")
        model = inject_lora_to_model(model, skip_prefixes=("upsample",))
        model = model.to(DEVICE)

        total, trainable = count_trainable(model)
        print(f"📊 参数量: {total/1e6:.2f}M 总 / {trainable/1e6:.3f}M 可训 "
              f"({100*trainable/total:.2f}%)")

        # 3. 优化器：只优化 requires_grad=True 的参数
        trainable_params = [p for p in model.parameters() if p.requires_grad]
        optimizer = optim.AdamW(trainable_params, lr=LR, weight_decay=WEIGHT_DECAY)
        scheduler = CosineAnnealingWarmRestarts(
            optimizer, T_0=10, T_mult=2, eta_min=1e-7)

        # 4. 恢复断点
        (model, optimizer, scheduler,
         completed_epoch, best_loss, best_psnr, best_ssim, best_lpips
        ) = load_checkpoint(model, optimizer, scheduler, dataset_type)

        # 5. 损失函数
        lpips_model = lpips.LPIPS(net="vgg").eval().to(DEVICE)
        for p in lpips_model.parameters():
            p.requires_grad = False

        need_up = (expected_channels == 3)   # RGB 版本 loss 里上采样
        criterion = JointLoss(
            lpips_model,
            alpha=1.0, beta=0.1, gamma=0.1,
            in_channels=expected_channels,
            need_upsample=need_up,
        ).to(DEVICE)

        early_stopping = EarlyStopping()

        # 6. AMP 加速（3060 必备）
        scaler = torch.cuda.amp.GradScaler()

        print(f"\n{'='*60}\n🔥 开始训练（从 epoch {completed_epoch}）\n{'='*60}")
        model.train()

        for epoch in range(completed_epoch, EPOCHS):
            current_train_epoch = epoch + 1
            sum_loss = sum_psnr = sum_ssim = sum_lpips = 0.0
            cnt = 0
            epoch_start = time.time()

            pbar = tqdm(train_loader,
                        desc=f"[{dataset_type}] Epoch {current_train_epoch}/{EPOCHS}")
            optimizer.zero_grad()

            for batch_idx, (lr_img, hr_img) in enumerate(pbar):
                try:
                    lr_img = lr_img.to(DEVICE, non_blocking=True)
                    hr_img = hr_img.to(DEVICE, non_blocking=True)

                    with torch.cuda.amp.autocast(dtype=torch.float16):
                        sr_img = model(lr_img)
                        sr_img, hr_img_a = model._align_tensor_size(sr_img, hr_img)
                        loss = criterion(sr_img, hr_img_a) / GRAD_ACCUM_STEPS

                    scaler.scale(loss).backward()

                    if (batch_idx + 1) % GRAD_ACCUM_STEPS == 0:
                        scaler.unscale_(optimizer)
                        torch.nn.utils.clip_grad_norm_(trainable_params, max_norm=1.0)
                        scaler.step(optimizer)
                        scaler.update()
                        optimizer.zero_grad()
                        scheduler.step(epoch + batch_idx / len(train_loader))

                    with torch.no_grad():
                        psnr, ssim_val, lpips_val = tb_logger.calculate_metrics(
                            sr_img.float(), hr_img_a.float())
                    sum_loss += loss.item() * GRAD_ACCUM_STEPS
                    sum_psnr += psnr
                    sum_ssim += ssim_val
                    sum_lpips += lpips_val
                    cnt += 1

                    pbar.set_postfix({
                        "Loss": f"{loss.item()*GRAD_ACCUM_STEPS:.4f}",
                        "PSNR": f"{psnr:.2f}",
                        "GPU": f"{torch.cuda.memory_allocated()/1e9:.2f}G",
                    })
                except RuntimeError as e:
                    if "out of memory" in str(e).lower():
                        print(f"\n⚠️ OOM at batch {batch_idx}，跳过")
                        optimizer.zero_grad()
                        torch.cuda.empty_cache()
                        continue
                    else:
                        print(f"\n⚠️ 批次 {batch_idx} 错误: {e}，跳过")
                        continue

            if cnt == 0:
                print(f"⚠️ Epoch {current_train_epoch} 无有效批次")
                continue

            avg_loss = sum_loss / cnt
            avg_psnr = sum_psnr / cnt
            avg_ssim = sum_ssim / cnt
            avg_lpips = sum_lpips / cnt
            current_lr = optimizer.param_groups[0]["lr"]
            epoch_time = time.time() - epoch_start

            print(f"\n✅ Epoch {current_train_epoch}/{EPOCHS} | {epoch_time:.1f}s")
            print(f"   Loss={avg_loss:.6f} PSNR={avg_psnr:.2f} "
                  f"SSIM={avg_ssim:.4f} LPIPS={avg_lpips:.4f} LR={current_lr:.8f}")
            print(f"   GPU={torch.cuda.memory_allocated()/1e9:.2f}G "
                  f"峰值={torch.cuda.max_memory_allocated()/1e9:.2f}G")

            save_checkpoint(model, optimizer, scheduler, current_train_epoch,
                            best_loss, best_psnr, best_ssim, best_lpips, dataset_type)

            # 分指标保存最佳
            for metric, val, cmp in [
                ("loss", avg_loss, "<"), ("psnr", avg_psnr, ">"),
                ("ssim", avg_ssim, ">"), ("lpips", avg_lpips, "<")
            ]:
                best_val = {"loss": best_loss, "psnr": best_psnr,
                            "ssim": best_ssim, "lpips": best_lpips}[metric]
                improved = (val < best_val) if cmp == "<" else (val > best_val)
                if improved:
                    if metric == "loss": best_loss = val
                    elif metric == "psnr": best_psnr = val
                    elif metric == "ssim": best_ssim = val
                    else: best_lpips = val
                    torch.save({
                        "epoch": current_train_epoch,
                        "model_state_dict": model.state_dict(),
                        f"best_{metric}": val,
                    }, os.path.join(best_dir,
                                    f"best_{dataset_type}_{metric}_epoch_{current_train_epoch}.pth"))
                    print(f"   🏆 新最佳 {metric}: {val:.6f}")

            tb_logger.log_epoch_metrics(dataset_type, current_train_epoch,
                                        avg_loss, avg_psnr, avg_ssim, avg_lpips, current_lr)
            if current_train_epoch % 10 == 0:
                tb_logger.log_weights(dataset_type, model, current_train_epoch)

            if early_stopping(avg_psnr, avg_ssim, avg_lpips):
                print(f"⛔ 早停触发，停止 {dataset_type}")
                break

            if current_train_epoch % 10 == 0:
                torch.save({
                    "epoch": current_train_epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "scheduler_state_dict": scheduler.state_dict(),
                }, emergency_path)

        print(f"\n🎉 {dataset_type} 完成！最佳: PSNR={best_psnr:.2f} "
              f"SSIM={best_ssim:.4f} LPIPS={best_lpips:.4f}")

    except (KeyboardInterrupt, Exception) as e:
        is_kb = isinstance(e, KeyboardInterrupt)
        print(f"\n{'='*60}")
        if is_kb:
            print("⚠️ 键盘中断，保存紧急模型...")
        else:
            print(f"❌ 训练出错: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
        try:
            sd = {"epoch": current_train_epoch, "error": str(e) if not is_kb else "KB"}
            if "model" in locals() and model is not None:
                sd["model_state_dict"] = model.state_dict()
            if "optimizer" in locals() and optimizer is not None:
                sd["optimizer_state_dict"] = optimizer.state_dict()
            torch.save(sd, emergency_path)
            print(f"💾 紧急保存: {emergency_path}")
        except Exception as se:
            print(f"❌ 紧急保存失败: {se}")
    finally:
        logger.close()
        sys.stdout = logger.terminal
        torch.cuda.empty_cache()
        gc.collect()


# ==============================================================================
# 7. 测试
# ==============================================================================
def save_image(tensor, save_path):
    tensor = tensor.squeeze(0).cpu()
    tensor = torch.clamp(tensor, 0.0, 1.0)
    img = (transforms.ToPILImage()(tensor).convert("L")
           if tensor.shape[0] == 1 else transforms.ToPILImage()(tensor))
    img.save(save_path)


@torch.no_grad()
def test_model(model_path, dataset_type, tb_logger, sample_ratio=1.0):
    log_file = os.path.join(OUTPUT_DETAIL_DIR, f"{dataset_type}_test_log.txt")
    test_logger = Logger(log_file)
    sys.stdout = test_logger

    test_loaders = load_test_datasets()
    test_loader = test_loaders[dataset_type]

    in_channels = 1 if "ct" in dataset_type else 3
    model = LUMWCNN(
        in_channels=in_channels,
        scale=SCALE,
        with_upsample=(in_channels == 1),
    ).to(DEVICE)

    ckpt = torch.load(model_path, map_location=DEVICE, weights_only=False)
    sd = ckpt.get("model_state_dict", ckpt)
    sd = {k.replace("module.", ""): v for k, v in sd.items()}
    model.load_state_dict(sd, strict=False)
    model.eval()

    torch.cuda.empty_cache()
    sum_psnr = sum_ssim = sum_lpips = 0.0
    cnt = 0
    test_dir = os.path.join(TEST_OUTPUT_DIR, dataset_type)
    os.makedirs(test_dir, exist_ok=True)

    pbar = tqdm(test_loader, desc=f"Test {dataset_type}")
    for idx, (lr_img, hr_img) in enumerate(pbar):
        lr_img = lr_img.to(DEVICE)
        hr_img = hr_img.to(DEVICE)
        with torch.cuda.amp.autocast(dtype=torch.float16):
            sr_img = model(lr_img)
        sr_img, hr_img = model._align_tensor_size(sr_img, hr_img)

        psnr, ssim_val, lpips_val = tb_logger.calculate_metrics(
            sr_img.float(), hr_img.float())
        sum_psnr += psnr; sum_ssim += ssim_val; sum_lpips += lpips_val
        cnt += 1

        pbar.set_postfix({"PSNR": f"{psnr:.2f}", "SSIM": f"{ssim_val:.4f}"})

        if idx == 0 or idx % 20 == 0:
            save_image(lr_img, os.path.join(test_dir, f"{idx:04d}_lr.png"))
            save_image(sr_img, os.path.join(test_dir, f"{idx:04d}_sr.png"))
            save_image(hr_img, os.path.join(test_dir, f"{idx:04d}_hr.png"))

        if idx % 50 == 0:
            torch.cuda.empty_cache()

    if cnt > 0:
        print(f"\n===== {dataset_type} 测试 =====")
        print(f"样本 {cnt} | PSNR={sum_psnr/cnt:.2f} | "
              f"SSIM={sum_ssim/cnt:.4f} | LPIPS={sum_lpips/cnt:.4f}")

    test_logger.close()
    sys.stdout = test_logger.terminal
    torch.cuda.empty_cache()


def find_best_ckpt(prefix):
    if not os.path.exists(CHECKPOINT_DIR):
        return None
    files = []
    for root, _, names in os.walk(CHECKPOINT_DIR):
        for n in names:
            if n.startswith(prefix) and n.endswith(".pth"):
                files.append(os.path.join(root, n))
    if not files:
        return None
    files.sort(key=os.path.getmtime)
    return files[-1]


# ==============================================================================
# 8. 主入口
# ==============================================================================
if __name__ == "__main__":
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    torch.backends.cudnn.benchmark = False    # ← laptop 上关掉，避免显存波动
    torch.cuda.empty_cache()

    tb_logger = TBLogger()
    train_loaders = load_datasets(luna_sample_ratio=0.2)

    # 初始模型（会再进 train_continual 里被重建 + 加载 ckp + LoRA 注入）
    model = LUMWCNN(scale=SCALE).to(DEVICE)

    print("\n" + "="*60)
    print("🔧 阶段 1: 从 DeepLesion CKPT 微调 → deeplesionkey_ct")
    print("="*60)
    train_continual(model, train_loaders["deeplesionkey_ct"],
                    DEEPLESION_CKPT, "deeplesionkey_ct", tb_logger)

    print("\n" + "="*60)
    print("🔧 阶段 2: 从 DIV2K CKPT 微调 → voc2012_rgb")
    print("="*60)
    train_continual(model, train_loaders["voc2012_rgb"],
                    DIV2K_CKPT, "voc2012_rgb", tb_logger)

    # 测试
    for prefix, ds_type in [
        ("best_luna16_ct_loss", "luna16_ct"),
        ("best_covid_ct_loss", "covid_ct"),
        ("best_div2k_rgb_loss", "div2k_rgb"),
        ("best_voc2012_rgb_loss", "voc2012_rgb"),
    ]:
        ckpt = find_best_ckpt(prefix)
        if ckpt:
            test_model(ckpt, ds_type, tb_logger)

    tb_logger.close_all()
    print("\n🎉 所有任务完成！")
