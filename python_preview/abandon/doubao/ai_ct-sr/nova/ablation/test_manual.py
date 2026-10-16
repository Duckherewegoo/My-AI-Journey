'''
    LU-MWCNN 消融实验测试脚本（DIV2K val 集评估）
'''
import os
import os.path as path
import sys
import importlib

import torch
import torch.nn.functional as F
import numpy as np
from PIL import Image
from tqdm import tqdm

from torch.utils.tensorboard import SummaryWriter
from torch.utils.data import DataLoader
from lpips import LPIPS

# ===== 路径 =====
dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__))
sys.path.append(path.join(dirname__, '../../baselines'))

# ===== 超参 =====
CROP_SIZE = 128
NOISE_STD = 0.01
NUM_WORKERS = 4
SCALE = 4

OUTPUT_PATH = r'/mnt/zhuoxu/code/graduation-project/nova/ablation/output_div2k'

CommonOpt = {
    'train_dir': r'/mnt/zhuoxu/datasets/DIV2K_HR/train/',
    'val_dir':   r'/mnt/zhuoxu/datasets/DIV2K_HR/val/',
    'dataset_interface': 'div2k.DIVKDataset',
    'crop_size': CROP_SIZE,
    'noise_std': NOISE_STD,
    'num_workers': NUM_WORKERS,
}

# ===== 项目模块 =====
from model_cpu import LUMWCNN_ABTEST
from utils.meters import AverageMeter
from utils.metrics import calc_psnr_torch, calc_ssim_torch

# ===== LPIPS（CPU） =====
lpips = LPIPS(net='vgg')
lpips = lpips.to('cpu')
lpips.eval()


def calc_lpips(img1, img2):
    """LPIPS 距离（要求输入在 [-1, 1]）"""
    return lpips(img1, img2).detach().cpu().squeeze().mean()


# ===== TensorBoard =====
tb = SummaryWriter(os.path.join(OUTPUT_PATH, './tensorboard'))


# ===== 权重路径（改成你要测的 ckp） =====
CKP_PATH = os.path.join(
    OUTPUT_PATH, 'ckp/epoch_299.pth')


if __name__ == '__main__':
    # 输出目录
    val_infer_dir = os.path.join(OUTPUT_PATH, 'val_inference')
    os.makedirs(val_infer_dir, exist_ok=True)

    with torch.no_grad():
        # ===== 模型 =====
        model = LUMWCNN_ABTEST()
        # model = model.cuda()          # CPU 版注释掉
        model.load_state_dict(
            torch.load(CKP_PATH, map_location='cpu'))

        # ===== 数据集 =====
        print('Current dataset_interface: ', CommonOpt['dataset_interface'])
        Dataset_ = importlib.import_module(
            '.' + CommonOpt['dataset_interface'].split('.')[0], 'datasets')
        Dataset_ = eval('Dataset_.{}'.format(
            CommonOpt['dataset_interface'].split('.')[1]))

        val_set = Dataset_(
            CommonOpt['val_dir'], CommonOpt['crop_size'],
            CommonOpt['noise_std'], 'val')
        val_loader = DataLoader(
            val_set, batch_size=1, shuffle=False, pin_memory=False)

        # ===== 测试 =====
        model.eval()
        model.valing = True

        epoch_psnr = AverageMeter()
        epoch_ssim = AverageMeter()
        epoch_lpips = AverageMeter()

        for data in tqdm(val_loader, ncols=80, desc='Validation'):
            lr, hr, cb_lr, cr_lr, filename = data
            # lr = lr.cuda()
            # hr = hr.cuda()

            # ===== Y 通道通过模型 =====
            predict = model(lr).detach().cpu().clamp(0, 1)

            # ⚠️ 关键修正：上采样到 HR 尺寸（原代码缺失）
            predict = F.interpolate(
                predict, size=hr.shape[-2:],
                mode='bicubic', align_corners=False)

            predict = predict.squeeze().squeeze()
            hr = hr.squeeze().squeeze()

            # ===== 更新指标 =====
            epoch_psnr.update(calc_psnr_torch(predict, hr.cpu()))
            epoch_ssim.update(calc_ssim_torch(predict, hr.cpu()))

            # LPIPS 要求 [-1, 1]
            predict_lpips = predict.unsqueeze(0).unsqueeze(0) * 2 - 1
            hr_lpips = hr.cpu().unsqueeze(0).unsqueeze(0) * 2 - 1
            epoch_lpips.update(calc_lpips(predict_lpips, hr_lpips))

            # ===== 保存结果 =====
            # Y 通道
            predict_y = np.array(predict.numpy() * 255, dtype=np.uint8)
            # Cb/Cr 直接插值到 HR 尺寸
            cb_lr_up = F.interpolate(
                cb_lr, size=hr.shape, mode='bicubic',
                align_corners=False).squeeze().numpy()
            cr_lr_up = F.interpolate(
                cr_lr, size=hr.shape, mode='bicubic',
                align_corners=False).squeeze().numpy()
            cb_lr_np = np.array(cb_lr_up * 255, dtype=np.uint8)
            cr_lr_np = np.array(cr_lr_up * 255, dtype=np.uint8)

            # CHW → HWC
            predict_np = np.stack(
                [predict_y, cb_lr_np, cr_lr_np], axis=-1)
            predict_rgb = Image.fromarray(
                predict_np, mode='YCbCr').convert('RGB')
            predict_rgb.save(os.path.join(
                val_infer_dir, '{}_rgb.png'.format(filename[0])))

            # 单通道 Y
            predict_y_img = Image.fromarray(predict_y, mode='L')
            predict_y_img.save(os.path.join(
                val_infer_dir, '{}_y.png'.format(filename[0])))

            # 输入 LR
            noisy_y = Image.fromarray(
                np.array(lr.detach().cpu().numpy().squeeze().squeeze() * 255,
                         dtype=np.uint8),
                mode='L')
            noisy_y.save(os.path.join(
                val_infer_dir, '{}_lr.png'.format(filename[0])))

        # ===== 打印指标 =====
        print('Val PSNR:  {:.2f}'.format(epoch_psnr.avg))
        print('Val SSIM:  {:.4f}'.format(epoch_ssim.avg))
        print('Val LPIPS: {:.4f}'.format(epoch_lpips.avg))

        tb.add_scalar('Val PSNR',  epoch_psnr.avg,  global_step=0)
        tb.add_scalar('Val SSIM',  epoch_ssim.avg,  global_step=0)
        tb.add_scalar('Val LPIPS', epoch_lpips.avg, global_step=0)
