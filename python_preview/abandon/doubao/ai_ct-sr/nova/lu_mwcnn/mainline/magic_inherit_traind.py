import os
import sys
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Subset
from torchvision import transforms
import numpy as np
from tqdm import tqdm
from PIL import Image
import os.path as path
import torch.nn.functional as F
from torch.utils.tensorboard.writer import SummaryWriter
import lpips
import warnings
warnings.filterwarnings('ignore')

# ========== 全局配置 ==========
DEEPLESION_CKPT = "./output_deeplesion/deeplesion_resume_ckpt/best_model.pth"
DIVK_CKPT = "./output_divk/divk_resume_ckpt/best_model.pth"

LUNA_DATA_DIR = "/home/dake/Documents/Projects/datasets/LUNA/sr_slice_dataset/"
VOC_DATA_DIR  = "/home/dake/Documents/Projects/datasets/VOC/sr_split/"
COVID_DATA_DIR = "/home/dake/Documents/Projects/datasets/COVID-CT/COVID-CT-Images/"

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
SCALE = 4
BATCH_SIZE = 8
LR = 1e-4                         # ← 从 2e-6 改为 1e-4
EPOCHS = 300
FREEZE_BACKBONE_EPOCHS = 0        # ← 建议不再冻结，直接全量微调
EARLY_STOPPING_PATIENCE = 20      # ← 从 8 改为 20
EARLY_STOPPING_MIN_DELTA = 0.01   # 基于 PSNR，单位 dB
CHECKPOINT_DIR = "./continual_ckpt"
OUTPUT_DETAIL_DIR = "./output_detail"

os.makedirs(CHECKPOINT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DETAIL_DIR, exist_ok=True)


# ========== 日志重定向 ==========
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


# ========== 小波变换 ==========
class DWT_Haar(nn.Module):
    def forward(self, x):
        B, C, H, W = x.shape
        assert H % 2 == 0 and W % 2 == 0, f"输入尺寸{H}x{W}必须是2的倍数"
        x = x.reshape(B, C, H // 2, 2, W // 2, 2)
        x = x.permute(0, 1, 3, 5, 2, 4).contiguous()
        return x.view(B, C * 4, H // 2, W // 2)

class IWT_Haar(nn.Module):
    def forward(self, x):
        B, C, H, W = x.shape
        assert C % 4 == 0, f"输入通道数{C}必须是4的倍数"
        x = x.view(B, C // 4, 2, 2, H, W)
        x = x.permute(0, 1, 4, 2, 5, 3).contiguous()
        return x.view(B, C // 4, H * 2, W * 2)


# ========== 卷积模块 ==========
class Convd(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size, act=True):
        super().__init__()
        layers = [nn.Conv2d(in_ch, out_ch, kernel_size, padding=kernel_size // 2)]
        if act:
            layers.append(nn.ReLU(inplace=True))
        self.model = nn.Sequential(*layers)
    def forward(self, x):
        return self.model(x)


# ========== LUMWCNN（通道数来自 ckp） ==========
class LUMWCNN(nn.Module):
    def __init__(self, in_channels=1, device=None, scale=4):
        super().__init__()
        self.device = device or DEVICE
        self.in_channels = in_channels
        self.scale = scale
        assert in_channels in [1, 3]

        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

        self.l_conv1 = nn.Sequential(Convd(in_channels, 64, 3), Convd(64, 64, 3))
        self.l_conv2 = nn.Sequential(Convd(256, 128, 3),       Convd(128, 128, 3))
        self.l_conv3 = nn.Sequential(Convd(512, 256, 3),       Convd(256, 256, 3))

        self.r_conv3 = nn.Sequential(Convd(256, 256, 3),       Convd(256, 512, 3))
        self.r_conv2 = nn.Sequential(Convd(128, 128, 3),       Convd(128, 256, 3))
        self.r_conv1 = nn.Sequential(Convd(64, 64, 3),         Convd(64, in_channels, 3, act=False))

        if scale == 4:
            self.upsample = nn.Sequential(
                nn.Conv2d(in_channels, in_channels * 4, 3, padding=1),
                nn.PixelShuffle(2),
                nn.Conv2d(in_channels, in_channels * 4, 3, padding=1),
                nn.PixelShuffle(2),
            )
        elif scale == 2:
            self.upsample = nn.Sequential(
                nn.Conv2d(in_channels, in_channels * 4, 3, padding=1),
                nn.PixelShuffle(2),
            )
        else:
            raise ValueError("scale 仅支持 2 或 4")

        self.pads = []

    def _align(self, a, b):
        mh = min(a.shape[2], b.shape[2])
        mw = min(a.shape[3], b.shape[3])
        return a[:, :, :mh, :mw], b[:, :, :mh, :mw]

    def wavelet_pad(self, x):
        ph = 1 if x.shape[-2] % 2 != 0 else 0
        pw = 1 if x.shape[-1] % 2 != 0 else 0
        self.pads.append([pw, ph])
        return F.pad(x, (0, pw, 0, ph), 'constant', 0)

    def wavelet_shave(self, x):
        if not self.pads:
            return x
        pw, ph = self.pads.pop()
        if pw: x = x[:, :, :, :-1]
        if ph: x = x[:, :, :-1, :]
        return x

    def forward(self, x):
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
        x_r, x_l2 = self._align(x_r, x_l2)
        x_r = x_r + x_l2

        x_r = self.wavelet_shave(self.IWT(self.r_conv2(x_r)))
        x_r, x_l1 = self._align(x_r, x_l1)
        x_r = x_r + x_l1

        x_r = self.r_conv1(x_r)
        x_r, x = self._align(x_r, x)
        x_r = x_r + x

        y = self.upsample(x_r)
        return torch.clamp(y, 0., 1.)   # ← 关键：clamp 到 [0,1]


# ========== 早停（基于验证集 PSNR，mode='max'） ==========
class EarlyStopping:
    def __init__(self, patience=20, min_delta=0.01, mode='max', verbose=True):
        self.patience = patience
        self.min_delta = min_delta
        self.mode = mode
        self.verbose = verbose
        self.counter = 0
        self.best_score = None
        self.early_stop = False
    def __call__(self, score):
        if self.best_score is None:
            self.best_score = score
        else:
            if self.mode == 'max':
                improve = score > (self.best_score + self.min_delta)
            else:
                improve = score < (self.best_score - self.min_delta)
            if improve:
                self.best_score = score
                self.counter = 0
            else:
                self.counter += 1
                if self.verbose:
                    print(f"EarlyStopping: {self.counter}/{self.patience} | best={self.best_score:.4f}")
                if self.counter >= self.patience:
                    self.early_stop = True
        return self.early_stop


# ========== TB 日志器 ==========
class TBLogger:
    def __init__(self, log_dir="./tb_logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.writers = {}
        self.lpips_model = lpips.LPIPS(net='vgg').eval().to(DEVICE)
        for p in self.lpips_model.parameters():
            p.requires_grad = False

    def get_writer(self, dataset_type):
        if dataset_type not in self.writers:
            writer_dir = os.path.join(self.log_dir, dataset_type)
            self.writers[dataset_type] = SummaryWriter(log_dir=writer_dir)
            print(f"初始化TensorBoard: {writer_dir}")
        return self.writers[dataset_type]

    def calculate_metrics(self, sr_img, hr_img):
        sr_img = sr_img.float().to(DEVICE)
        hr_img = hr_img.float().to(DEVICE)

        # PSNR
        mse = F.mse_loss(sr_img, hr_img)
        psnr = 10 * torch.log10(1.0 / (mse + 1e-8))

        # SSIM
        def ssim(x, y):
            C1, C2 = 0.01**2, 0.03**2
            win_size, sigma = 11, 1.5
            gauss = torch.tensor([np.exp(-(i - win_size//2)**2 / (2*sigma**2)) for i in range(win_size)])
            gauss = (gauss / gauss.sum()).to(x.device)
            window = gauss.unsqueeze(1) @ gauss.unsqueeze(0)
            window = window.unsqueeze(0).unsqueeze(0).repeat(x.shape[1], 1, 1, 1)
            pad = win_size // 2
            mu_x = F.conv2d(x, window, padding=pad, groups=x.shape[1])
            mu_y = F.conv2d(y, window, padding=pad, groups=y.shape[1])
            mu_x_sq, mu_y_sq, mu_xy = mu_x**2, mu_y**2, mu_x*mu_y
            sig_x = F.conv2d(x*x, window, padding=pad, groups=x.shape[1]) - mu_x_sq
            sig_y = F.conv2d(y*y, window, padding=pad, groups=y.shape[1]) - mu_y_sq
            sig_xy = F.conv2d(x*y, window, padding=pad, groups=x.shape[1]) - mu_xy
            ssim_map = ((2*mu_xy + C1) * (2*sig_xy + C2)) / ((mu_x_sq + mu_y_sq + C1) * (sig_x + sig_y + C2))
            return ssim_map.mean()

        ssim_val = ssim(sr_img, hr_img)

        # LPIPS（输入必须 [-1,1]）
        sr_n = sr_img * 2 - 1
        hr_n = hr_img * 2 - 1
        if sr_n.shape[1] == 1:
            sr_n = sr_n.repeat(1, 3, 1, 1)
            hr_n = hr_n.repeat(1, 3, 1, 1)
        lpips_val = self.lpips_model(sr_n, hr_n).mean()

        return psnr.item(), ssim_val.item(), lpips_val.item()

    def log_scalars(self, dataset_type, epoch, scalars: dict):
        writer = self.get_writer(dataset_type)
        for k, v in scalars.items():
            writer.add_scalar(k, v, epoch)

    def close_all(self):
        for w in self.writers.values():
            w.close()


# ========== 数据集 ==========
class ResizeIfSmaller:
    def __init__(self, min_size=128):
        self.min_size = min_size
    def __call__(self, img):
        w, h = img.size
        scale = max(self.min_size / w, self.min_size / h, 1.0)
        nw, nh = int(w * scale), int(h * scale)
        nw = nw if nw % 2 == 0 else nw + 1
        nh = nh if nh % 2 == 0 else nh + 1
        if (nw, nh) != (w, h):
            img = img.resize((nw, nh), Image.BICUBIC)
        return img


class _BaseSRDataset(torch.utils.data.Dataset):
    """统一处理：读图 -> transform -> 按 SCALE 对齐裁剪 -> 生成 LR"""
    def __init__(self, img_paths, transform, mode='L'):
        self.img_paths = img_paths
        self.transform = transform
        self.mode = mode
        print(f"  数据集加载: 共 {len(img_paths)} 张")
    def __len__(self):
        return len(self.img_paths)
    def __getitem__(self, idx):
        try:
            img = Image.open(self.img_paths[idx]).convert(self.mode)
            if self.transform:
                img = self.transform(img)          # -> tensor (C,H,W)
            _, hr_h, hr_w = img.shape
            lr_h = (hr_h // SCALE) * SCALE
            lr_w = (hr_w // SCALE) * SCALE
            img = img[:, :lr_h, :lr_w]
            lr_img = transforms.Resize((lr_h // SCALE, lr_w // SCALE),
                                       interpolation=transforms.InterpolationMode.BICUBIC)(img)
            return lr_img, img
        except Exception as e:
            print(f"加载失败 {self.img_paths[idx]}: {e}，使用第 0 张替代")
            return self.__getitem__(0)


def make_luna_dataset(root, transform):
    img_dir = os.path.join(root)
    paths = [os.path.join(img_dir, f) for f in os.listdir(img_dir) if f.endswith(".png")]
    return _BaseSRDataset(paths, transform, mode='L')

def make_covid_dataset(root, transform):
    img_dir = os.path.join(root)
    paths = [os.path.join(img_dir, f) for f in os.listdir(img_dir) if f.endswith(".png")]
    return _BaseSRDataset(paths, transform, mode='L')

def make_voc_dataset(root, transform):
    img_dir = os.path.join(root, "img") if os.path.isdir(os.path.join(root, "img")) else root
    paths = [os.path.join(img_dir, f) for f in os.listdir(img_dir) if f.endswith((".jpg", ".png"))]
    return _BaseSRDataset(paths, transform, mode='RGB')


# ========== Transform ==========
ct_transform_train = transforms.Compose([
    ResizeIfSmaller(128),
    transforms.RandomCrop(128),
    transforms.RandomHorizontalFlip(p=0.5),
    transforms.ToTensor(),
])
ct_transform_eval = transforms.Compose([
    transforms.Resize((128, 128)),
    transforms.ToTensor(),
])
rgb_transform_train = transforms.Compose([
    ResizeIfSmaller(128),
    transforms.RandomCrop(128),
    transforms.RandomHorizontalFlip(p=0.5),
    transforms.ToTensor(),
])
rgb_transform_eval = transforms.Compose([
    transforms.Resize((128, 128)),
    transforms.ToTensor(),
])


# ========== 构建 DataLoader ==========
print("开始加载数据集...")

# LUNA：三目录
luna_train_loader = DataLoader(
    make_luna_dataset(os.path.join(LUNA_DATA_DIR, "train"), ct_transform_train),
    batch_size=BATCH_SIZE, shuffle=True, num_workers=4, pin_memory=True, drop_last=True)
luna_val_loader = DataLoader(
    make_luna_dataset(os.path.join(LUNA_DATA_DIR, "val"), ct_transform_eval),
    batch_size=1, shuffle=False, num_workers=4, pin_memory=True)
luna_test_loader = DataLoader(
    make_luna_dataset(os.path.join(LUNA_DATA_DIR, "test"), ct_transform_eval),
    batch_size=1, shuffle=False, num_workers=4, pin_memory=True)

# COVID：从 postive 里 split 出 val
covid_full_train = make_covid_dataset(os.path.join(COVID_DATA_DIR, "postive"), ct_transform_train)
covid_full_eval  = make_covid_dataset(os.path.join(COVID_DATA_DIR, "postive"), ct_transform_eval)
n_covid = len(covid_full_train)
n_covid_val = max(1, int(0.1 * n_covid))
n_covid_train = n_covid - n_covid_val
g = torch.Generator().manual_seed(42)
train_idx, val_idx = torch.randperm(n_covid, generator=g)[:n_covid_train], \
                     torch.randperm(n_covid, generator=g)[n_covid_train:]
covid_train_loader = DataLoader(Subset(covid_full_train, train_idx.tolist()),
                                batch_size=BATCH_SIZE, shuffle=True, num_workers=4,
                                pin_memory=True, drop_last=True)
covid_val_loader = DataLoader(Subset(covid_full_eval, val_idx.tolist()),
                              batch_size=1, shuffle=False, num_workers=4, pin_memory=True)

# VOC：三目录
voc_train_loader = DataLoader(
    make_voc_dataset(os.path.join(VOC_DATA_DIR, "train"), rgb_transform_train),
    batch_size=BATCH_SIZE, shuffle=True, num_workers=4, pin_memory=True, drop_last=True)
voc_val_loader = DataLoader(
    make_voc_dataset(os.path.join(VOC_DATA_DIR, "val"), rgb_transform_eval),
    batch_size=1, shuffle=False, num_workers=4, pin_memory=True)
voc_test_loader = DataLoader(
    make_voc_dataset(os.path.join(VOC_DATA_DIR, "test"), rgb_transform_eval),
    batch_size=1, shuffle=False, num_workers=4, pin_memory=True)

print("所有数据集加载完成")


# ========== 预训练权重加载 ==========
def load_pretrained_weights(model, ckpt_path, in_channels):
    if not os.path.exists(ckpt_path):
        raise FileNotFoundError(f"预训练权重不存在：{ckpt_path}")
    ckpt = torch.load(ckpt_path, map_location=DEVICE, weights_only=False)
    sd = ckpt.get("model_state_dict", ckpt)
    sd = {k.replace('module.', ''): v for k, v in sd.items()}
    sd = {k.replace('.layers.', '.model.'): v for k, v in sd.items()}
    sd = {k: v for k, v in sd.items()
          if isinstance(v, torch.Tensor) and not any(x in k for x in ['running_mean', 'running_var', 'num_batches_tracked'])}

    # 通道适配
    key = 'l_conv1.0.model.0.weight'
    if key in sd:
        pre_ch = sd[key].shape[1]
        if pre_ch != in_channels:
            print(f"通道适配：{pre_ch}→{in_channels}")
            if pre_ch == 3 and in_channels == 1:
                sd[key] = sd[key].mean(dim=1, keepdim=True)
            elif pre_ch == 1 and in_channels == 3:
                sd[key] = sd[key].repeat(1, 3, 1, 1)

    model_dict = model.state_dict()
    matched = {k: v for k, v in sd.items() if k in model_dict and model_dict[k].shape == v.shape}
    unmatched = [k for k in sd if k not in matched]
    model_dict.update(matched)
    model.load_state_dict(model_dict, strict=False)
    print(f"加载预训练：匹配 {len(matched)} 层 | 未匹配 {len(unmatched)} 层")
    return model


# ========== 断点加载 ==========
def load_checkpoint(model, optimizer, dataset_type):
    files = [f for f in os.listdir(CHECKPOINT_DIR)
             if f.startswith(f"{dataset_type}_epoch_") and f.endswith(".pth")]
    parsed = []
    for f in files:
        try:
            ep = int(f.replace(f"{dataset_type}_epoch_", "").replace(".pth", ""))
            parsed.append((ep, f))
        except:
            continue
    if not parsed:
        print(f"无断点，从头训练 {dataset_type}")
        return model, optimizer, 0, float('inf'), 0., 0., float('inf')
    parsed.sort()
    max_ep, latest = parsed[-1]
    ckpt = torch.load(os.path.join(CHECKPOINT_DIR, latest), map_location=DEVICE)
    model.load_state_dict(ckpt['model_state_dict'])
    try:
        optimizer.load_state_dict(ckpt['optimizer_state_dict'])
    except Exception as e:
        print(f"优化器状态加载失败：{e}，重建")
        optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=LR)
    start_epoch = ckpt['epoch'] + 1
    best_loss = ckpt.get('best_loss', float('inf'))
    best_psnr = ckpt.get('best_psnr', 0.)
    best_ssim = ckpt.get('best_ssim', 0.)
    best_lpips = ckpt.get('best_lpips', float('inf'))
    print(f"从 Epoch {start_epoch} 恢复 | best_psnr={best_psnr:.2f}")
    return model, optimizer, start_epoch, best_loss, best_psnr, best_ssim, best_lpips


# ========== 验证 / 测试 ==========
@torch.no_grad()
def evaluate(model, loader, tb_logger, desc='Val'):
    model.eval()
    psnr_sum, ssim_sum, lpips_sum, n = 0., 0., 0., 0
    for lr_img, hr_img in tqdm(loader, desc=desc, ncols=80):
        lr_img, hr_img = lr_img.to(DEVICE), hr_img.to(DEVICE)
        sr_img = model(lr_img)
        sr_img, hr_img = model._align(sr_img, hr_img)
        psnr, ssim_val, lpips_val = tb_logger.calculate_metrics(sr_img, hr_img)
        psnr_sum += psnr; ssim_sum += ssim_val; lpips_sum += lpips_val
        n += 1
    if n == 0:
        return 0., 0., 0.
    return psnr_sum / n, ssim_sum / n, lpips_sum / n


# ========== 训练主函数 ==========
def train_continual(model, train_loader, val_loader, test_loader,
                    pretrain_ckpt, dataset_type, tb_logger):
    log_file = os.path.join(OUTPUT_DETAIL_DIR, f"{dataset_type}_train_log.txt")
    logger = Logger(log_file)
    sys.stdout = logger
    print(f"开始记录 {dataset_type} 训练日志：{log_file}")

    in_channels = 1 if "ct" in dataset_type else 3
    try:
        print(f"\n===== 开始训练 {dataset_type} =====")
        print(f"输入通道: {in_channels} | 缩放: {SCALE} | batch: {BATCH_SIZE} | LR: {LR}")
        model = load_pretrained_weights(model, pretrain_ckpt, in_channels)
        model = model.to(DEVICE)

        optimizer = optim.Adam(model.parameters(), lr=LR, betas=(0.9, 0.999))
        model, optimizer, start_epoch, best_loss, best_psnr, best_ssim, best_lpips = \
            load_checkpoint(model, optimizer, dataset_type)

        scheduler = optim.lr_scheduler.OneCycleLR(
            optimizer,
            max_lr=LR,
            total_steps=EPOCHS * len(train_loader),
            pct_start=0.1,
            anneal_strategy='cos',
        )
        early_stopping = EarlyStopping(patience=EARLY_STOPPING_PATIENCE,
                                       min_delta=EARLY_STOPPING_MIN_DELTA,
                                       mode='max')
        criterion = nn.L1Loss()

        for epoch in range(start_epoch, EPOCHS):
            # ---------- 训练 ----------
            model.train()
            train_loss = 0.
            pbar = tqdm(train_loader, desc=f"[{dataset_type}] Epoch {epoch+1}/{EPOCHS}")
            for lr_img, hr_img in pbar:
                lr_img, hr_img = lr_img.to(DEVICE), hr_img.to(DEVICE)
                sr_img = model(lr_img)
                sr_img, hr_img = model._align(sr_img, hr_img)
                loss = criterion(sr_img, hr_img)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                scheduler.step()
                train_loss += loss.item()
                pbar.set_postfix({'loss': f'{loss.item():.4f}'})
            train_loss /= len(train_loader)

            # ---------- 验证 ----------
            val_psnr, val_ssim, val_lpips = evaluate(model, val_loader, tb_logger, desc='Val')

            print(f"\n[{dataset_type}] Epoch {epoch+1}/{EPOCHS}")
            print(f"  train_loss={train_loss:.6f}")
            print(f"  val_psnr={val_psnr:.2f} | val_ssim={val_ssim:.4f} | val_lpips={val_lpips:.4f}")

            # TB
            tb_logger.log_scalars(dataset_type, epoch + 1, {
                'train/loss': train_loss,
                'val/psnr': val_psnr,
                'val/ssim': val_ssim,
                'val/lpips': val_lpips,
                'train/lr': optimizer.param_groups[0]['lr'],
            })

            # 保存本轮
            ckpt_path = os.path.join(CHECKPOINT_DIR, f"{dataset_type}_epoch_{epoch+1}.pth")
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'train_loss': train_loss,
                'val_psnr': val_psnr,
                'best_loss': best_loss,
                'best_psnr': best_psnr,
                'best_ssim': best_ssim,
                'best_lpips': best_lpips,
            }, ckpt_path)

            # ---------- 保存最佳模型（基于 val） ----------
            if val_psnr > best_psnr:
                best_psnr = val_psnr
                torch.save({
                    'epoch': epoch + 1,
                    'model_state_dict': model.state_dict(),
                    'best_psnr': best_psnr,
                }, os.path.join(CHECKPOINT_DIR, f"best_{dataset_type}_psnr_epoch_{epoch+1}.pth"))
                print(f"  新最佳 PSNR: {best_psnr:.2f} dB")

            if val_ssim > best_ssim:
                best_ssim = val_ssim
                torch.save({
                    'epoch': epoch + 1,
                    'model_state_dict': model.state_dict(),
                    'best_ssim': best_ssim,
                }, os.path.join(CHECKPOINT_DIR, f"best_{dataset_type}_ssim_epoch_{epoch+1}.pth"))

            if val_lpips < best_lpips:
                best_lpips = val_lpips
                torch.save({
                    'epoch': epoch + 1,
                    'model_state_dict': model.state_dict(),
                    'best_lpips': best_lpips,
                }, os.path.join(CHECKPOINT_DIR, f"best_{dataset_type}_lpips_epoch_{epoch+1}.pth"))

            # ---------- 早停（基于 val PSNR） ----------
            if early_stopping(val_psnr):
                print(f"触发早停 @ Epoch {epoch+1} | best_psnr={best_psnr:.2f}")
                break

        # ---------- 最终测试 ----------
        print(f"\n===== {dataset_type} 训练结束，在 test 集上评估 =====")
        best_ckpts = [f for f in os.listdir(CHECKPOINT_DIR)
                      if f.startswith(f"best_{dataset_type}_psnr_epoch_")]
        if best_ckpts:
            best_ckpts.sort(key=lambda f: int(f.replace(f"best_{dataset_type}_psnr_epoch_", "").replace(".pth", "")))
            best_path = os.path.join(CHECKPOINT_DIR, best_ckpts[-1])
            model.load_state_dict(torch.load(best_path, map_location=DEVICE)['model_state_dict'])
            print(f"加载最佳模型：{best_path}")
        test_psnr, test_ssim, test_lpips = evaluate(model, test_loader, tb_logger, desc='Test')
        print(f"\n🏁 {dataset_type} 最终 Test - PSNR: {test_psnr:.2f} | SSIM: {test_ssim:.4f} | LPIPS: {test_lpips:.4f}")

    except KeyboardInterrupt:
        print(f"\n中断，保存紧急模型...")
        torch.save({'model_state_dict': model.state_dict()},
                   os.path.join(CHECKPOINT_DIR, f"{dataset_type}_emergency.pth"))
        raise
    finally:
        sys.stdout = logger.terminal
        logger.close()
        print(f"{dataset_type} 日志已保存：{log_file}")


# ========== 主函数 ==========
if __name__ == "__main__":
    print(f"设备：{DEVICE}")
    tb_logger = TBLogger(log_dir="./tb_logs")
    try:
        print("\n===== LUNA CT =====")
        train_continual(LUMWCNN(in_channels=1, device=DEVICE, scale=SCALE),
                        luna_train_loader, luna_val_loader, luna_test_loader,
                        DEEPLESION_CKPT, "luna_ct", tb_logger)

        print("\n===== COVID CT =====")
        train_continual(LUMWCNN(in_channels=1, device=DEVICE, scale=SCALE),
                        covid_train_loader, covid_val_loader, None,
                        DEEPLESION_CKPT, "covid_ct", tb_logger)

        print("\n===== VOC RGB =====")
        train_continual(LUMWCNN(in_channels=3, device=DEVICE, scale=SCALE),
                        voc_train_loader, voc_val_loader, voc_test_loader,
                        DIVK_CKPT, "voc_rgb", tb_logger)
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        tb_logger.close_all()
    print("\n全部训练完成")
