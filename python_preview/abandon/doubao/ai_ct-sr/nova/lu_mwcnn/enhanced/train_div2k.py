'''
    LU-MWCNN 训练代码 @ DIVK (优化版，带断点续传)
'''

 导入必要的库
import matplotlib.pyplot as plt
from lpips import LPIPS
import os
import argparse
from tqdm import tqdm
import torch
import torch.nn as nn
import torchvision.transforms as transforms
import numpy as np
from PIL import Image
import importlib
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter
import os.path as path
import sys
from base.utils.metrics import calc_psnr_torch, calc_ssim_torch
from base.utils.lpips import calc_lpips
from base.utils.meters import AverageMeter
from model import LUMWCNN

 设置中文字体支持
import matplotlib
matplotlib.use('Agg')
plt.rcParams["font.family"] = ["SimHei", "WenQuanYi Micro Hei", "Heiti TC"]

 配置参数


def get_args():
    parser = argparse.ArgumentParser(description='LU-MWCNN 训练脚本')
    parser.add_argument('--lr', type=float, default=e-, help='初始学习率')
    parser.add_argument('--epochs', type=int, default=, help='训练轮数')
    parser.add_argument('--batch_size', type=int, default=, help='批次大小')
    parser.add_argument('--val_every', type=int, default=, help='每多少轮验证一次')
    parser.add_argument('--output_path', type=str,
                        default='./output_divk', help='输出路径')
    parser.add_argument('--resume', type=str, default=None,
                        help='从指定checkpoint恢复训练')
    parser.add_argument('--num_workers', type=int, default=, help='数据加载线程数')
    parser.add_argument('--crop_size', type=int, default=, help='裁剪大小')
    parser.add_argument('--noise_std', type=float, default=., help='噪声标准差')
    parser.add_argument('--lpips_weight', type=float,
                        default=., help='LPIPS损失权重')
    return parser.parse_args()

 联合损失函数


class MyJointLoss(nn.Module):
    def __init__(self, lpips_weight=.):
        super(MyJointLoss, self).__init__()
        print('\n加载 VGG LPIPS 用于联合损失计算...\n')
        self.lpips = LPIPS(net='vgg').to(device)
        self.mse = nn.MSELoss()
        self.lpips_weight = lpips_weight

    def forward(self, x, y):
        def normalize(tensor):   归一化到 [-, ]
            return (tensor.clamp(, ) - .)  

        return torch.mean(self.mse(x, y) + self.lpips_weight  self.lpips(normalize(x), normalize(y)))

 寻找最新的checkpoint


def find_latest_checkpoint(ckp_dir):
    if not os.path.exists(ckp_dir):
        return None

    checkpoints = [f for f in os.listdir(
        ckp_dir) if f.startswith('epoch_') and f.endswith('.pth')]
    if not checkpoints:
        return None

     提取epoch编号并排序
    checkpoints.sort(key=lambda x: int(
        x.split('_')[].split('.')[]), reverse=True)
    return os.path.join(ckp_dir, checkpoints[])

 主函数


def main():
    global device
     设备配置
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'使用设备: {device}')

     解析参数
    args = get_args()

     创建输出目录
    OUTPUT_PATH = os.path.join('./output_divk/')
    os.makedirs(OUTPUT_PATH, exist_ok=True)
    ckp_dir = os.path.join(OUTPUT_PATH, 'ckp')
    val_inference_dir = os.path.join(OUTPUT_PATH, 'val_inference')
    os.makedirs(ckp_dir, exist_ok=True)
    os.makedirs(val_inference_dir, exist_ok=True)

     TensorBoard配置
    tb = SummaryWriter(os.path.join(OUTPUT_PATH, 'tensorboard'))

     数据集配置
    MainDir = "/home/dake/Documents/Projects/"
    CommonOpt = {
        'train_dir': path.join(MainDir, 'datasets/DIVK_HR/train/'),
        'val_dir': path.join(MainDir, 'datasets/DIVK_HR/val/'),
        'dataset_interface': 'divk.DIVKDataset',
        'crop_size': args.crop_size,
        'noise_std': args.noise_std,
        'num_workers': args.num_workers,
        'output_path': OUTPUT_PATH
    }

     检查数据集路径
    if not os.path.exists(CommonOpt['train_dir']):
        print(f"错误: 训练数据集路径不存在 - {CommonOpt['train_dir']}")
        return

    if not os.path.exists(CommonOpt['val_dir']):
        print(f"错误: 验证数据集路径不存在 - {CommonOpt['val_dir']}")
        return

     初始化模型
    model = LUMWCNN().to(device)

     损失函数和优化器
    criterion = MyJointLoss(lpips_weight=args.lpips_weight)
    optimizer = optim.Adam(model.parameters(), lr=args.lr,
                           weight_decay=e-, betas=(., .), eps=e-)
    scheduler = lr_scheduler.MultiStepLR(
        optimizer, list(range(, args.epochs, )), gamma=.)

     断点续传
    start_epoch = 
    resume_path = args.resume if args.resume else find_latest_checkpoint(
        ckp_dir)

    if resume_path and os.path.exists(resume_path):
        print(f'从 checkpoint 恢复训练: {resume_path}')
        checkpoint = torch.load(resume_path, map_location=device)
        model.load_state_dict(checkpoint['model_state_dict'])
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
        start_epoch = checkpoint['epoch'] +    从下一个epoch开始
        print(f'恢复成功，将从 epoch {start_epoch} 开始训练')

     加载数据集
    print(f'当前数据集接口: {CommonOpt["dataset_interface"]}')
    try:
        dataset_module = importlib.import_module(
            '.' + CommonOpt['dataset_interface'].split('.')[], 'base.datasets')
        DatasetClass = eval(
            f'dataset_module.{CommonOpt["dataset_interface"].split(".")[]}')
    except Exception as e:
        print(f'加载数据集失败: {e}')
        return

     训练集
    train_set = DatasetClass(
        CommonOpt['train_dir'], CommonOpt['crop_size'], CommonOpt['noise_std'], 'train')
    train_loader = DataLoader(train_set, batch_size=args.batch_size,
                              shuffle=True, num_workers=CommonOpt['num_workers'],
                              pin_memory=True)

     验证集
    val_set = DatasetClass(
        CommonOpt['val_dir'], CommonOpt['crop_size'], CommonOpt['noise_std'], 'val')
    val_loader = DataLoader(val_set, batch_size=,
                            shuffle=False, pin_memory=True)

    print(f'训练集大小: {len(train_set)}, 验证集大小: {len(val_set)}')
     在训练循环外初始化早停参数

    best_val_psnr = .

    patience =    连续个epoch验证性能未提升则停止

    counter =     未提升计数器

     开始训练
    print(f'开始训练，共 {args.epochs} 轮，从第 {start_epoch} 轮开始')
    for epoch in range(start_epoch, args.epochs):
        model.train()
        epoch_loss = AverageMeter()

        with tqdm(total=(len(train_set) - len(train_set) % args.batch_size),
                  ncols=, desc='训练进度') as t:
            t.set_description(f'Epoch: {epoch + }/{args.epochs}')

            for data in train_loader:
                lr, hr = data
                lr = lr.to(device)
                hr = hr.to(device)

                 模型前向传播
                predict = model(lr)
                loss = criterion(predict, hr)

                 更新损失记录
                epoch_loss.update(torch.mean(loss).item())

                 反向传播和优化
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                t.set_postfix(loss=f'{epoch_loss.avg:.f}')
                t.update(len(lr))

             记录损失到TensorBoard
            tb.add_scalar('训练损失', epoch_loss.avg, global_step=epoch)

         学习率调整
        scheduler.step()

         保存checkpoint
        checkpoint = {
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'scheduler_state_dict': scheduler.state_dict()
        }
        torch.save(checkpoint, os.path.join(ckp_dir, f'epoch_{epoch}.pth'))

         定期删除旧的checkpoint，只保留最近个
        checkpoints = [f for f in os.listdir(
            ckp_dir) if f.startswith('epoch_') and f.endswith('.pth')]
        if len(checkpoints) > :
            checkpoints.sort(key=lambda x: int(x.split('_')[].split('.')[]))
            for old_ckp in checkpoints[:-]:
                os.remove(os.path.join(ckp_dir, old_ckp))

         验证
        if epoch ==  or (epoch + ) % args.val_every == :
            model.eval()

            epoch_psnr = AverageMeter()
            epoch_ssim = AverageMeter()
            epoch_lpips = AverageMeter()

            with torch.no_grad():
                for data in tqdm(val_loader, ncols=, desc='验证进度'):
                    lr, hr, cb_lr, cr_lr, filename = data
                    lr = lr.to(device)
                    hr = hr.to(device)

                     模型推理
                    predict = model(lr).detach().cpu().clamp(, )

                     处理输出格式
                    predict = predict.squeeze()
                    hr_cpu = hr.squeeze().cpu()

                     计算指标
                    epoch_psnr.update(calc_psnr_torch(predict, hr_cpu))
                    epoch_ssim.update(calc_ssim_torch(predict, hr_cpu))
                    epoch_lpips.update(calc_lpips(predict, hr_cpu))

                     保存结果
                    predict_y = np.array(predict.numpy()  , dtype=np.uint)

                     处理Cb、Cr通道
                    cb_lr_img = Image.fromarray(
                        np.array(cb_lr.numpy().squeeze()  , dtype=np.uint))
                    cr_lr_img = Image.fromarray(
                        np.array(cr_lr.numpy().squeeze()  , dtype=np.uint))

                     上采样Cb、Cr通道
                    predict_cb = np.array(transforms.Resize(
                        (cb_lr_img.size[]  , cb_lr_img.size[]  ),
                        interpolation=Image.BICUBIC)(cb_lr_img))
                    predict_cr = np.array(transforms.Resize(
                        (cr_lr_img.size[]  , cr_lr_img.size[]  ),
                        interpolation=Image.BICUBIC)(cr_lr_img))

                     合并通道并保存
                    predict_np = np.array(
                        (predict_y, predict_cb, predict_cr)).transpose(, , )
                    predict_rgb = Image.fromarray(
                        predict_np, mode='YCbCr').convert('RGB')
                    predict_rgb.save(os.path.join(
                        val_inference_dir, f'{filename[]}_rgb.png'))

                     保存Y通道结果
                    predict_y_img = Image.fromarray(predict_y, mode='L')
                    predict_y_img.save(os.path.join(
                        val_inference_dir, f'{filename[]}_y.png'))

                     保存输入图像
                    noisy_y_img = Image.fromarray(
                        np.array(lr.detach().cpu().numpy().squeeze()
                                  , dtype=np.uint),
                        mode='L')
                    noisy_y_img.save(os.path.join(
                        val_inference_dir, f'{filename[]}_lr.png'))

             打印验证结果
            print(f'验证结果 - Epoch {epoch + }:')
            print(f'PSNR: {epoch_psnr.avg:.f} dB')
            print(f'SSIM: {epoch_ssim.avg:.f}')
            print(f'LPIPS: {epoch_lpips.avg:.f}')

             记录到TensorBoard
            tb.add_scalar('验证PSNR', epoch_psnr.avg, global_step=epoch)
            tb.add_scalar('验证SSIM', epoch_ssim.avg, global_step=epoch)
            tb.add_scalar('验证LPIPS', epoch_lpips.avg, global_step=epoch)
             修改验证部分逻辑（在验证循环结束后）

            if epoch_psnr.avg > best_val_psnr:

                best_val_psnr = epoch_psnr.avg

                counter =    重置计数器

                 保存最佳模型

                best_ckp_path = os.path.join(ckp_dir, 'best_model.pth')

                torch.save({

                    'epoch': epoch,

                    'model_state_dict': model.state_dict(),

                    'optimizer_state_dict': optimizer.state_dict(),

                    'scheduler_state_dict': scheduler.state_dict(),

                    'best_psnr': best_val_psnr

                }, best_ckp_path)

            else:

                counter += 

                if counter >= patience:

                    print('Training stopped early at epoch')
                    print(f'{epoch} | Best PSNR: {best_val_psnr:.f}dB')

                    break   终止训练循环

             在训练循环的break后添加清理代码

            print('Training stopped at epoch')
            print(f'{epoch}. Best validation PSNR: {best_val_psnr:.f}dB')

    print('训练完成!')
    tb.close()


if __name__ == '__main__':
    main()
