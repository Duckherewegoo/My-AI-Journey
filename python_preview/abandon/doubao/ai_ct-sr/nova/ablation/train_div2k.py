'''
    LU-MWCNN 训练代码。（消融实验，DIV2K Y 通道）
'''
from lpips import LPIPS
import os
import sys
import os.path as path
from tqdm import tqdm
import torch
import torch.nn as nn
import importlib
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.utils.data import DataLoader
from torch.utils.tensorboard.writer import SummaryWriter

from base.utils.metrics import calc_psnr_torch, calc_ssim_torch
from base.utils.meters import AverageMeter
from model import LUMWCNN_ABTEST

dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__))                    # current directory first
sys.path.append(path.join(dirname__, '../../baselines'))


# ===================== 超参 =====================
LR = 1e-4
EPOCH = 500
BATCH_SIZE = 16
VAL_EVERY = 5

OUTPUT_PATH = r'/home/dake/Documents/Projects/Graduation_Projects/codes/nova/ablation/output_div2k'
MainDir = r'/home/dake/Documents/Projects/'

CommonOpt = {
    # 数据集
    'train_dir': path.join(MainDir, 'datasets/DIV2K_HR/train'),
    'val_dir':   path.join(MainDir, 'datasets/DIV2K_HR/val'),
    'dataset_interface': 'div2k.DIVKDataset',

    # 数据预处理
    'crop_size': 128,
    'noise_std': 0.01,

    # 数据加载
    'num_workers': 4,

    # 结果输出
    'output_path': path.join(MainDir, 'nova/ablation/output_div2k/'),
}

os.makedirs(OUTPUT_PATH, exist_ok=True)
tb = SummaryWriter(os.path.join(OUTPUT_PATH, './tensorboard'))


# ===================== 联合损失 =====================
class MyJointLoss(nn.Module):
    def __init__(self, lpips_weight=0.1):
        super(MyJointLoss, self).__init__()
        print('\nLoading VGG LPIPS for joint loss...\n')
        self.lpips = LPIPS(net='vgg').cuda()
        self.mse = nn.MSELoss()
        self.lpips_weight = lpips_weight

        # 上采样模块：两次 Conv + PixelShuffle(2) → 4× 放大
        self.upsample_block = nn.Sequential(
            nn.Conv2d(in_channels=1, out_channels=4, kernel_size=3, padding=1),
            nn.PixelShuffle(upscale_factor=2),
            nn.Conv2d(in_channels=1, out_channels=4, kernel_size=3, padding=1),
            nn.PixelShuffle(upscale_factor=2),
        ).cuda()

    def forward(self, x, y):
        x_upsampled = self.upsample_block(x)

        def normalize(tensor):
            return (tensor.clamp(0, 1) - 0.5) * 2      # [0,1] → [-1,1]

        return torch.mean(
            self.mse(x_upsampled, y) +
            self.lpips_weight * self.lpips(normalize(x_upsampled), normalize(y))
        )


# ===================== 训练入口 =====================
if __name__ == '__main__':
    # 模型
    model = LUMWCNN_ABTEST()
    model = model.cuda()

    # Adam
    criterion = MyJointLoss(lpips_weight=0.1)
    optimizer = optim.Adam(
        model.parameters(),
        lr=LR,
        weight_decay=1e-4,
        betas=(0.9, 0.999),
        eps=1e-8,
    )
    # 每 50 epoch 学习率减半
    scheduler = lr_scheduler.MultiStepLR(
        optimizer,
        list(range(50, EPOCH, 50)),
        gamma=0.5,
    )

    # ===== 加载数据集 =====
    print('Current dataset_interface: ', CommonOpt['dataset_interface'])
    Dataset_ = importlib.import_module(
        '.' + CommonOpt['dataset_interface'].split('.')[0], 'base.datasets')
    Dataset_ = eval('Dataset_.{}'.format(
        CommonOpt['dataset_interface'].split('.')[1]))

    train_set = Dataset_(
        CommonOpt['train_dir'], CommonOpt['crop_size'],
        CommonOpt['noise_std'], 'train')
    train_loader = DataLoader(
        train_set,
        batch_size=BATCH_SIZE,
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

    # ===== 加载断点 =====
    start_epoch = 0
    ckp_dir = os.path.join(CommonOpt['output_path'], 'ckp/')
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

    # ===== 训练 =====
    for epoch in range(start_epoch, EPOCH):
        model.train()
        epoch_loss = AverageMeter()

        with tqdm(total=(len(train_set) - len(train_set) % BATCH_SIZE),
                  ncols=80, desc='Training') as t:
            t.set_description(f'Epoch: {epoch + 1}/{EPOCH}')

            for data in train_loader:
                lr, hr = data
                lr = lr.cuda(non_blocking=True)
                hr = hr.cuda(non_blocking=True)

                predict = model(lr)
                loss = criterion(predict, hr)

                epoch_loss.update(loss.item())

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                t.set_postfix(loss='{:.4f}'.format(epoch_loss.avg))
                t.update(len(lr))

        tb.add_scalar('Loss', epoch_loss.avg, global_step=epoch)
        scheduler.step()

        # 保存断点
        ckp_path = path.join(ckp_dir, f'epoch_{epoch}.pth')
        torch.save({
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'scheduler_state_dict': scheduler.state_dict(),
        }, ckp_path)

        print(f'[Epoch {epoch + 1}] Loss: {epoch_loss.avg:.6f}')
