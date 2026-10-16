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
from torch.amp import autocast, GradScaler
 导入自定义模型（modell.py放在同目录）
from modell import LUMWCNN

 ===================== 通用工具函数（稳定计算SSIM/PSNR） =====================


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
    """通用SSIM计算（兼容彩色/灰度，无cv版本依赖）"""
    C = (.  )  
    C = (.  )  

     统一转为灰度（彩色图）
    if len(img.shape) ==  and img.shape[] == :
        img = cv.cvtColor(img, cv.COLOR_RGBGRAY)
        img = cv.cvtColor(img, cv.COLOR_RGBGRAY)
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

     方差和协方差
    sigma_sq = cv.filterD(img, -, window)[:-, :-] - mu_sq
    sigma_sq = cv.filterD(img, -, window)[:-, :-] - mu_sq
    sigma = cv.filterD(img  img, -, window)[:-, :-] - mu_mu

     SSIM计算
    ssim_map = ((  mu_mu + C)  (  sigma + C)) / ((mu_sq + mu_sq + C)  (sigma_sq + sigma_sq + C))
    return float(ssim_map.mean())


def calculate_psnr(img, img):
    """稳定计算PSNR（避免除零）"""
    img = img.astype(np.float)
    img = img.astype(np.float)
    mse = np.mean((img - img)  )
    if mse == :
        return float('inf')
    return   np.log((  ) / mse)


 ===================== 核心配置 =====================
os.environ['PYTORCH_ALLOC_CONF'] = 'expandable_segments:True'
os.environ['CUDA_LAUNCH_BLOCKING'] = ''
torch.backends.cudnn.benchmark = True
torch.backends.cudnn.deterministic = False
torch.backends.cuda.matmul.allow_tf = True
torch.backends.cudnn.allow_tf = True
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

 ===================== 损失函数（适配模型） =====================


class JointLoss(nn.Module):
    """联合损失（MSE + LPIPS，兼容灰度/彩色）"""

    def __init__(self, lpips_weight=., image_mode='color'):
        super().__init__()
        self.mse = nn.MSELoss()
        self.lpips_weight = lpips_weight
        self.in_channels =  if image_mode == 'color' else 

         LPIPS加载（绑定到设备）
        self.lpips = LPIPS(net='vgg', version='.').to(device)
        self.lpips.eval()

    def forward(self, pred, target):
         尺寸对齐（解决小波变换pad/shave导致的尺寸差异）
        min_h = min(pred.shape[], target.shape[])
        min_w = min(pred.shape[], target.shape[])
        pred = pred[:, :, :min_h, :min_w]
        target = target[:, :, :min_h, :min_w]

        pred = pred.clamp(, )
        target = target.clamp(, )
        mse_loss = self.mse(pred, target)

        if self.lpips_weight > :
             灰度转通道适配LPIPS
            if self.in_channels == :
                pred_rgb = torch.cat([pred, pred, pred], dim=)
                target_rgb = torch.cat([target, target, target], dim=)
            else:
                pred_rgb = pred
                target_rgb = target

             LPIPS归一化
            pred_norm = (pred_rgb - .)  
            target_norm = (target_rgb - .)  
            lpips_loss = torch.mean(self.lpips(pred_norm, target_norm))
            total_loss = mse_loss + self.lpips_weight  lpips_loss
        else:
            total_loss = mse_loss
        return total_loss

 ===================== 数据集（超分/去噪通用） =====================


class LUNADataset(Dataset):
    """LUNA CT切片超分数据集（灰度单通道）"""

    def __init__(self, data_dir, crop_size=, scale=, phase='train'):
        self.data_dir = data_dir
        self.crop_size = crop_size   HR切片尺寸（必须是scale的整数倍）
        self.scale = scale           超分倍数
        self.lr_size = (crop_size // scale, crop_size // scale)
        self.phase = phase

         筛选CT切片（PNG格式）
        self.valid_files = [
            os.path.join(data_dir, f) for f in os.listdir(data_dir)
            if f.lower().endswith(".png")
        ]
        assert len(self.valid_files) > , f"{phase}目录无有效CT切片: {data_dir}"
        assert crop_size % scale == , f"crop_size({crop_size})必须是scale({scale})的整数倍"

         裁剪策略
        if phase == 'train':
            self.crop_hr = transforms.RandomCrop(crop_size)
        else:
            self.crop_hr = transforms.CenterCrop(crop_size)
        self.to_tensor = transforms.ToTensor()

    def __len__(self):
        return len(self.valid_files)

    def __getitem__(self, idx):
         . 加载CT灰度切片
        fpath = self.valid_files[idx]
        with Image.open(fpath) as img:
            img = img.convert('L')   强制转为灰度单通道
            hr_img = self.crop_hr(img)   裁剪HR切片

         . 生成LR切片（双三次下采样，超分核心逻辑）
        lr_img = hr_img.resize(self.lr_size, Image.BICUBIC)

         . 可选：加轻微噪声（适配医学影像特性）
        if self.phase == 'train':
            lr_np = np.array(lr_img).astype(np.float)
            noise = np.random.normal(, ., lr_np.shape)   极低噪声（医学影像少噪声）
            lr_np = np.clip(lr_np + noise, , ).astype(np.uint)
            lr_img = Image.fromarray(lr_np)

         . 转换为张量（-范围）
        hr_tensor = self.to_tensor(hr_img)   shape: (, crop_size, crop_size)
        lr_tensor = self.to_tensor(lr_img)   shape: (, lr_size[], lr_size[])

         . 尺寸校验
        assert hr_tensor.shape == (, self.crop_size, self.crop_size), f"HR尺寸错误: {hr_tensor.shape}"
        assert lr_tensor.shape == (, self.lr_size[], self.lr_size[]), f"LR尺寸错误: {lr_tensor.shape}"

        return lr_tensor, hr_tensor

 ===================== 训练/验证工具 =====================


def init_model(args, device):
    """初始化模型、损失、优化器"""
     初始化WaveletUNet/LUMWCNN
    model = LUMWCNN(in_channels= if args.image_mode == 'color' else , device=device)
    model = model.to(device)

     损失函数
    criterion = JointLoss(
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

     混合精度
    scaler = GradScaler('cuda') if args.mixed_precision else None

    return model, criterion, optimizer, scheduler, scaler


def load_ckpt(args, model, optimizer, scheduler, scaler):
    """加载断点"""
    start_epoch, best_psnr = , .
    if args.resume and os.path.exists(args.resume):
        ckpt = torch.load(args.resume, map_location=device)
         加载模型（兼容设备）
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
    """单轮训练"""
    model.train()
    total_loss = .
    pbar = tqdm(loader, desc=f"Epoch {epoch + }", ncols=)

    for step, (lr, hr) in enumerate(pbar):
        lr, hr = lr.to(device, non_blocking=True), hr.to(device, non_blocking=True)

         混合精度前向
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

         调试保存
        if step %  == :
            pred_np = pred[].cpu().detach().numpy().transpose(, , )
            hr_np = hr[].cpu().numpy().transpose(, , )
            if pred_np.shape[] == :
                pred_np = pred_np.squeeze()
                hr_np = hr_np.squeeze()
            cv.imwrite(f"debug_epoch{epoch}_step{step}_pred.png", (pred_np  ).clip(, ).astype(np.uint))
            cv.imwrite(f"debug_epoch{epoch}_step{step}_gt.png", (hr_np  ).clip(, ).astype(np.uint))

        total_loss += loss.item()  args.grad_accum_steps
        pbar.set_postfix(loss=f"{total_loss / (step + ):.f}", lr=f"{scheduler.get_last_lr()[]:.e}")

    scheduler.step()
    return total_loss / len(loader)


@ torch.no_grad()
def validate(model, loader, device, image_mode):
    """验证（计算PSNR/SSIM）"""
    model.eval()
    total_psnr, total_ssim = ., .
    total_samples = 

    for lr, hr in loader:
        lr, hr = lr.to(device), hr.to(device)
        with autocast('cuda', enabled=True):
            pred = model(lr).clamp(, )

         批次内计算指标
        batch_size = pred.size()
        for j in range(batch_size):
             转numpy（RGB/HWC格式）
            pred_j = pred[j].permute(, , ).cpu().numpy()  
            hr_j = hr[j].permute(, , ).cpu().numpy()  

             尺寸对齐
            min_h = min(pred_j.shape[], hr_j.shape[])
            min_w = min(pred_j.shape[], hr_j.shape[])
            pred_j = pred_j[:min_h, :min_w]
            hr_j = hr_j[:min_h, :min_w]

             类型转换
            pred_j = pred_j.astype(np.uint)
            hr_j = hr_j.astype(np.uint)

             计算SSIM/PSNR
            if image_mode == 'color':
                pred_bgr = cv.cvtColor(pred_j, cv.COLOR_RGBBGR)
                hr_bgr = cv.cvtColor(hr_j, cv.COLOR_RGBBGR)
                ssim = calculate_ssim(pred_bgr, hr_bgr)
                psnr = calculate_psnr(pred_bgr, hr_bgr)
            else:
                pred_gray = pred_j.squeeze()
                hr_gray = hr_j.squeeze()
                ssim = calculate_ssim(pred_gray, hr_gray)
                psnr = calculate_psnr(pred_gray, hr_gray)

            total_psnr += psnr
            total_ssim += ssim
            total_samples += 

     平均指标
    avg_psnr = total_psnr / total_samples if total_samples >  else .
    avg_ssim = total_ssim / total_samples if total_samples >  else .
    print(f"验证结果：PSNR {avg_psnr:.f} dB | SSIM {avg_ssim:.f}")
    return avg_psnr, avg_ssim

 ===================== 模型加载/使用示例（训练后直接调用） =====================


def load_model_for_inference(model_path, image_mode='color', device=None):
    """加载训练好的模型用于推理"""
    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

     初始化模型
    in_channels =  if image_mode == 'color' else 
    model = LUMWCNN(in_channels=in_channels, device=device)
    model = model.to(device)

     加载权重
    ckpt = torch.load(model_path, map_location=device)
    if 'model' in ckpt:   兼容训练保存的checkpoint
        model.load_state_dict(ckpt['model'])
    else:   直接保存的state_dict
        model.load_state_dict(ckpt)

    model.eval()
    return model


def infer_image(model, img_path, image_mode='color', device=None):
    """单张图像推理示例"""
    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

     图像预处理
    img = Image.open(img_path).convert('L' if image_mode == 'gray' else 'RGB')
    to_tensor = transforms.ToTensor()
    img_tensor = to_tensor(img).unsqueeze().to(device)

     推理
    with torch.no_grad():
        output = model(img_tensor).clamp(, )

     转PIL图像
    output_np = output.squeeze().permute(, , ).cpu().numpy()
    if image_mode == 'gray':
        output_np = output_np.squeeze()
    output_img = Image.fromarray((output_np  ).astype(np.uint))
    return output_img

 ===================== 主函数 =====================


def get_args():
    parser = argparse.ArgumentParser(description='WaveletUNet/LUMWCNN 训练（修复版）')
    parser.add_argument('--lr', type=float, default=e-, help='学习率')
    parser.add_argument('--epochs', type=int, default=, help='训练轮数')
    parser.add_argument('--batch_size', type=int, default=, help='批次大小')
    parser.add_argument('--crop_size', type=int, default=, help='图像裁剪尺寸')
     parser.add_argument('--noise_std', type=float, default=., help='噪声标准差')
    parser.add_argument('--scale', type=int, default=, help='超分倍数（//）')
    parser.add_argument('--image_mode', type=str, default='color', choices=['color', 'gray'])
    parser.add_argument('--lpips_weight', type=float, default=., help='LPIPS损失权重')
    parser.add_argument('--mixed_precision', action='store_true', default=True, help='混合精度训练')
    parser.add_argument('--grad_accum_steps', type=int, default=, help='梯度累积步数')
    parser.add_argument('--resume', type=str, default=None, help='恢复训练的checkpoint路径')
    parser.add_argument('--data_dir', type=str, default='/home/dake/Documents/Projects/datasets/DIVK_HR/', help='DIVK数据集根目录')
    parser.add_argument('--output_dir', type=str, default='./output_divk_wavelet', help='输出目录')
    return parser.parse_args()


def main():
    args = get_args()
    os.makedirs(args.output_dir, exist_ok=True)

     初始化模型（CT是单通道，image_mode=gray）
    model, criterion, optimizer, scheduler, scaler = init_model(args, device)
    start_epoch, best_psnr = load_ckpt(args, model, optimizer, scheduler, scaler)

     构建LUNA数据集（替换原DIVKDataset）
    train_set = LUNADataset(
        data_dir="/home/dake/Documents/Projects/datasets/LUNA/luna_slices/train",   训练集路径
        crop_size=args.crop_size,
        scale=args.scale,
        phase='train'
    )
    val_set = LUNADataset(
        data_dir="/home/dake/Documents/Projects/datasets/LUNA/luna_slices/val",     验证集路径
        crop_size=args.crop_size,
        scale=args.scale,
        phase='val'
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

     模型验证（确保前向正常）
    print("=== 模型前向验证 ===")
    test_input = torch.randn(,  if args.image_mode == 'color' else , , ).to(device)
    model.eval()
    with torch.no_grad():
        test_output = model(test_input)
    print(f"输入尺寸: {test_input.shape} | 输出尺寸: {test_output.shape}")
    model.train()

     TensorBoard日志
    tb = SummaryWriter(os.path.join(args.output_dir, 'tb_logs'))
    print(f"\n 开始训练：批次{args.batch_size} | 累积步数{args.grad_accum_steps}")

     训练循环
    for epoch in range(start_epoch, args.epochs):
         训练
        train_loss = train_one_epoch(model, train_loader, criterion, optimizer, scheduler, scaler, epoch, args)
        tb.add_scalar('train/loss', train_loss, epoch)

         验证+保存
        if (epoch + ) %  == :
            val_psnr, val_ssim = validate(model, val_loader, device, args.image_mode)
            tb.add_scalar('val/psnr', val_psnr, epoch)
            tb.add_scalar('val/ssim', val_ssim, epoch)

             保存最佳模型
            if val_psnr > best_psnr:
                best_psnr = val_psnr
                save_path = os.path.join(args.output_dir, 'best_model.pth')
                torch.save({
                    'epoch': epoch,
                    'model': model.state_dict(),
                    'optimizer': optimizer.state_dict(),
                    'scheduler': scheduler.state_dict(),
                    'scaler': scaler.state_dict() if scaler else None,
                    'best_psnr': best_psnr,
                    'args': args
                }, save_path)
                print(f" 保存最佳模型：{save_path} (PSNR {best_psnr:.f})")

         定期保存
        if (epoch + ) %  == :
            save_path = os.path.join(args.output_dir, f'epoch_{epoch}.pth')
            torch.save({
                'epoch': epoch,
                'model': model.state_dict(),
                'optimizer': optimizer.state_dict(),
                'scheduler': scheduler.state_dict(),
                'scaler': scaler.state_dict() if scaler else None
            }, save_path)
            print(f" 保存epoch {epoch}模型：{save_path}")

    tb.close()
    print(f"\n 训练完成！最佳PSNR：{best_psnr:.f}")
    print(f" 模型使用示例：")
    print(f"from {__file__.split('/')[-].split('.')[]} import load_model_for_inference, infer_image")
    print(f"model = load_model_for_inference('{os.path.join(args.output_dir, 'best_model.pth')}', image_mode='{args.image_mode}')")
    print(f"output_img = infer_image(model, 'test.jpg', image_mode='{args.image_mode}')")


if __name__ == '__main__':
     忽略无关警告
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="torchvision")
    warnings.filterwarnings("ignore", category=FutureWarning, module="torch.amp")

    try:
        '''
         测试超分数据集
        test_dataset = DIVKDataset(
            data_dir="/home/dake/Documents/Projects/datasets/DIVK_HR/train",
            crop_size=,
            scale=,
            phase='val',
            image_mode='color'
        )
        lr, hr = test_dataset[]
        print(f"LR尺寸: {lr.shape} (预期：××)")   倍超分，/=
        print(f"HR尺寸: {hr.shape} (预期：××)")

         保存可视化结果
        lr_np = lr.permute(, , ).numpy()  
        hr_np = hr.permute(, , ).numpy()  
        cv.imwrite("test_lr.png", cv.cvtColor(lr_np.astype(np.uint), cv.COLOR_RGBBGR))
        cv.imwrite("test_hr.png", cv.cvtColor(hr_np.astype(np.uint), cv.COLOR_RGBBGR))
        print(" 超分数据集测试完成，已保存LR/HR示例图像")
        '''
        main()
    except Exception as e:
        print(f"\n 训练出错：{e}")
        torch.cuda.empty_cache()
        raise
