import os
import cv
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from torch.utils.tensorboard import SummaryWriter
from torchvision import transforms, utils
from PIL import Image
from tqdm import tqdm
import argparse
from lpips import LPIPS
 直接使用PyTorch .+的新AMP API
from torch.amp import autocast, GradScaler

 ===================== 通用工具函数（添加SSIM计算） =====================


def get_numeric_value(val):
    """递归提取嵌套元组/列表中的数值"""
    if isinstance(val, (tuple, list)):
        return get_numeric_value(val[]) if val else .
    elif isinstance(val, np.ndarray):
        return float(val.mean()) if val.size >  else .
    elif isinstance(val, (int, float, np.number)):
        return float(val)
    else:
        return .


def calculate_ssim(img, img):
    """通用SSIM计算函数（不依赖cv.quality，避免版本兼容问题）"""
    C = (.  )  
    C = (.  )  

     转为灰度图（如果是彩色图）
    if len(img.shape) ==  and img.shape[] == :
        img = cv.cvtColor(img, cv.COLOR_BGRGRAY)
        img = cv.cvtColor(img, cv.COLOR_BGRGRAY)
    elif len(img.shape) == :
        img = img[:, :, ]
        img = img[:, :, ]

     转为float
    img = img.astype(np.float)
    img = img.astype(np.float)

     高斯核
    kernel = cv.getGaussianKernel(, .)
    window = np.outer(kernel, kernel.transpose())

     计算均值
    mu = cv.filterD(img, -, window)[:-, :-]
    mu = cv.filterD(img, -, window)[:-, :-]

    mu_sq = mu  
    mu_sq = mu  
    mu_mu = mu  mu

     计算方差和协方差
    sigma_sq = cv.filterD(img, -, window)[:-, :-] - mu_sq
    sigma_sq = cv.filterD(img, -, window)[:-, :-] - mu_sq
    sigma = cv.filterD(img  img, -, window)[:-, :-] - mu_mu

     计算SSIM
    ssim_map = ((  mu_mu + C)  (  sigma + C)) / ((mu_sq + mu_sq + C)  (sigma_sq + sigma_sq + C))
    return float(ssim_map.mean())


 ===================== 核心配置 =====================
os.environ['PYTORCH_ALLOC_CONF'] = 'expandable_segments:True'
os.environ['CUDA_LAUNCH_BLOCKING'] = ''
torch.backends.cudnn.benchmark = True
torch.backends.cudnn.deterministic = False
torch.backends.cuda.matmul.allow_tf = True
torch.backends.cudnn.allow_tf = True
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

 ===================== 带倍上采样的超分模型 =====================


class LUMWCNN(nn.Module):
    """带强制倍上采样的超分模型（确保输出x）"""

    def __init__(self, in_channels=, upscale_factor=):
        super().__init__()
        self.upscale_factor = upscale_factor

         基础特征提取
        self.features = nn.Sequential(
            nn.Convd(in_channels, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True)
        )

         强制倍上采样模块
        self.upsample = nn.Sequential(
            nn.Convd(,   (upscale_factor), kernel_size=, padding=),
            nn.PixelShuffle(upscale_factor),
            nn.Convd(, in_channels, kernel_size=, padding=),
            nn.Sigmoid()
        )

    def forward(self, x):
        features = self.features(x)
        out = self.upsample(features)
        return out

 ===================== 损失函数 =====================


class MyJointLoss(nn.Module):
    """联合损失函数（修复LPIPS + 严格尺寸校验）"""

    def __init__(self, lpips_weight=., image_mode='color'):
        super().__init__()
        self.mse = nn.MSELoss()
        self.lpips_weight = lpips_weight
        self.in_channels =  if image_mode == 'color' else 

         修复LPIPS加载
        self.lpips = LPIPS(net='vgg', version='.').to(device)
        self.lpips.eval()

    def forward(self, x, y):
         强制校验尺寸
        if x.shape != y.shape:
            raise RuntimeError(
                f"尺寸不匹配！模型输出{x.shape} vs 目标HR{y.shape}\n"
                f"请检查模型是否包含{y.shape[]//x.shape[]}倍上采样层"
            )

        x = x.clamp(, )
        y = y.clamp(, )
        mse_loss = self.mse(x, y)

        if self.lpips_weight > :
             适配灰度图
            if self.in_channels == :
                x = torch.cat([x, x, x], dim=)
                y = torch.cat([y, y, y], dim=)
             LPIPS归一化
            x_norm = (x - .)  
            y_norm = (y - .)  
            lpips_loss = torch.mean(self.lpips(x_norm, y_norm))
            total_loss = mse_loss + self.lpips_weight  lpips_loss
        else:
            total_loss = mse_loss
        return total_loss

 ===================== 数据集 =====================


class DIVKDataset(Dataset):
    """超分数据集（LR:x → HR:x）"""

    def __init__(self, data_dir, crop_size=, noise_std=., phase='train', image_mode='color'):
        self.data_dir = data_dir
        self.crop_size = crop_size
        self.lr_size = crop_size // 
        self.noise_std = noise_std / .
        self.phase = phase
        self.image_mode = image_mode

        self.valid_files = [
            os.path.join(data_dir, f) for f in os.listdir(data_dir)
            if f.lower().endswith(('.png', '.jpg', '.jpeg'))
        ]
        assert len(self.valid_files) > , f"{phase}目录无有效图像: {data_dir}"

         裁剪策略
        if phase == 'train':
            self.crop_transform = transforms.RandomCrop(crop_size)
        else:
            self.crop_transform = transforms.CenterCrop(crop_size)
        self.to_tensor = transforms.ToTensor()

    def __len__(self):
        return len(self.valid_files)

    def __getitem__(self, idx):
        fpath = self.valid_files[idx]
        with Image.open(fpath) as img:
             转换图像模式
            img = img.convert('L' if self.image_mode == 'gray' else 'RGB')
             裁剪HR图像
            hr_img = self.crop_transform(img)
            hr_tensor = self.to_tensor(hr_img)

             生成LR图像
            lr_tensor = F.interpolate(
                hr_tensor.unsqueeze(),
                size=(self.lr_size, self.lr_size),
                mode='bicubic',
                align_corners=False
            ).squeeze()

             训练阶段加噪声
            if self.phase == 'train':
                lr_tensor = lr_tensor + torch.randn_like(lr_tensor)  self.noise_std
                lr_tensor = torch.clamp(lr_tensor, ., .)

             验证尺寸
            assert lr_tensor.shape[:] == (self.lr_size, self.lr_size), f"LR尺寸错误: {lr_tensor.shape}"
            assert hr_tensor.shape[:] == (self.crop_size, self.crop_size), f"HR尺寸错误: {hr_tensor.shape}"

            return lr_tensor, hr_tensor

 ===================== 训练工具 =====================


def init_model(args, device: torch.device):
    """初始化模型"""
    in_channels =  if args.image_mode == 'color' else 
    model = LUMWCNN(in_channels=in_channels, upscale_factor=).to(device)

     损失函数
    criterion = MyJointLoss(
        lpips_weight=args.lpips_weight,
        image_mode=args.image_mode
    ).to(device)

     优化器
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.lr,
        weight_decay=e-,
        betas=(., .),
        eps=e-
    )

     学习率调度器
    scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer,
        T_=,
        T_mult=,
        eta_min=e-
    )

     PyTorch .+ AMP
    scaler = GradScaler('cuda') if args.mixed_precision else None

    return model, criterion, optimizer, scheduler, scaler


def load_ckpt(args, model, optimizer, scheduler, scaler):
    start_epoch, best_psnr = , .
    if args.resume and os.path.exists(args.resume):
        ckpt = torch.load(args.resume, map_location=device)
        model.load_state_dict(ckpt['model'])
        optimizer.load_state_dict(ckpt['optimizer'])
        scheduler.load_state_dict(ckpt['scheduler'])
        start_epoch = ckpt['epoch'] + 
        best_psnr = ckpt.get('best_psnr', .)
        if scaler and 'scaler' in ckpt:
            scaler.load_state_dict(ckpt['scaler'])
        print(f" 恢复训练：从epoch {start_epoch} 开始，最佳PSNR {best_psnr:.f}")
    return start_epoch, best_psnr


def train_one_epoch(model, loader, criterion, optimizer, scheduler, scaler, epoch, args):
    model.train()
    total_loss = .
    pbar = tqdm(loader, desc=f"Epoch {epoch + }", ncols=)

    for step, (lr, hr) in enumerate(pbar):
        lr, hr = lr.to(device, non_blocking=True), hr.to(device, non_blocking=True)

         PyTorch .+ autocast
        with autocast('cuda', enabled=scaler is not None):
            pred = model(lr)
            loss = criterion(pred, hr)
            loss = loss / args.grad_accum_steps

         反向传播
        if scaler:
            scaler.scale(loss).backward()
        else:
            loss.backward()

         梯度累积
        if (step + ) % args.grad_accum_steps == :
            if scaler:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=.)
                scaler.step(optimizer)
                scaler.update()
            else:
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=.)
                optimizer.step()
            optimizer.zero_grad(set_to_none=True)

         调试输出
        if step %  == :
            pred_np = pred[].cpu().detach().numpy().transpose(, , )
            hr_np = hr[].cpu().numpy().transpose(, , )
            if pred_np.shape[] == :
                pred_np = pred_np.squeeze()
                hr_np = hr_np.squeeze()
            cv.imwrite(f"./debug/debug_epoch{epoch}_step{step}_pred.png", (pred_np  ).clip(, ).astype(np.uint))
            cv.imwrite(f"./debug/debug_epoch{epoch}_step{step}_gt.png", (hr_np  ).clip(, ).astype(np.uint))

        total_loss += loss.item()  args.grad_accum_steps
        pbar.set_postfix(loss=f"{total_loss / (step + ):.f}", lr=f"{scheduler.get_last_lr()[]:.e}")

    scheduler.step()
    return total_loss / len(loader)

 ===================== 彻底修复的validate函数 =====================


@torch.no_grad()
def validate(model, loader, device):
    model.eval()
    total_psnr, total_ssim = ., .
    total_samples = 
    test_cases = 

    for i, (lr, hr) in enumerate(loader):
        if i >= test_cases:
            break

         零输入测试
        if i == :
            zero_input = torch.zeros_like(lr[]).unsqueeze().to(device)
            with autocast('cuda', enabled=True):
                pred_zero = model(zero_input).clamp(, )
            mse_zero = F.mse_loss(pred_zero, hr[].unsqueeze().to(device))
            psnr_zero =   torch.log( / (mse_zero + e-))
            print(f"零输入PSNR: {psnr_zero.item():.f} dB")

         正常验证
        lr, hr = lr.to(device), hr.to(device)
        with autocast('cuda', enabled=True):
            pred = model(lr).clamp(, )

         计算指标（彻底修复SSIM）
        batch_size = pred.size()
        for j in range(batch_size):
             转换为numpy数组
            pred_j = pred[j].permute(, , ).cpu().numpy()  
            hr_j = hr[j].permute(, , ).cpu().numpy()  

             确保数据类型正确
            pred_j = pred_j.astype(np.uint)
            hr_j = hr_j.astype(np.uint)

             ========== 使用自定义SSIM计算（彻底避开cv兼容性问题） ==========
             彩色图转BGR
            if pred_j.ndim ==  and pred_j.shape[] == :
                pred_bgr = cv.cvtColor(pred_j, cv.COLOR_RGBBGR)
                hr_bgr = cv.cvtColor(hr_j, cv.COLOR_RGBBGR)
                ssim_j = calculate_ssim(pred_bgr, hr_bgr)
             灰度图
            else:
                pred_gray = pred_j.squeeze() if pred_j.ndim ==  else pred_j
                hr_gray = hr_j.squeeze() if hr_j.ndim ==  else hr_j
                ssim_j = calculate_ssim(pred_gray, hr_gray)

             计算PSNR
            mse_j = np.mean((pred_j.astype(np.float) - hr_j.astype(np.float))  )
            psnr_j =   np.log(   / (mse_j + e-))

             确保是浮点数
            psnr_j = float(psnr_j)
            ssim_j = float(ssim_j)

            total_psnr += psnr_j
            total_ssim += ssim_j
            total_samples += 

     计算平均值
    avg_psnr = total_psnr / total_samples if total_samples >  else .
    avg_ssim = total_ssim / total_samples if total_samples >  else .
    print(f"验证结果：PSNR {avg_psnr:.f} dB | SSIM {avg_ssim:.f}")
    return avg_psnr, avg_ssim

 ===================== 主函数 =====================


def get_args():
    parser = argparse.ArgumentParser(description='LU-MWCNN 超分模型（最终修复版）')
    parser.add_argument('--lr', type=float, default=e-, help='学习率')
    parser.add_argument('--epochs', type=int, default=, help='训练轮数')
    parser.add_argument('--batch_size', type=int, default=, help='批次大小')
    parser.add_argument('--crop_size', type=int, default=, help='HR图像裁剪尺寸')
    parser.add_argument('--noise_std', type=float, default=., help='噪声标准差')
    parser.add_argument('--image_mode', type=str, default='color', choices=['color', 'gray'])
    parser.add_argument('--lpips_weight', type=float, default=., help='LPIPS权重')
    parser.add_argument('--mixed_precision', action='store_true', default=True, help='混合精度')
    parser.add_argument('--grad_accum_steps', type=int, default=, help='梯度累积')
    parser.add_argument('--resume', type=str, default=None, help='恢复训练')
    parser.add_argument('--data_dir', type=str, default='/home/dake/Documents/Projects/datasets/DIVK_HR/', help='数据集目录')
    parser.add_argument('--output_dir', type=str, default='./output_divk_opt', help='输出目录')
    return parser.parse_args()


def main():
    args = get_args()
    os.makedirs(args.output_dir, exist_ok=True)

     初始化模型
    model, criterion, optimizer, scheduler, scaler = init_model(args, device)
    start_epoch, best_psnr = load_ckpt(args, model, optimizer, scheduler, scaler)

     构建数据集
    train_set = DIVKDataset(
        os.path.join(args.data_dir, 'train'),
        crop_size=args.crop_size,
        noise_std=args.noise_std,
        phase='train',
        image_mode=args.image_mode
    )
    val_set = DIVKDataset(
        os.path.join(args.data_dir, 'val'),
        crop_size=args.crop_size,
        noise_std=args.noise_std,
        phase='val',
        image_mode=args.image_mode
    )

     数据加载器
    train_loader = DataLoader(
        train_set,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=,
        pin_memory=True,
        drop_last=True
    )
    val_loader = DataLoader(
        val_set,
        batch_size=,
        shuffle=False,
        num_workers=,
        pin_memory=True
    )

     预验证模型输出尺寸
    print("=== 模型尺寸验证 ===")
    test_lr = torch.randn(, , , ).to(device)
    test_pred = model(test_lr)
    print(f"输入LR尺寸: {test_lr.shape}")
    print(f"输出HR尺寸: {test_pred.shape} (预期: [, , , ])")
    assert test_pred.shape == (, , , ), "模型输出尺寸错误！请检查上采样层"

     验证数据集尺寸
    print("\n=== 数据集结构验证 ===")
    for i, (lr, hr) in enumerate(train_loader):
        if i == :
            print(f"LR批次尺寸: {lr.shape} | HR批次尺寸: {hr.shape}")
            utils.save_image(lr[], "debug_lr.png", normalize=True)
            utils.save_image(hr[], "debug_hr.png", normalize=True)
        if i >= :
            break

     开始训练
    tb = SummaryWriter(os.path.join(args.output_dir, 'tb_logs'))
    print(f"\n 开始训练：批次{args.batch_size} | 累积步数{args.grad_accum_steps}")

    for epoch in range(start_epoch, args.epochs):
        train_loss = train_one_epoch(model, train_loader, criterion, optimizer, scheduler, scaler, epoch, args)
        tb.add_scalar('train/loss', train_loss, epoch)

         验证与保存
        if (epoch + ) %  == :
            val_psnr, val_ssim = validate(model, val_loader, device)
            tb.add_scalar('val/psnr', val_psnr, epoch)
            tb.add_scalar('val/ssim', val_ssim, epoch)

            if val_psnr > best_psnr:
                best_psnr = val_psnr
                torch.save({
                    'epoch': epoch,
                    'model': model.state_dict(),
                    'optimizer': optimizer.state_dict(),
                    'scheduler': scheduler.state_dict(),
                    'scaler': scaler.state_dict() if scaler else None,
                    'best_psnr': best_psnr
                }, os.path.join(args.output_dir, 'best_model.pth'))
                print(f" 更新最佳模型：PSNR {best_psnr:.f}")

        if (epoch + ) %  == :
            torch.save({
                'epoch': epoch,
                'model': model.state_dict(),
                'optimizer': optimizer.state_dict(),
                'scheduler': scheduler.state_dict(),
                'scaler': scaler.state_dict() if scaler else None
            }, os.path.join(args.output_dir, f'epoch_{epoch}.pth'))

    tb.close()
    print(f"\n 训练完成！最佳PSNR：{best_psnr:.f}")


if __name__ == '__main__':
     忽略无关警告
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="torchvision")
    warnings.filterwarnings("ignore", category=FutureWarning, module="torch.amp")

    try:
        main()
    except Exception as e:
        print(f"\n 训练出错：{e}")
        torch.cuda.empty_cache()
        raise
