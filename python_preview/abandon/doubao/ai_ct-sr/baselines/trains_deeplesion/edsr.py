'''
    EDSR 在 DeepLesion 上的训练代码。（3060 8GB 适配）
'''
import os
import sys
import os.path as path
from tqdm import tqdm
import torch
import torch.nn as nn
import numpy as np
from PIL import Image
import importlib
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.utils.data import DataLoader
from torch.utils.tensorboard.writer import SummaryWriter

from base.utils.metrics import calc_psnr_torch, calc_ssim_torch
from base.utils.meters import AverageMeter
from base.models.edsr import EDSR

dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__, '../'))


EDSROpt = {
    # 模型
    'resblock_channels': 64,
    'resblock_depth': 16,
    # 训练
    'lr': 1e-4,
    'epochs': 500,
    'batch_size': 8,           # ← 3060 8GB 专用（EDSR 吃显存）
    # 验证
    'val_every': 5,
}

MainDir = r'../../nova/'
IODir = r'../'

CommonOpt = {
    # 数据集
    'train_dir': os.path.join(MainDir, 'datasets/DeepLesion_Key_slices/train/HR'),
    'val_dir':   os.path.join(MainDir, 'datasets/DeepLesion_Key_slices/val/HR'),
    'dataset_interface': 'deeplesion.DeepLesionDataset',

    # 数据预处理
    'crop_size': 128,
    'noise_std': 0.01,

    # 数据加载
    'num_workers': 4,

    # 结果输出
    'output_path': os.path.join(IODir, 'baselines/outputs_deeplesion'),
}

tb = SummaryWriter(os.path.join(CommonOpt['output_path'], 'edsr/tensorboard'))


if __name__ == '__main__':
    # 创建输出目录
    val_infer_dir = os.path.join(CommonOpt['output_path'], 'edsr/val_inference')
    os.makedirs(val_infer_dir, exist_ok=True)

    # 模型
    model = EDSR(
        EDSROpt['resblock_channels'],
        EDSROpt['resblock_depth'],
    )
    model = model.cuda()

    # MSELoss + Adam
    criterion = nn.MSELoss()
    optimizer = optim.Adam(
        model.parameters(),
        lr=EDSROpt['lr'],
        weight_decay=1e-4,
        betas=(0.9, 0.999),
        eps=1e-8,
    )
    # EDSR 官方：每 200 epoch 学习率减半
    # https://github.com/sanghyun-son/EDSR-PyTorch/blob/master/src/option.py
    scheduler = lr_scheduler.MultiStepLR(
        optimizer,
        list(range(200, EDSROpt['epochs'], 200)),
        gamma=0.5,
    )

    # 加载数据集
    Dataset_ = importlib.import_module(
        '.' + CommonOpt['dataset_interface'].split('.')[0], 'base.datasets')
    Dataset_ = eval('Dataset_.{}'.format(
        CommonOpt['dataset_interface'].split('.')[1]))

    train_set = Dataset_(
        CommonOpt['train_dir'], CommonOpt['crop_size'],
        CommonOpt['noise_std'], 'train')
    train_loader = DataLoader(
        train_set,
        batch_size=EDSROpt['batch_size'],
        shuffle=True,
        num_workers=CommonOpt['num_workers'],
        pin_memory=True,
        drop_last=True,
    )
    val_set = Dataset_(
        CommonOpt['val_dir'], CommonOpt['crop_size'],
        CommonOpt['noise_std'], 'val')
    val_loader = DataLoader(
        val_set, batch_size=1, shuffle=False, pin_memory=True)

    # ========== 加载断点 ==========
    start_epoch = 0
    ckp_dir = os.path.join(CommonOpt['output_path'], 'edsr/edckp')
    os.makedirs(ckp_dir, exist_ok=True)

    ckp_files = [f for f in os.listdir(ckp_dir)
                 if f.startswith('epoch_') and f.endswith('.pth')]
    epoch_numbers = []
    for file in ckp_files:
        try:
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
            start_epoch = max_epoch
            print(f'已加载检查点：epoch {max_epoch}，继续训练...')
        else:
            print('未找到检查点文件，从头开始训练...')
    else:
        print('无检查点文件，从头开始训练...')

    # ========== 早停参数 ==========
    best_val_psnr = 0.0
    patience = 20
    counter = 0

    # ========== AMP（3060 必备） ==========
    scaler = torch.cuda.amp.GradScaler()

    # ========== 训练循环 ==========
    for epoch in range(start_epoch, EDSROpt['epochs']):
        model.train()
        epoch_loss = AverageMeter()

        with tqdm(total=(len(train_set) - len(train_set) % EDSROpt['batch_size']),
                  ncols=80, desc='Training') as t:
            t.set_description(f'Epoch: {epoch + 1}/{EDSROpt["epochs"]}')

            for data in train_loader:
                lr, hr = data
                lr = lr.cuda(non_blocking=True)
                hr = hr.cuda(non_blocking=True)

                optimizer.zero_grad()

                # AMP 前向 + 反向
                with torch.cuda.amp.autocast(dtype=torch.float16):
                    predict = model(lr)
                    loss = criterion(predict, hr)

                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()

                epoch_loss.update(torch.mean(loss))

                t.set_postfix(
                    loss='{:.4f}'.format(epoch_loss.avg),
                    mem='{:.2f}G'.format(torch.cuda.memory_allocated() / 1e9),
                )
                t.update(len(lr))

        tb.add_scalar('Loss', epoch_loss.avg, global_step=epoch)
        scheduler.step()

        # 保存断点
        ckp_path = os.path.join(ckp_dir, f'epoch_{epoch}.pth')
        torch.save({
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'scheduler_state_dict': scheduler.state_dict(),
        }, ckp_path)

        # ========== 验证 ==========
        if epoch == 0 or (epoch + 1) % EDSROpt['val_every'] == 0:
            model.eval()
            epoch_psnr = AverageMeter()
            epoch_ssim = AverageMeter()

            for data in tqdm(val_loader, ncols=80, desc='Validation'):
                lr, hr, filename = data
                lr = lr.cuda()
                hr = hr.cuda()

                with torch.no_grad(), torch.cuda.amp.autocast(dtype=torch.float16):
                    predict = model(lr)
                predict = predict.float().detach().cpu().clamp(0, 1)

                # 去掉 batch 和 channel 维
                predict = predict.squeeze().squeeze()
                hr = hr.squeeze().squeeze()

                epoch_psnr.update(calc_psnr_torch(predict, hr.cpu()))
                epoch_ssim.update(calc_ssim_torch(predict, hr.cpu()))

                # 保存推断结果
                predict_y = np.array(predict.numpy() * 255, dtype=np.uint8)
                Image.fromarray(predict_y, mode='L').convert('L').save(
                    os.path.join(val_infer_dir,
                                 '{}_gray.png'.format(filename[0])))

                noisy_y = Image.fromarray(
                    np.array(lr.detach().cpu().numpy().squeeze().squeeze() * 255,
                             dtype=np.uint8),
                    mode='L')
                noisy_y.save(os.path.join(
                    val_infer_dir, '{}_lr.png'.format(filename[0])))

            print('Val PSNR: {:.2f}'.format(epoch_psnr.avg))
            print('Val SSIM: {:.4f}'.format(epoch_ssim.avg))

            tb.add_scalar('Val PSNR', epoch_psnr.avg, global_step=epoch)
            tb.add_scalar('Val SSIM', epoch_ssim.avg, global_step=epoch)

            # 早停 + 最佳保存
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
