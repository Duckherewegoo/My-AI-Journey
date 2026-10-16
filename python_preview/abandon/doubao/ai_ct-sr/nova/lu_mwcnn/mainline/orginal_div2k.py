'''
    LU-MWCNN 训练代码 @ DIVK。
'''

 准备引入
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
from torch.utils.data import DataLoader
from model import LUMWCNN
from torch.utils.tensorboard import SummaryWriter
import sys
import os.path as path

dirname__ = path.dirname(path.abspath(__file__))

sys.path.append(path.join(dirname__))   current directory first
sys.path.append(path.join(dirname__, '../../baselines'))

LR = e-
EPOCH = 
BATCH_SIZE = 
VAL_EVERY = 
OUTPUT_PATH = r'/mnt/zhuoxu/code/graduation-project/nova/lu-mwcnn/output_divk'

CommonOpt = {
     数据集
    'train_dir': r'/mnt/zhuoxu/datasets/DIVK_HR/train/',
    'val_dir': r'/mnt/zhuoxu/datasets/DIVK_HR/val/',
    'dataset_interface': 'divk.DIVKDataset',

     数据预处理
    'crop_size': ,
    'noise_std': .,

     数据加载
    'num_workers': ,
}


tb = SummaryWriter(os.path.join(OUTPUT_PATH, './tensorboard'))


class MyJointLoss(nn.Module):
    def __init__(self, lpips_weight=.):
        super(MyJointLoss, self).__init__()
        print('\nLoading VGG LPIPS for joint loss...\n')
        self.lpips = LPIPS(net='vgg').cuda()
        self.mse = nn.MSELoss()
        self.lpips_weight = lpips_weight

    def forward(self, x, y):
        def normalize(tensor):   normalize to [-, ]
            return (tensor.clamp(, ) - .)  

        return torch.mean(self.mse(x, y) + self.lpips_weight  self.lpips(normalize(x), normalize(y)))


if __name__ == '__main__':
    model = LUMWCNN()
    model = model.cuda()

     Adam optimizer
    criterion = MyJointLoss()
    optimizer = optim.Adam(model.parameters(), lr=LR, weight_decay=e-, betas=(., .), eps=e-)
     learning rate decays by x. every  epochs
    scheduler = lr_scheduler.MultiStepLR(optimizer, list(range(, EPOCH, )), gamma=.)

     加载数据集
    print('Current dataset_interface: ', CommonOpt['dataset_interface'])
    Dataset_ = importlib.import_module('.' + CommonOpt['dataset_interface'].split('.')[], 'datasets')
    Dataset_ = eval('Dataset_.{}'.format(CommonOpt['dataset_interface'].split('.')[]))
    train_set = Dataset_(CommonOpt['train_dir'], CommonOpt['crop_size'], CommonOpt['noise_std'], 'train')
    train_loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True, num_workers=CommonOpt['num_workers'])
    val_set = Dataset_(CommonOpt['val_dir'], CommonOpt['crop_size'], CommonOpt['noise_std'], 'val')
    val_loader = DataLoader(val_set, batch_size=, shuffle=False, pin_memory=True)

     训练
    for epoch in range(EPOCH):
        model.train()
        epoch_loss = AverageMeter()

        with tqdm(total=(len(train_set) - len(train_set) % BATCH_SIZE), ncols=, desc='Training') as t:
            t.set_description('Epoch: {}/{}'.format(epoch + , EPOCH))

             训练过程
            for data in train_loader:
                lr, hr = data
                lr = lr.cuda()
                hr = hr.cuda()

                 通过网络，获得输出
                predict = model(lr).cuda()
                loss = criterion(predict, hr)

                 更新损失记录
                epoch_loss.update(torch.mean(loss))

                 反向传播并优化
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                t.set_postfix(loss='{:.f}'.format(epoch_loss.avg))
                t.update(len(lr))

            tb.add_scalar('Loss', epoch_loss.avg, global_step=epoch)

             衰减学习率
            scheduler.step()

             保存ckp
            torch.save(model.state_dict(), os.path.join(OUTPUT_PATH, './ckp/', 'epoch_{}.pth'.format(epoch)))

             验证
            if epoch ==  or (epoch + ) % VAL_EVERY == :
                model.eval()
                model.valing = True

                 PSNR / SSIM 和 LPIPS 均只在 Y 通道上计算
                epoch_psnr = AverageMeter()
                epoch_ssim = AverageMeter()
                epoch_lpips = AverageMeter()

                for data in tqdm(val_loader, ncols=, desc='Validation'):
                    lr, hr, cb_lr, cr_lr, filename = data
                    lr = lr.cuda()
                    hr = hr.cuda()

                     Y 通道通过模型
                    with torch.no_grad():
                        predict = model(lr).detach().cpu().clamp(, )

                     squeeze BatchSize and Channel dimensions, become -ch Y-ch
                    predict = predict.squeeze().squeeze()
                    hr = hr.squeeze().squeeze()

                     更新 PSNR / SSIM 和 LPIPS 记录
                    epoch_psnr.update(calc_psnr_torch(predict, hr.cpu()))
                    epoch_ssim.update(calc_ssim_torch(predict, hr.cpu()))
                    epoch_lpips.update(calc_lpips(predict, hr.cpu()))

                     保存最新推断结果
                     Y 通道
                    predict_y = np.array(predict.numpy()  , dtype=np.uint)
                     Cb、Cr直接插值
                    cb_lr = Image.fromarray(np.array(cb_lr.numpy().squeeze().squeeze()  , dtype=np.uint))
                    cr_lr = Image.fromarray(np.array(cr_lr.numpy().squeeze().squeeze()  , dtype=np.uint))
                    predict_cb = np.array(
                        transforms.Resize((cb_lr.size[]  , cb_lr.size[]  ), interpolation=Image.BICUBIC)(cb_lr))
                    predict_cr = np.array(
                        transforms.Resize((cr_lr.size[]  , cr_lr.size[]  ), interpolation=Image.BICUBIC)(cr_lr))
                     融合多通道图并保存
                    predict_np = np.array((predict_y, predict_cb, predict_cr)).transpose(, , )   CHW To HWC
                    predict_rgb = Image.fromarray(predict_np, mode='YCbCr').convert('RGB')
                    predict_rgb.save(os.path.join(OUTPUT_PATH, './val_inference/', '{}_rgb.png'.format(filename[])))
                     保存单通道图
                    predict_y = Image.fromarray(predict_y, mode='L')
                    predict_y.save(os.path.join(OUTPUT_PATH, './val_inference/', '{}_y.png'.format(filename[])))
                     保存输入的图片
                    noisy_y = Image.fromarray(np.array(lr.detach().cpu().numpy().squeeze().squeeze()  ,
                                                       dtype=np.uint),
                                              mode='L')
                    noisy_y.save(os.path.join(OUTPUT_PATH, './val_inference/', '{}_lr.png'.format(filename[])))

                 打印当前指标结果
                print('Val PSNR: {:.f}'.format(epoch_psnr.avg))
                print('Val SSIM: {:.f}'.format(epoch_ssim.avg))
                print('Val LPIPS: {:.f}'.format(epoch_lpips.avg))

                 保存相关指标到 TensorBoard
                tb.add_scalar('Val PSNR', epoch_psnr.avg, global_step=epoch)
                tb.add_scalar('Val SSIM', epoch_ssim.avg, global_step=epoch)
                tb.add_scalar('Val LPIPS', epoch_lpips.avg, global_step=epoch)
