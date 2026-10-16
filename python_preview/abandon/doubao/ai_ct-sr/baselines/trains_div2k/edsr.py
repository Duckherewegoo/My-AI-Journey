'''
    EDSR 在 DIV2K 上的训练代码。
    数据集：DIV2K，RGB 图像，但训练/验证指标只使用 Y 通道。
    验证时把 Cb/Cr 双三次上采样后与预测 Y 融合，恢复彩色图。
'''

import os
import os.path as path
import sys
import importlib
from PIL import Image
import numpy as np
from tqdm import tqdm

import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.utils.data import DataLoader
from torch.utils.tensorboard.writer import SummaryWriter
import torchvision.transforms as transforms

from base.models.edsr import EDSR
from base.utils.meters import AverageMeter
from base.utils.metrics import calc_psnr_torch, calc_ssim_torch
from base.utils.lpips import calc_lpips

dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__, '../'))

MainDir = r'../../nova/'
IODir = r'../'

EDSROpt = {
    # ===== 模型 =====
    # 从 epoch_199.pth 的 ckp 推断：
    # conv_in.weight (64, 1, 3, 3)
    # resblocks.0 ~ resblocks.15，共 16 个 resblock
    # conv_after_resblocks.weight (64, 64, 3, 3)
    # upsample_4x.conv1/conv2.weight (256, 64, 3, 3)
    # conv_out.weight (1, 64, 3, 3)
    'resblock_channels': 64,      # ckp 推断
    'resblock_depth': 16,         # ckp 推断：resblocks.0 ~ resblocks.15

    # ===== 训练 =====
    'lr': 1e-4,                   # 项目统一 / DWSR 脚本一致
    'epochs': 500,                # 项目统一 / DWSR 脚本一致
    'batch_size': 8,              # FIXME: 需你确认。3060 8GB 上 EDSR 保守值；若你记得是 16/4 请改。

    # ===== 验证 =====
    'val_every': 5,               # 项目统一 / DWSR 脚本一致
}

CommonOpt = {
    # ===== 数据集 =====
    'train_dir': os.path.join(MainDir, 'datasets/DIV2K_HR/train/'),
    'val_dir':   os.path.join(MainDir, 'datasets/DIV2K_HR/val/'),
    'dataset_interface': 'div2k.DIVKDataset',

    # ===== 数据预处理 =====
    'crop_size': 128,             # 项目统一 / DWSR 脚本一致
    'noise_std': 0.01,            # 项目统一 / DWSR 脚本一致

    # ===== 数据加载 =====
    'num_workers': 4,             # 项目统一 / 笔记本 CPU

    # ===== 结果输出 =====
    'output_path': os.path.join(IODir, 'baselines/outputs_div2k'),
}

tb = SummaryWriter(os.path.join(CommonOpt['output_path'], 'edsr/tensorboard'))


if __name__ == '__main__':
    # ===== 输出目录 =====
    ckp_dir = os.path.join(CommonOpt['output_path'], 'edsr/ckp/')
    val_infer_dir = os.path.join(CommonOpt['output_path'], 'edsr/val_inference/')
    os.makedirs(ckp_dir, exist_ok=True)
    os.makedirs(val_infer_dir, exist_ok=True)

    # ===== 模型 =====
    # EDSR 默认 scale=4, in_channels=1, out_channels=1
    model = EDSR(EDSROpt['resblock_channels'], EDSROpt['resblock_depth'])
    model = model.cuda()

    # ===== 损失与优化器 =====
    criterion = nn.MSELoss()
    optimizer = optim.Adam(
        model.parameters(),
        lr=EDSROpt['lr'],
        weight_decay=1e-4,        # 标准做法
        betas=(0.9, 0.999),       # 标准做法
        eps=1e-8,                 # 标准做法
    )

    # 学习率衰减：
    # 这里沿用 DWSR 脚本的项目统一写法：每 50 epoch 减半。
    # 如果你记得 EDSR 当时按原论文每 200 epoch 衰减，请把 50 改成 200。
    scheduler = lr_scheduler.MultiStepLR(
        optimizer,
        list(range(50, EDSROpt['epochs'], 50)),
        gamma=0.5,
    )

    # ===== 加载数据集 =====
    Dataset_ = importlib.import_module(
        '.' + CommonOpt['dataset_interface'].split('.')[0], 'base.datasets')
    Dataset_ = eval('Dataset_.{}'.format(
        CommonOpt['dataset_interface'].split('.')[1]))

    train_set = Dataset_(
        CommonOpt['train_dir'],
        CommonOpt['crop_size'],
        CommonOpt['noise_std'],
        'train',
    )
    train_loader = DataLoader(
        train_set,
        batch_size=EDSROpt['batch_size'],
        shuffle=True,
        num_workers=CommonOpt['num_workers'],
        pin_memory=True,
        drop_last=True,
    )

    val_set = Dataset_(
        CommonOpt['val_dir'],
        CommonOpt['crop_size'],
        CommonOpt['noise_std'],
        'val',
    )
    val_loader = DataLoader(
        val_set,
        batch_size=1,
        shuffle=False,
        pin_memory=True,
    )

    # ===== 加载断点 =====
    start_epoch = 0

    ckp_files = [
        f for f in os.listdir(ckp_dir)
        if f.startswith('epoch_') and f.endswith('.pth')
    ]
    epoch_numbers = []
    for file in ckp_files:
        try:
            # epoch_199.pth -> 199
            epoch_str = file.split('epoch_')[1].split('.pth')[0]
            epoch_numbers.append(int(epoch_str))
        except (IndexError, ValueError):
            continue

    if epoch_numbers:
        max_epoch = max(epoch_numbers)
        ckp_path = os.path.join(ckp_dir, f'epoch_{max_epoch}.pth')
        if os.path.exists(ckp_path):
            checkpoint = torch.load(ckp_path, map_location='cuda')
            model.load_state_dict(checkpoint['model_state_dict'])
            optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
            start_epoch = max_epoch + 1   # 修复：从下一个 epoch 开始
            print(f'已加载检查点：epoch {max_epoch}，继续训练...')
        else:
            print('未找到检查点文件，从头开始训练...')
    else:
        print('无检查点文件，从头开始训练...')

    # ===== 早停参数 =====
    best_val_psnr = 0.0
    patience = 20                  # 项目统一 / DWSR 脚本一致
    counter = 0

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # ===== 训练循环 =====
    for epoch in range(start_epoch, EDSROpt['epochs']):
        model.train()
        epoch_loss = AverageMeter()

        with tqdm(
            total=(len(train_set) - len(train_set) % EDSROpt['batch_size']),
            ncols=80,
            desc='Training',
        ) as t:
            t.set_description(
                'Epoch: {}/{}'.format(epoch + 1, EDSROpt['epochs'])
            )

            for data in train_loader:
                lr, hr = data
                lr = lr.cuda(non_blocking=True)
                hr = hr.cuda(non_blocking=True)

                # 前向
                predict = model(lr)
                loss = criterion(predict, hr)

                # 记录损失
                epoch_loss.update(torch.mean(loss))

                # 反向传播
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                t.set_postfix(loss='{:.4f}'.format(epoch_loss.avg))
                t.update(len(lr))

        tb.add_scalar('Loss', epoch_loss.avg, global_step=epoch)

        # 学习率衰减
        scheduler.step()

        # ===== 保存断点 =====
        ckp_path = os.path.join(ckp_dir, f'epoch_{epoch}.pth')
        torch.save({
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'scheduler_state_dict': scheduler.state_dict(),
        }, ckp_path)

        # ===== 验证 =====
        if epoch == 0 or (epoch + 1) % EDSROpt['val_every'] == 0:
            model.eval()

            epoch_psnr = AverageMeter()
            epoch_ssim = AverageMeter()
            epoch_lpips = AverageMeter()

            for data in tqdm(val_loader, ncols=80, desc='Validation'):
                # DIVKDataset 的 val 返回 5 元组
                lr, hr, cb_lr, cr_lr, filename = data

                lr = lr.to(device)
                hr = hr.to(device)

                # Y 通道通过模型
                with torch.no_grad():
                    predict = model(lr).detach().cpu().clamp(0, 1)

                # squeeze 成单通道 H×W
                predict = predict.squeeze().squeeze()
                hr = hr.squeeze().squeeze()

                # ===== 指标：只在 Y 通道上计算 =====
                epoch_psnr.update(calc_psnr_torch(predict, hr.cpu()))
                epoch_ssim.update(calc_ssim_torch(predict, hr.cpu()))
                epoch_lpips.update(calc_lpips(predict, hr.cpu()))

                # ===== 保存彩色推断结果 =====
                # Y 通道预测结果，转 uint8
                predict_y = np.array(predict.numpy() * 255, dtype=np.uint8)

                # Cb/Cr 是 LR 尺寸，直接双三次上采样到 HR 尺寸。
                # 注意：PIL Image.size = (W, H)，Resize 参数是 (H, W)。
                cb_lr_img = Image.fromarray(
                    np.array(cb_lr.numpy().squeeze().squeeze() * 255, dtype=np.uint8)
                )
                cr_lr_img = Image.fromarray(
                    np.array(cr_lr.numpy().squeeze().squeeze() * 255, dtype=np.uint8)
                )

                predict_cb = np.array(
                    transforms.Resize(
                        (cb_lr_img.size[1] * 4, cb_lr_img.size[0] * 4),
                        interpolation=Image.BICUBIC,
                    )(cb_lr_img)
                )
                predict_cr = np.array(
                    transforms.Resize(
                        (cr_lr_img.size[1] * 4, cr_lr_img.size[0] * 4),
                        interpolation=Image.BICUBIC,
                    )(cr_lr_img)
                )

                # 融合 YCbCr -> RGB
                # np.array((Y, Cb, Cr)) 形状为 (3, H, W)，转成 (H, W, 3)
                predict_np = np.array(
                    (predict_y, predict_cb, predict_cr)
                ).transpose(1, 2, 0)

                predict_rgb = Image.fromarray(
                    predict_np, mode='YCbCr'
                ).convert('RGB')
                predict_rgb.save(
                    os.path.join(val_infer_dir, '{}_rgb.png'.format(filename[0]))
                )

                # 保存单通道 Y 图
                Image.fromarray(predict_y, mode='L').save(
                    os.path.join(val_infer_dir, '{}_y.png'.format(filename[0]))
                )

                # 保存 LR 输入图
                noisy_y = Image.fromarray(
                    np.array(
                        lr.detach().cpu().numpy().squeeze().squeeze() * 255,
                        dtype=np.uint8,
                    ),
                    mode='L',
                )
                noisy_y.save(
                    os.path.join(val_infer_dir, '{}_lr.png'.format(filename[0]))
                )

            # ===== 打印验证指标 =====
            print('Val PSNR:  {:.2f}'.format(epoch_psnr.avg))
            print('Val SSIM:  {:.4f}'.format(epoch_ssim.avg))
            print('Val LPIPS: {:.4f}'.format(epoch_lpips.avg))

            tb.add_scalar('Val PSNR',  epoch_psnr.avg,  global_step=epoch)
            tb.add_scalar('Val SSIM',  epoch_ssim.avg,  global_step=epoch)
            tb.add_scalar('Val LPIPS', epoch_lpips.avg, global_step=epoch)

            # ===== 最佳模型与早停 =====
            if epoch_psnr.avg > best_val_psnr:
                best_val_psnr = epoch_psnr.avg
                counter = 0

                best_ckp_path = os.path.join(ckp_dir, 'best_model.pth')
                torch.save({
                    'epoch': epoch,
                    'model_state_dict': model.state_dict(),
                    'optimizer_state_dict': optimizer.state_dict(),
                    'scheduler_state_dict': scheduler.state_dict(),
                    'best_psnr': best_val_psnr,
                }, best_ckp_path)
                print(f'🏆 新最佳 PSNR: {best_val_psnr:.2f} dB')
            else:
                counter += 1
                if counter >= patience:
                    print('Training stopped early at epoch')
                    print(f'{epoch} | Best PSNR: {best_val_psnr:.2f} dB')
                    break
