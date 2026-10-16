'''
    WaveletUNet (LUMWCNN) 超分训练代码 @ DIVK/VOC
    适配要求：断点续传、早停、学习率回火、最优模型保存、高PSNR/SSIM
    重构：模块化拆分主函数，降低复杂度，修复硬伤逻辑
'''

 保持原始导入库不变（确保自定义库兼容）
from lpips import LPIPS
import os
from tqdm import tqdm
import torch
import torch.nn as nn
import torchvision.transforms as transforms
import numpy as np
from PIL import Image
import importlib
from utils.lpips import calc_lpips
from utils.metrics import 
from utils.meters import AverageMeter
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.utils.data import DataLoader, Dataset
from model import LUMWCNN   导入修复后的WaveletUNet模型
from torch.utils.tensorboard import SummaryWriter
import sys
import os.path as path
import warnings
from typing import Tuple, Dict, Any, Optional, List
warnings.filterwarnings('ignore')

 ===================== . 核心配置（适配你的数据集路径） =====================
 基础参数
LR = e-
EPOCH = 
BATCH_SIZE = 
VAL_EVERY =    缩短验证间隔，更早捕捉最优模型
OUTPUT_PATH = r'./output_divk'   适配你的路径
RESUME = True   开启断点续传
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

 数据集配置（优先DIVK，VOC作为补充）
CommonOpt = {
     主数据集：DIVK（你的路径）
    'train_dir': r'../datasets/DIVK_HR/train/',
    'val_dir': r'../datasets/DIVK_HR/val/',
     补充数据集：VOC（可选切换）
     'train_dir': r'../datasets/VOC/sr_split/train/',
     'val_dir': r'../datasets/VOC/sr_split/val/',
    'dataset_interface': 'divk.DIVKDataset',

     数据预处理（超分任务核心配置）
    'crop_size': ,
    'noise_std': .,   轻微噪声增强，提升鲁棒性
    'scale': ,   倍超分（匹配模型scale参数）

     数据加载
    'num_workers': ,   适配个人设备，避免内存溢出
}

 早停&回火配置
EARLY_STOP_PATIENCE =    轮无提升则早停
LR_RESTORE_PATIENCE =    轮无提升则学习率回火
LR_RESTORE_FACTOR = .    回火系数
MIN_LR = e-              最小学习率，防止训练停滞

 ===================== . 工具函数 & 损失函数（保持兼容） =====================
tb = SummaryWriter(os.path.join(OUTPUT_PATH, './tensorboard'))


class MyJointLoss(nn.Module):
    def __init__(self, lpips_weight=.):   降低LPIPS权重，优先保证PSNR/SSIM
        super(MyJointLoss, self).__init__()
        print('\nLoading VGG LPIPS for joint loss...\n')
        self.lpips = LPIPS(net='vgg').to(DEVICE)
        self.mse = nn.MSELoss()
        self.lpips_weight = lpips_weight

    def forward(self, x, y):
        def normalize(tensor):   normalize to [-, ]
            return (tensor.clamp(, ) - .)  
        return torch.mean(self.mse(x, y) + self.lpips_weight  self.lpips(normalize(x), normalize(y)))

 ===================== . 断点续传函数 =====================


def load_checkpoint(
    model: nn.Module,
    optimizer: optim.Optimizer,
    scheduler: lr_scheduler._LRScheduler,
    output_path: str
) -> Tuple[nn.Module, optim.Optimizer, lr_scheduler._LRScheduler, int, float, float]:
    """加载断点续传检查点

    Args:
        model: 训练模型
        optimizer: 优化器
        scheduler: 学习率调度器
        output_path: 检查点保存路径

    Returns:
        模型、优化器、调度器、起始epoch、最优PSNR、最优SSIM
    """
    checkpoint_path = os.path.join(output_path, 'latest_checkpoint.pth')
    start_epoch = 
    best_psnr = .
    best_ssim = .
    if os.path.exists(checkpoint_path) and RESUME:
        checkpoint = torch.load(checkpoint_path, map_location=DEVICE)
        model.load_state_dict(checkpoint['model_state_dict'])
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
        start_epoch = checkpoint['epoch'] + 
        best_psnr = checkpoint['best_psnr']
        best_ssim = checkpoint['best_ssim']
        print(
            f" 断点续传：从第 {start_epoch} 轮恢复训练，历史最优PSNR: {best_psnr:.f}, SSIM: {best_ssim:.f}")
    else:
        print(" 全新训练，无断点可恢复")
    return model, optimizer, scheduler, start_epoch, best_psnr, best_ssim

 ===================== . 保存检查点 =====================


def save_checkpoint(
    model: nn.Module,
    optimizer: optim.Optimizer,
    scheduler: lr_scheduler._LRScheduler,
    epoch: int,
    best_psnr: float,
    best_ssim: float,
    output_path: str
) -> None:
    """保存训练检查点（最新断点+当前epoch模型）

    Args:
        model: 训练模型
        optimizer: 优化器
        scheduler: 学习率调度器
        epoch: 当前训练轮次
        best_psnr: 最优PSNR
        best_ssim: 最优SSIM
        output_path: 保存路径
    """
     确保保存目录存在
    os.makedirs(output_path, exist_ok=True)
    ckp_dir = os.path.join(output_path, './ckp/')
    os.makedirs(ckp_dir, exist_ok=True)

     保存最新断点
    checkpoint = {
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': scheduler.state_dict(),
        'best_psnr': best_psnr,
        'best_ssim': best_ssim
    }
    checkpoint_path = os.path.join(output_path, 'latest_checkpoint.pth')
    torch.save(checkpoint, checkpoint_path)

     保存当前轮次pth（按要求保留所有轮次）
    epoch_pth_path = os.path.join(ckp_dir, f'epoch_{epoch}.pth')
    torch.save(model.state_dict(), epoch_pth_path)

 ===================== . 学习率回火 =====================


def adjust_lr_with_restore(
    optimizer: optim.Optimizer,
    current_lr: float,
    restore_factor: float = LR_RESTORE_FACTOR
) -> float:
    """学习率回火调整

    Args:
        optimizer: 优化器
        current_lr: 当前学习率
        restore_factor: 回火系数

    Returns:
        调整后的学习率
    """
    new_lr = current_lr  restore_factor
    if new_lr < MIN_LR:
        new_lr = MIN_LR
    for param_group in optimizer.param_groups:
        param_group['lr'] = new_lr
    print(f" 学习率回火：{current_lr:.f} → {new_lr:.f}")
    return new_lr

 ===================== . 模块化核心函数 =====================


def init_model(scale: int) -> nn.Module:
    """初始化LUMWCNN模型

    Args:
        scale: 超分倍数

    Returns:
        初始化后的模型
    """
    model = LUMWCNN(in_channels=, device=DEVICE, scale=scale)   超分倍，灰度通道
    model = model.to(DEVICE)
    print(f" 模型初始化完成，设备：{DEVICE}，超分倍数：{scale}")
    return model


def init_optimizer_scheduler(
    model: nn.Module,
    lr: float,
    epoch: int
) -> Tuple[MyJointLoss, optim.Optimizer, lr_scheduler._LRScheduler]:
    """初始化损失函数、优化器、学习率调度器

    Args:
        model: 训练模型
        lr: 初始学习率
        epoch: 总训练轮次

    Returns:
        损失函数、优化器、调度器
    """
    criterion = MyJointLoss(lpips_weight=.)   降低LPIPS权重，优先PSNR/SSIM
    optimizer = optim.Adam(
        model.parameters(),
        lr=lr,
        weight_decay=e-,
        betas=(., .),
        eps=e-
    )
     学习率调度：每轮衰减.（基础调度）
    scheduler = lr_scheduler.MultiStepLR(
        optimizer,
        list(range(, epoch, )),
        gamma=.
    )
    return criterion, optimizer, scheduler


def load_dataset(cfg: Dict[str, Any]) -> Tuple[DataLoader, DataLoader]:
    """加载训练/验证数据集

    Args:
        cfg: 数据集配置字典

    Returns:
        训练加载器、验证加载器
    """
    print(' 当前数据集接口: ', cfg['dataset_interface'])
     动态导入数据集类
    dataset_module = importlib.import_module(
        '.' + cfg['dataset_interface'].split('.')[], 'datasets')
    dataset_class = eval(
        f'dataset_module.{cfg["dataset_interface"].split(".")[]}')

     构建数据集
    train_set = dataset_class(
        cfg['train_dir'], cfg['crop_size'], cfg['noise_std'], 'train')
    val_set = dataset_class(
        cfg['val_dir'], cfg['crop_size'], cfg['noise_std'], 'val')

     构建数据加载器
    train_loader = DataLoader(
        train_set,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=cfg['num_workers'],
        pin_memory=True   修复硬伤：添加pin_memory提升GPU加载效率
    )
    val_loader = DataLoader(
        val_set,
        batch_size=,
        shuffle=False,
        pin_memory=True
    )
    return train_loader, val_loader


def train_one_epoch(
    model: nn.Module,
    train_loader: DataLoader,
    criterion: MyJointLoss,
    optimizer: optim.Optimizer,
    epoch: int,
    total_epoch: int,
    current_lr: float
) -> float:
    """单轮训练函数

    Args:
        model: 训练模型
        train_loader: 训练数据加载器
        criterion: 损失函数
        optimizer: 优化器
        epoch: 当前轮次
        total_epoch: 总轮次
        current_lr: 当前学习率

    Returns:
        本轮平均训练损失
    """
    model.train()
    epoch_loss = AverageMeter()
    total_samples = len(train_loader.dataset) - \
        len(train_loader.dataset) % BATCH_SIZE

     训练进度条
    with tqdm(total=total_samples, ncols=, desc='Training') as t:
        t.set_description(
            f'Epoch: {epoch + }/{total_epoch} (LR: {current_lr:.f})')

        for data in train_loader:
            lr_img, hr_img = data
             修复硬伤：non_blocking提升效率
            lr_img = lr_img.to(DEVICE, non_blocking=True)
            hr_img = hr_img.to(DEVICE, non_blocking=True)

             前向传播
            predict = model(lr_img)
            loss = criterion(predict, hr_img)

             反向传播
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

             更新损失
            epoch_loss.update(torch.mean(loss))
            t.set_postfix(loss=f'{epoch_loss.avg:.f}')
            t.update(len(lr_img))

    return epoch_loss.avg.item()


def validate_one_epoch(
    model: nn.Module,
    val_loader: DataLoader,
    output_path: str,
    epoch: int
) -> Tuple[float, float, float]:
    """单轮验证函数

    Args:
        model: 训练模型
        val_loader: 验证数据加载器
        output_path: 验证结果保存路径
        epoch: 当前轮次

    Returns:
        平均PSNR、平均SSIM、平均LPIPS
    """
    model.eval()
    model.valing = True   开启模型内形状打印（调试用）
    epoch_psnr = AverageMeter()
    epoch_ssim = AverageMeter()
    epoch_lpips = AverageMeter()

     确保验证结果保存目录存在
    save_dir = os.path.join(output_path, './val_inference/')
    os.makedirs(save_dir, exist_ok=True)

    with torch.no_grad():
        for data in tqdm(val_loader, ncols=, desc='Validation'):
            lr, hr, cb_lr, cr_lr, filename = data
            lr = lr.to(DEVICE, non_blocking=True)
            hr = hr.to(DEVICE, non_blocking=True)

             模型推理
            predict = model(lr).detach().cpu().clamp(, )

             修复硬伤：安全维度压缩（避免多维度挤压导致的形状错误）
            predict = predict.squeeze()   先去掉batch维度
            if predict.dim() == :
                predict = predict.squeeze()   去掉通道维度
            hr = hr.squeeze().squeeze().cpu()   同步hr维度

             计算核心指标（Y通道）
            epoch_psnr.update(calc_psnr_torch(predict, hr))
            epoch_ssim.update(calc_ssim_torch(predict, hr))
            epoch_lpips.update(calc_lpips(predict, hr))

             保存验证结果
            predict_y = np.array(predict.numpy()  , dtype=np.uint)
            predict_y_img = Image.fromarray(predict_y, mode='L')
            predict_y_img.save(os.path.join(
                save_dir, f'{filename[]}_epoch_{epoch+}_y.png'))

             输入噪声图保存
            noisy_y = np.array(lr.detach().cpu().squeeze(
                ).squeeze().numpy()  , dtype=np.uint)
            noisy_y_img = Image.fromarray(noisy_y, mode='L')
            noisy_y_img.save(os.path.join(
                save_dir, f'{filename[]}_epoch_{epoch+}_lr.png'))

     打印验证指标
    print(f"\n Epoch {epoch+} 验证结果：")
    print(
        f"PSNR: {epoch_psnr.avg:.f} | SSIM: {epoch_ssim.avg:.f} | LPIPS: {epoch_lpips.avg:.f}")

    return epoch_psnr.avg.item(), epoch_ssim.avg.item(), epoch_lpips.avg.item()

 ===================== . 主函数 =====================


def main() -> None:
    """主训练流程入口"""
    try:
         . 初始化模型
        model = init_model(CommonOpt['scale'])

         . 初始化损失函数、优化器、调度器
        criterion, optimizer, scheduler = init_optimizer_scheduler(
            model, LR, EPOCH)

         . 断点续传加载
        model, optimizer, scheduler, start_epoch, best_psnr, best_ssim = load_checkpoint(
            model, optimizer, scheduler, OUTPUT_PATH
        )

         . 加载数据集
        train_loader, val_loader = load_dataset(CommonOpt)

         . 早停&回火计数器初始化
        early_stop_count = 
        lr_restore_count = 
        current_lr = LR

         . 核心训练循环
        for epoch in range(start_epoch, EPOCH):
             单轮训练
            train_loss = train_one_epoch(
                model=model,
                train_loader=train_loader,
                criterion=criterion,
                optimizer=optimizer,
                epoch=epoch,
                total_epoch=EPOCH,
                current_lr=current_lr
            )

             记录训练损失
            tb.add_scalar('Train/Loss', train_loss, global_step=epoch)

             学习率基础调度
            scheduler.step()
            current_lr = optimizer.param_groups[]['lr']

             . 验证流程（缩短验证间隔，更早捕捉最优模型）
            if epoch ==  or (epoch + ) % VAL_EVERY == :
                 单轮验证
                val_psnr, val_ssim, val_lpips = validate_one_epoch(
                    model=model,
                    val_loader=val_loader,
                    output_path=OUTPUT_PATH,
                    epoch=epoch
                )

                 记录验证指标
                tb.add_scalar('Val/PSNR', val_psnr, global_step=epoch)
                tb.add_scalar('Val/SSIM', val_ssim, global_step=epoch)
                tb.add_scalar('Val/LPIPS', val_lpips, global_step=epoch)

                 . 最优模型保存（PSNR优先，SSIM辅助）
                if val_psnr > best_psnr or (val_psnr == best_psnr and val_ssim > best_ssim):
                    best_psnr = val_psnr
                    best_ssim = val_ssim
                     保存最优模型
                    best_model_path = os.path.join(
                        OUTPUT_PATH, 'best_model.pth')
                    torch.save(model.state_dict(), best_model_path)
                    print(
                        f" 最优模型更新：PSNR={best_psnr:.f}, SSIM={best_ssim:.f} → 保存至 {best_model_path}")
                     重置早停/回火计数器
                    early_stop_count = 
                    lr_restore_count = 
                else:
                     无提升，计数器+
                    early_stop_count += 
                    lr_restore_count += 
                    print(
                        f"️  无提升：早停计数={early_stop_count}/{EARLY_STOP_PATIENCE}，回火计数={lr_restore_count}/{LR_RESTORE_PATIENCE}")

                     学习率回火触发
                    if lr_restore_count >= LR_RESTORE_PATIENCE:
                        current_lr = adjust_lr_with_restore(
                            optimizer, current_lr)
                        lr_restore_count =    重置回火计数

                     早停触发
                    if early_stop_count >= EARLY_STOP_PATIENCE:
                        print(f" 早停触发：连续{EARLY_STOP_PATIENCE}轮无提升，终止训练")
                        print(
                            f" 最终最优指标：PSNR={best_psnr:.f}, SSIM={best_ssim:.f}")
                        break

             . 保存检查点（每轮都保存，保证断点续传+所有轮次pth）
            save_checkpoint(
                model=model,
                optimizer=optimizer,
                scheduler=scheduler,
                epoch=epoch,
                best_psnr=best_psnr,
                best_ssim=best_ssim,
                output_path=OUTPUT_PATH
            )

         训练结束总结
        print("\n==================== 训练完成 ====================")
        print(f" 最优模型路径：{os.path.join(OUTPUT_PATH, 'best_model.pth')}")
        print(f" 最优指标：PSNR={best_psnr:.f}, SSIM={best_ssim:.f}")
        print(f" 所有轮次PTH保存路径：{os.path.join(OUTPUT_PATH, './ckp/')}")

    except Exception as e:
        print(f" 训练过程出错：{str(e)}")
        raise
    finally:
        tb.close()


if __name__ == '__main__':
    main()
