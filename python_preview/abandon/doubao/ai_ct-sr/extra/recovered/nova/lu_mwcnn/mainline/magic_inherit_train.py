# 反编译源文件: /home/dake/Documents/Projects/Graduction_Projects/codes/nova/lu_mwcnn/mainline/__pycache__/magic_inherit_train.cpython-311.pyc
# 生成时间: 2026-09-14 16:06:15.181696
# ============================================================================

# Source Generated with Decompyle++
# File: magic_inherit_train.cpython-311.pyc (Python 3.11)

import os
import sys
import time
import torch
from torch.nn import nn
from torch.optim import optim
from torch.utils.data import DataLoader, Subset
from torchvision import transforms
import numpy as np
from tqdm import tqdm
from PIL import Image
from os.path import path

functional
from torch.utils.tensorboard.writer import SummaryWriter
import torch.nn.functional, nn
import lpips
import warnings
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts, CosineAnnealingLR
from torchmetrics.image import StructuralSimilarityIndexMeasure
warnings.filterwarnings('ignore')
DEEPLESION_CKPT = './output_deeplesion/goat/best_luna16_ct_psnr_epoch_56.pth'
DIV2K_CKPT = './output_div2k/div2k_resume_ckpt/div2k_rgb_epoch_500.pth'
LUNA16_DATA_DIR = '/home/dake/Documents/Projects/datasets/LUNA16/sr_slice_dataset/'
VOC2012_DATA_DIR = '/home/dake/Documents/Projects/datasets/VOC2012/sr_split/'
COVID_DATA_DIR = '/home/dake/Documents/Projects/datasets/COVID-19CT/COVID19-CT-Images/'
DIV2K_DATA_DIR = '/home/dake/Documents/Projects/datasets/DIV2K_HR/'
DEEPLESION_DATA_DIR = '/home/dake/Documents/Projects/datasets/DeepLesion/deeplesion_category_split/lung/'
DEEPLESION_KEY_DATA_DIR = '/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/'
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
SCALE = 4
BATCH_SIZE = 4
LR = 5e-06
WEIGHT_DECAY = 0.0001
EPOCHS = 1000
FREEZE_BACKBONE_EPOCHS = 5
EARLY_STOPPING_PATIENCE = 30
EARLY_STOPPING_MIN_DELTA = 0.0001
NUM_WORKERS = 4
PREFETCH_FACTOR = 2
CHECKPOINT_DIR = './continual_ckpt'
OUTPUT_DETAIL_DIR = './output_detail'
TB_LOG_DIR = './tb_logs'
TEST_OUTPUT_DIR = './test_output'
os.makedirs(CHECKPOINT_DIR, exist_ok = True)
os.makedirs(OUTPUT_DETAIL_DIR, exist_ok = True)
os.makedirs(TB_LOG_DIR, exist_ok = True)
os.makedirs(TEST_OUTPUT_DIR, exist_ok = True)

class Logger:
    '''日志重定向类：同时输出到终端和文件'''
    
    def __init__(self, log_file):
        self.terminal = sys.stdout
        self.log = open(log_file, 'a', encoding = 'utf-8')
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



class EarlyStopping:
    '''早停机制：基于PSNR/SSIM/LPIPS多指标判断'''
    
    def __init__(self, patience, min_delta, verbose = (40, 0.0001, True)):
        self.patience = patience
        self.min_delta = min_delta
        self.verbose = verbose
        self.counter = 0
        self.best_psnr = -float('inf')
        self.best_ssim = -float('inf')
        self.best_lpips = float('inf')
        self.early_stop = False

    
    def reset_counter(self):
        '''重置早停计数器'''
        self.counter = 0
        if self.verbose:
            print('🔄 早停计数器已重置为0')
            return None

    
    def __call__(self, psnr, ssim, lpips):
        '''
        每轮训练后调用，判断是否触发早停
        Args:
            psnr: 当前轮PSNR值
            ssim: 当前轮SSIM值
            lpips: 当前轮LPIPS值
        Returns:
            bool: 是否触发早停
        '''
        psnr_improved = psnr > self.best_psnr + self.min_delta
        ssim_improved = ssim > self.best_ssim + self.min_delta
        lpips_improved = lpips < self.best_lpips - self.min_delta
        if not psnr_improved:
            if not ssim_improved:
                any_improved = lpips_improved
                if psnr_improved:
                    self.best_psnr = psnr
        if ssim_improved:
            self.best_ssim = ssim
        if lpips_improved:
            self.best_lpips = lpips
        if any_improved:
            self.counter = 0
        elif self.verbose:
            print(f'''⏱️ EarlyStopping counter: {self.counter}/{self.patience} | 最佳PSNR: {self.best_psnr:.2f} | 最佳SSIM: {self.best_ssim:.4f} | 最佳LPIPS: {self.best_lpips:.4f}''')
        if self.counter >= self.patience:
            True = self, self.counter += 1, .counter
            if self.verbose:
                print('⚠️ Early stopping triggered!（多指标均无有效提升）')
        return self.early_stop



class TBLogger:
    '''TensorBoard日志器：负责指标计算和日志写入（修复SSIM维度错误）'''
    
    def __init__(self, log_dir = (TB_LOG_DIR,)):
        self.log_dir = log_dir
        self.writers = { }
        self.lpips_model = lpips.LPIPS(net = 'vgg').eval().to(DEVICE)
        self.ssim_metric = StructuralSimilarityIndexMeasure(kernel_size = 11, sigma = 1.5, data_range = 1, k1 = 0.01, k2 = 0.03).to(DEVICE)

    
    def compute_ssim(self, preds, targets):
        '''计算SSIM，自动处理RGB和灰度图'''
        return self.ssim_metric(preds, targets)

    
    def get_writer(self, dataset_type):
        '''获取指定数据集的TensorBoard写入器'''
        if dataset_type not in self.writers:
            writer_dir = os.path.join(self.log_dir, dataset_type)
            self.writers[dataset_type] = SummaryWriter(log_dir = writer_dir)
            print(f'''📝 初始化TensorBoard日志器: {writer_dir}''')
        return self.writers[dataset_type]

    
    def calculate_metrics(self, sr_img, hr_img):
        '''
        计算超分图像的评估指标：PSNR/SSIM/LPIPS
        Args:
            sr_img: 超分图像 (B,C,H,W)
            hr_img: 高清原图 (B,C,H,W)
        Returns:
            tuple: (psnr, ssim, lpips)
        '''
        sr_img = sr_img.float().to(DEVICE)
        hr_img = hr_img.float().to(DEVICE)
        (B, C, H, W) = sr_img.shape
        if hr_img.shape[1] != C:
            if hr_img.shape[1] == 1 and C == 3:
                hr_img = hr_img.repeat(1, 3, 1, 1)
            elif hr_img.shape[1] == 3 and C == 1:
                hr_img = 0.299 * hr_img[(:, 0:1, :, :)] + 0.587 * hr_img[(:, 1:2, :, :)] + 0.114 * hr_img[(:, 2:3, :, :)]
            else:
                raise ValueError(f'''HR通道数{hr_img.shape[1]}与SR通道数{C}不匹配''')
        sr_img = torch.clamp(sr_img, 0, 1)
        hr_img = torch.clamp(hr_img, 0, 1)
        sr_img = sr_img.to(torch.float32)
        hr_img = hr_img.to(torch.float32)
        if sr_img.shape != hr_img.shape and sr_img.shape[2:] != hr_img.shape[2:]:
            hr_img = F.interpolate(hr_img, size = sr_img.shape[2:], mode = 'bilinear', align_corners = False)
        mse = F.mse_loss(sr_img, hr_img)
        psnr = 10 * torch.log10(1 / (mse + 1e-08))
        ssim_val = self.ssim_metric(sr_img, hr_img)
        if sr_img.shape[1] == 1:
            sr_lpips = sr_img.repeat(1, 3, 1, 1)
            hr_lpips = hr_img.repeat(1, 3, 1, 1)
        else:
            hr_lpips = hr_img
            sr_lpips = sr_img
        sr_lpips = (sr_lpips - 0.5) * 2
        hr_lpips = (hr_lpips - 0.5) * 2
        sr_lpips = torch.clamp(sr_lpips, -1, 1)
        hr_lpips = torch.clamp(hr_lpips, -1, 1)
        lpips_val = self.lpips_model(sr_lpips, hr_lpips).mean()
        return (psnr.item(), ssim_val.item(), lpips_val.item())

    
    def log_epoch_metrics(self, dataset_type, epoch, loss, psnr, ssim, lpips, lr):
        '''记录单轮训练的指标到TensorBoard'''
        writer = self.get_writer(dataset_type)
        writer.add_scalar('train/epoch_loss', loss, epoch)
        writer.add_scalar('train/epoch_psnr', psnr, epoch)
        writer.add_scalar('train/epoch_ssim', ssim, epoch)
        writer.add_scalar('train/epoch_lpips', lpips, epoch)
        writer.add_scalar('train/lr', lr, epoch)
        print(f'''📊 TensorBoard日志记录 - Epoch {epoch}: Loss={loss:.6f}, PSNR={psnr:.2f}, SSIM={ssim:.4f}, LPIPS={lpips:.4f}, LR={lr:.8f}''')

    
    def log_weights(self, dataset_type, model, epoch):
        '''记录模型权重和梯度分布到TensorBoard'''
        writer = self.get_writer(dataset_type)
    # WARNING: Decompyle incomplete

    
    def close_all(self):
        '''关闭所有TensorBoard写入器'''
        for writer in self.writers.values():
            writer.close()
            print('📝 所有TensorBoard日志器已关闭')
            return None



class DWT_Haar(nn.Module):
    '''哈尔小波变换模块（下采样）'''
    
    def forward(self, x):
        (B, C, H, W) = x.shape
    # WARNING: Decompyle incomplete



class IWT_Haar(nn.Module):
    '''哈尔小波逆变换模块（上采样）'''
    
    def forward(self, x):
        (B, C, H, W) = x.shape
    # WARNING: Decompyle incomplete



class Conv2d(nn.Module):
    pass
# WARNING: Decompyle incomplete


class LUMWCNN(nn.Module):
    pass
# WARNING: Decompyle incomplete


class JointLoss(nn.Module):
    pass
# WARNING: Decompyle incomplete


class CTEnhanceTransform:
    '''CT影像专用数据增强：旋转+平移+归一化+高斯噪声'''
    
    def __init__(self, rotate_range, translate_range, noise_std = (15, 0.1, 0.01)):
        self.rotate_range = rotate_range
        self.translate_range = translate_range
        self.noise_std = noise_std

    
    def __call__(self, img):
        angle = np.random.uniform(-(self.rotate_range), self.rotate_range)
        img = img.rotate(angle, resample = Image.BICUBIC, fillcolor = 0)
        (w, h) = img.size
        dx = int(np.random.uniform(-(self.translate_range), self.translate_range) * w)
        dy = int(np.random.uniform(-(self.translate_range), self.translate_range) * h)
        img = Image.fromarray(np.roll(np.array(img), (dy, dx), axis = (0, 1)))
        img_np = np.array(img, dtype = np.float32)
        img_np = (img_np - -1024) / 1424
        img_np = np.clip(img_np, 0, 1)
        img = Image.fromarray((img_np * 255).astype(np.uint8))
        if np.random.rand() < 0.5:
            img_np = np.array(img, dtype = np.float32) / 255
            noise = np.random.normal(0, self.noise_std, img_np.shape)
            img_np = np.clip(img_np + noise, 0, 1)
            img = Image.fromarray((img_np * 255).astype(np.uint8))
        return img



class ResizeIfSmaller(object):
    '''将图像缩放到最小尺寸（保证尺寸为2的倍数）（你的原代码，无修改）'''
    
    def __init__(self, min_size):
        self.min_size = min_size

    
    def __call__(self, img):
        (w, h) = img.size
        scale = max(self.min_size / w, self.min_size / h, 1)
        new_w = int(w * scale)
        new_h = int(h * scale)
        new_w = new_w if new_w % 2 == 0 else new_w + 1
        new_h = new_h if new_h % 2 == 0 else new_h + 1
        if new_w != w or new_h != h:
            img = img.resize((new_w, new_h), Image.BICUBIC)
        return img



class CTDataset(torch.utils.data.Dataset):
    '''
    通用 CT 医学图像数据集加载器
    替代原 LUNA16Dataset、DEEPLESIONDataset、COVIDDataset
    '''
    
    def __init__(self, data_dir, transform, is_test, dataset_name = (None, False, 'CT')):
        pass
    # WARNING: Decompyle incomplete

    
    def __getitem__(self, idx):
        img = Image.open(self.img_paths[idx]).convert('L')
        if self.transform:
            img = self.transform(img)
        (C, H, W) = img.shape
        new_H = (H // SCALE) * SCALE
        new_W = (W // SCALE) * SCALE
        img = img[(:, :new_H, :new_W)]
        lr_img = transforms.Resize((new_H // SCALE, new_W // SCALE), Image.BICUBIC)(img)
        return (lr_img, img)

    
    def __len__(self):
        return len(self.img_paths)



class DIV2KDataset(torch.utils.data.Dataset):
    '''DIV2K RGB数据集加载器（修复版）'''
    
    def __init__(self, data_dir, transform, is_test = (None, False)):
        pass
    # WARNING: Decompyle incomplete

    
    def _load_backup_img(self):
        '''加载备用图片，避免递归错误'''
        if not self.img_paths:
            raise ValueError('数据集目录下无有效图片！')
        
        try:
            img = Image.open(self.img_paths[0]).convert('RGB')
            if self.transform:
                img = self.transform(img)
            lr_img = F.interpolate(img.unsqueeze(0), scale_factor = 1 / self.scale, mode = 'bicubic', align_corners = False).squeeze(0)
            return (lr_img, img)
        except Exception:
            e = None
            raise ValueError(f'''备用图片加载失败: {e}''')
            e = None
            del e


    
    def __getitem__(self, idx):
        img = Image.open(self.img_paths[idx]).convert('L')
        if self.transform:
            img = self.transform(img)
        (C, H, W) = img.shape
        new_H = (H // SCALE) * SCALE
        new_W = (W // SCALE) * SCALE
        img = img[(:, :new_H, :new_W)]
        lr_img = transforms.Resize((new_H // SCALE, new_W // SCALE), Image.BICUBIC)(img)
        return (lr_img, img)

    
    def __len__(self):
        return len(self.img_paths)



class VOC2012Dataset(torch.utils.data.Dataset):
    '''VOC2012 RGB数据集加载器（修复版）'''
    
    def __init__(self, data_dir, transform, is_test = (None, False)):
        pass
    # WARNING: Decompyle incomplete

    
    def _load_backup_img(self):
        '''加载备用图片，避免递归错误'''
        if not self.img_paths:
            raise ValueError('数据集目录下无有效图片！')
        
        try:
            img = Image.open(self.img_paths[0]).convert('RGB')
            if self.transform:
                img = self.transform(img)
            lr_img = F.interpolate(img.unsqueeze(0), scale_factor = 1 / self.scale, mode = 'bicubic', align_corners = False).squeeze(0)
            return (lr_img, img)
        except Exception:
            e = None
            raise ValueError(f'''备用图片加载失败: {e}''')
            e = None
            del e


    
    def __getitem__(self, idx):
        img = Image.open(self.img_paths[idx]).convert('L')
        if self.transform:
            img = self.transform(img)
        (C, H, W) = img.shape
        new_H = (H // SCALE) * SCALE
        new_W = (W // SCALE) * SCALE
        img = img[(:, :new_H, :new_W)]
        lr_img = transforms.Resize((new_H // SCALE, new_W // SCALE), Image.BICUBIC)(img)
        return (lr_img, img)

    
    def __len__(self):
        return len(self.img_paths)


ct_transform = transforms.Compose([
    ResizeIfSmaller(128),
    CTEnhanceTransform(rotate_range = 15, translate_range = 0.1, noise_std = 0.01),
    transforms.RandomCrop(128),
    transforms.ToTensor()])
ct_test_transform = transforms.Compose([
    ResizeIfSmaller(128),
    transforms.ToTensor()])
rgb_transform = transforms.Compose([
    ResizeIfSmaller(256),
    transforms.RandomCrop(256),
    transforms.RandomHorizontalFlip(p = 0.5),
    transforms.ToTensor(),
    transforms.Normalize(mean = [
        0.485,
        0.456,
        0.406], std = [
        0.229,
        0.224,
        0.225])])
rgb_test_transform = transforms.Compose([
    ResizeIfSmaller(256),
    transforms.ToTensor(),
    transforms.Normalize(mean = [
        0.485,
        0.456,
        0.406], std = [
        0.229,
        0.224,
        0.225])])

def load_datasets(luna_sample_ratio = (1,)):
    '''
    加载所有训练数据集（适配5800H+RTX3060 Mobile，支持LUNA16采样）
    Args:
        luna_sample_ratio: LUNA16训练集采样比例（0.2=20%，1.0=全量），COVID/VOC2012/Div2K全量
    Returns:
        dict: 包含各数据集的DataLoader，key为luna16_ct/covid_ct/voc2012_rgb
    '''
    print('🔄 开始加载训练数据集（适配5800H+RTX3060 Mobile）...')
    print(f'''🔧 采样配置：LUNA16采样比例={luna_sample_ratio}，COVID/VOC2012/DIV2K全量训练''')
    luna16_train_set = CTDataset(data_dir = os.path.join(LUNA16_DATA_DIR, 'train'), transform = ct_transform, dataset_name = 'LUNA16')
    deeplesion_train_set = CTDataset(data_dir = os.path.join(DEEPLESION_DATA_DIR, 'train'), transform = ct_transform, dataset_name = 'DEEPLESION')
    covid_train_set = CTDataset(data_dir = os.path.join(COVID_DATA_DIR, 'postive'), transform = ct_transform, dataset_name = 'COVID')
    luna16_train_loader = DataLoader(luna16_train_set, batch_size = BATCH_SIZE, shuffle = True, num_workers = NUM_WORKERS, pin_memory = True, persistent_workers = True, prefetch_factor = 6, drop_last = True)
    deeplesion_train_loader = DataLoader(deeplesion_train_set, batch_size = BATCH_SIZE, shuffle = True, num_workers = NUM_WORKERS, pin_memory = True, persistent_workers = True, prefetch_factor = 6, drop_last = True)
    deeplesionkey_train_set = CTDataset(os.path.join(DEEPLESION_KEY_DATA_DIR, 'train/HR'), ct_transform)
    deeplesionkey_train_loader = DataLoader(deeplesionkey_train_set, batch_size = BATCH_SIZE, shuffle = True, num_workers = NUM_WORKERS, pin_memory = True, persistent_workers = True, prefetch_factor = 6, drop_last = True)
    covid_train_set = COVIDDataset(os.path.join(COVID_DATA_DIR, 'postive'), ct_transform)
    covid_train_loader = DataLoader(covid_train_set, batch_size = BATCH_SIZE, shuffle = True, num_workers = NUM_WORKERS, pin_memory = True, persistent_workers = True, prefetch_factor = 6, drop_last = True)
    print(f'''📝 COVID训练集加载：共{len(covid_train_set)}张（全量）''')
    div2k_train_set = DIV2KDataset(os.path.join(DIV2K_DATA_DIR, 'train'), rgb_transform)
    div2k_train_loader = DataLoader(div2k_train_set, batch_size = BATCH_SIZE, shuffle = True, num_workers = NUM_WORKERS, pin_memory = True, persistent_workers = True, prefetch_factor = 6, drop_last = True)
    print(f'''📝 DIV2K训练集加载：共{len(div2k_train_set)}张（全量）''')
    voc2012_train_set = VOC2012Dataset(os.path.join(VOC2012_DATA_DIR, 'train/img'), rgb_transform)
    voc2012_train_loader = DataLoader(voc2012_train_set, batch_size = BATCH_SIZE, shuffle = True, num_workers = NUM_WORKERS, pin_memory = True, persistent_workers = True, prefetch_factor = 6, drop_last = True)
    print(f'''📝 VOC2012训练集加载：共{len(voc2012_train_set)}张（全量）''')
    print('✅ 所有训练数据集加载完成（适配5800H+RTX3060 Mobile）')
    return {
        'luna16_ct': luna16_train_loader,
        'deeplesionkey_ct': deeplesionkey_train_loader,
        'deeplesion_ct': deeplesion_train_loader,
        'covid_ct': covid_train_loader,
        'div2k_rgb': div2k_train_loader,
        'voc2012_rgb': voc2012_train_loader }


def load_test_datasets(sample_ratio = (1,)):
    '''
    加载所有测试数据集（适配5800H+RTX3060 Mobile，支持采样）
    Args:
        sample_ratio: 测试集采样比例（0.1=10%，1.0=全量），仅对LUNA16生效（样本量太大）
    Returns:
        dict: 包含各数据集的DataLoader，key为luna16_ct/covid_ct/voc2012_rgb
    '''
    print('🔄 开始加载测试数据集（适配5800H+RTX3060 Mobile）...')
    print(f'''🔧 采样配置：LUNA16采样比例={sample_ratio}，COVID/VOC2012全量测试''')
    luna16_test_set = CTDataset(os.path.join(LUNA16_DATA_DIR, 'test'), ct_test_transform, is_test = True)
    if sample_ratio < 1:
        original_size = len(luna16_test_set)
        sample_size = int(original_size * sample_ratio)
        sampled_indices = list(range(sample_size))
        luna16_test_set = Subset(luna16_test_set, sampled_indices)
        print(f'''📝 LUNA16测试集采样：{original_size} → {sample_size} 张''')
    luna16_test_loader = DataLoader(luna16_test_set, batch_size = 1, shuffle = False, num_workers = 4, pin_memory = True, persistent_workers = True, prefetch_factor = PREFETCH_FACTOR)
    covid_test_set = CTDataset(os.path.join(COVID_DATA_DIR, 'test'), ct_test_transform, is_test = True)
    covid_test_loader = DataLoader(covid_test_set, batch_size = 1, shuffle = False, num_workers = 4, pin_memory = True, persistent_workers = True, prefetch_factor = PREFETCH_FACTOR)
    print(f'''📝 COVID测试集加载：共{len(covid_test_set)}张（全量）''')
    div2k_test_set = VOC2012Dataset(os.path.join(DIV2K_DATA_DIR, 'test'), rgb_test_transform, is_test = True)
    div2k_test_loader = DataLoader(div2k_test_set, batch_size = 1, shuffle = False, num_workers = 4, pin_memory = True, persistent_workers = True, prefetch_factor = PREFETCH_FACTOR)
    print(f'''📝 DIV2K测试集加载：共{len(div2k_test_set)}张（全量）''')
    voc2012_test_set = VOC2012Dataset(os.path.join(VOC2012_DATA_DIR, 'test/img'), rgb_test_transform, is_test = True)
    voc2012_test_loader = DataLoader(voc2012_test_set, batch_size = 1, shuffle = False, num_workers = 4, pin_memory = True, persistent_workers = True, prefetch_factor = PREFETCH_FACTOR)
    print(f'''📝 VOC2012测试集加载：共{len(voc2012_test_set)}张（全量）''')
    print('✅ 所有测试数据集加载完成（适配5800H+RTX3060 Mobile）')
    return {
        'luna16_ct': luna16_test_loader,
        'covid_ct': covid_test_loader,
        'div2k_rgb': div2k_test_loader,
        'voc2012_rgb': voc2012_test_loader }


def get_dataset_checkpoint_dir(dataset_type):
    '''获取数据集检查点目录'''
    dir_path = os.path.join(CHECKPOINT_DIR, dataset_type)
    os.makedirs(dir_path, exist_ok = True)
    return dir_path


def get_best_checkpoint_dir(dataset_type):
    '''获取最佳模型目录'''
    dir_path = os.path.join(CHECKPOINT_DIR, f'''best_{dataset_type}''')
    os.makedirs(dir_path, exist_ok = True)
    return dir_path


def get_emergency_checkpoint_dir():
    '''获取紧急模型目录'''
    dir_path = os.path.join(CHECKPOINT_DIR, 'emergency')
    os.makedirs(dir_path, exist_ok = True)
    return dir_path


def load_pretrained_weights(model, pretrain_ckpt, in_channels):
    '''加载预训练权重（适配通道数）- 修复版'''
    pass
# WARNING: Decompyle incomplete


def check_data_health(loader, logger, phase = ('train',)):
    '''
    检查数据集健康状态（适配train/val/test，支持传入logger打印日志）
    Args:
        loader: DataLoader实例
        logger: 日志对象（用于输出日志）
        phase: 阶段名称（train/val/test），仅用于日志打印
    '''
    logger.info(f'''检查{phase}数据健康...''')
    
    try:
        for batch_idx, data in enumerate(loader):
            if batch_idx > 2:
                pass
            elif len(data) == 2:
                (lr, hr) = data
            else:
                (lr, hr, _) = data
            lr = lr.to(DEVICE, non_blocking = True)
            hr = hr.to(DEVICE, non_blocking = True)
            lr_max = round(lr.max().item(), 3)
            lr_min = round(lr.min().item(), 3)
            hr_max = round(hr.max().item(), 3)
            hr_min = round(hr.min().item(), 3)
            logger.info(f'''批次 {batch_idx}: LR范围 [{lr_min}, {lr_max}], HR范围 [{hr_min}, {hr_max}]''')
            logger.info(f'''{phase}数据健康检查通过 ✅''')
            return None
            except Exception:
                e = None
                logger.error(f'''{phase}数据集加载失败: {e}''')
                raise 
                e = None
                del e



def load_checkpoint(model, optimizer, scheduler, dataset_type):
    '''
    全面修复的检查点加载函数 - 彻底解决通道不匹配问题
    '''
    pass
# WARNING: Decompyle incomplete


def save_checkpoint(model, optimizer, scheduler, epoch, best_loss, best_psnr, best_ssim, best_lpips, dataset_type):
    '''
    保存训练断点（新目录结构）
    Args:
        model: 模型实例
        optimizer: 优化器实例
        scheduler: 学习率调度器实例
        epoch: 已完成的训练轮次
        best_loss/best_psnr/best_ssim/best_lpips: 最佳指标
        dataset_type: 数据集类型
    '''
    pass
# WARNING: Decompyle incomplete


def train_continual(model, train_loader, pretrain_ckpt, dataset_type, tb_logger):
    '''
    最终修复的训练函数 - 从根源上解决通道不匹配问题
    关键思想：在加载检查点之前，确保模型通道数与数据集匹配
    '''
    log_file = os.path.join(OUTPUT_DETAIL_DIR, f'''{dataset_type}_train_log.txt''')
    logger = Logger(log_file)
    sys.stdout = logger
    print(f'''📝 开始记录{dataset_type}训练日志到：{log_file}''')
    expected_channels = 1 if 'ct' in dataset_type else 3
    dataset_dir = get_dataset_checkpoint_dir(dataset_type)
    best_dir = get_best_checkpoint_dir(dataset_type)
    emergency_dir = get_emergency_checkpoint_dir()
    emergency_ckpt_path = os.path.join(emergency_dir, f'''{dataset_type}_emergency_model.pth''')
    completed_epoch = 0
    best_loss = float('inf')
    best_psnr = 0
    best_ssim = 0
    best_lpips = float('inf')
# WARNING: Decompyle incomplete


def save_image(tensor, save_path):
    '''将张量保存为图像'''
    tensor = tensor.squeeze(0).cpu()
    tensor = torch.clamp(tensor, 0, 1)
    if tensor.shape[0] == 1:
        img = transforms.ToPILImage()(tensor).convert('L')
    else:
        img = transforms.ToPILImage()(tensor)
    img.save(save_path)
    print(f'''💾 图像已保存：{save_path}''')


def test_model(model_path, dataset_type, tb_logger, sample_ratio = (1,)):
    '''
    适配5800H+RTX3060 Mobile的测试函数
    Args:
        model_path: 模型权重路径
        dataset_type: 测试数据集类型（luna16_ct/covid_ct/voc2012_rgb）
        tb_logger: TensorBoard日志器
        sample_ratio: 测试集采样比例（0.1=10%，1.0=全量，LUNA16建议设0.2）
    '''
    test_log_file = os.path.join(OUTPUT_DETAIL_DIR, f'''{dataset_type}_test_log.txt''')
    test_logger = Logger(test_log_file)
    sys.stdout = test_logger
    print(f'''\n===== 开始测试{dataset_type}模型（适配5800H+RTX3060 Mobile） =====''')
    print(f'''📝 测试日志保存到：{test_log_file}''')
    print(f'''🔧 测试模型路径：{model_path} | 测试集采样比例：{sample_ratio}''')
    test_loaders = load_test_datasets()
    test_loader = test_loaders[dataset_type]
    if sample_ratio < 1 and dataset_type == 'luna16_ct':
        full_test_set = test_loader.dataset
        sample_size = int(len(full_test_set) * sample_ratio)
        sampled_indices = list(range(sample_size))
        sampled_test_set = torch.utils.data.Subset(full_test_set, sampled_indices)
        test_loader = DataLoader(sampled_test_set, batch_size = 1, shuffle = False, num_workers = 4, pin_memory = True, persistent_workers = True, prefetch_factor = PREFETCH_FACTOR)
        print(f'''📝 LUNA16测试集采样：{len(full_test_set)} → {sample_size} 张''')
    in_channels = 1 if 'ct' in dataset_type else 3
    model = LUMWCNN(in_channels = in_channels, scale = SCALE).to(DEVICE)
    checkpoint = torch.load(model_path, map_location = DEVICE, weights_only = True)
    if 'model_state_dict' in checkpoint:
        model.load_state_dict(checkpoint['model_state_dict'])
    else:
        model.load_state_dict(checkpoint)
    model.eval()
    torch.cuda.empty_cache()
    torch.backends.cudnn.benchmark = True
    (total_psnr, total_ssim, total_lpips, total_cnt) = (0, 0, 0, 0)
    test_pbar = tqdm(test_loader, desc = f'''测试 {dataset_type} (适配5800H+RTX3060)''')
    dataset_test_dir = os.path.join(TEST_OUTPUT_DIR, dataset_type)
    os.makedirs(dataset_test_dir, exist_ok = True)
    torch.no_grad()
    for lr_img, hr_img in enumerate(test_pbar):
        hr_img = hr_img.to(DEVICE, non_blocking = True)
        lr_img = lr_img.to(DEVICE, non_blocking = True)
        sr_img = model(lr_img)
        (sr_img, hr_img) = model._align_tensor_size(sr_img, hr_img)
        (psnr, ssim_val, lpips_val) = tb_logger.calculate_metrics(sr_img, hr_img)
        total_psnr += psnr
        total_ssim += ssim_val
        total_lpips += lpips_val
        total_cnt += 1
        test_pbar.set_postfix({
            'PSNR': f'''{psnr:.2f}''',
            'SSIM': f'''{ssim_val:.4f}''',
            'LPIPS': f'''{lpips_val:.4f}''',
            '累计PSNR': f'''{total_psnr / total_cnt:.2f}''' })
        torch.cuda.empty_cache()
        torch.cuda.empty_cache()
        None(None, None)
    with None:
        if not None if idx == 0 or idx % 20 == 0 else None:
            pass
    if total_cnt > 0:
        avg_psnr = total_psnr / total_cnt
        avg_ssim = total_ssim / total_cnt
        avg_lpips = total_lpips / total_cnt
    else:
        avg_psnr = 0
        avg_ssim = 0
        avg_lpips = 0
    print(f'''\n===== {dataset_type}测试完成（适配5800H+RTX3060） =====''')
    print(f'''📊 测试样本数：{total_cnt}''')
    print(f'''📊 平均指标 - PSNR: {avg_psnr:.2f} | SSIM: {avg_ssim:.4f} | LPIPS: {avg_lpips:.4f}''')
    tb_logger.get_writer(f'''{dataset_type}_test''')
    tb_logger.log_epoch_metrics(f'''{dataset_type}_test''', 0, 0, avg_psnr, avg_ssim, avg_lpips, 0)
    torch.cuda.empty_cache()
    test_logger.close()
    sys.stdout = test_logger.terminal
    print(f'''✅ {dataset_type}测试完成，显存已清理''')


def find_best_ckpt(prefix):
    '''容错版找最佳模型：避免找不到文件报错'''
    pass
# WARNING: Decompyle incomplete

if __name__ == '__main__':
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'
    torch.backends.cudnn.benchmark = True
    torch.cuda.empty_cache()
    tb_logger = TBLogger()
    train_loaders = load_datasets(luna_sample_ratio = 0.2)
    model = LUMWCNN(scale = SCALE).to(DEVICE)
    train_continual(model, train_loaders['deeplesionkey_ct'], DEEPLESION_CKPT, 'deeplesionkey_ct', tb_logger)
    train_continual(model, train_loaders['voc2012_rgb'], DIV2K_CKPT, 'voc2012_rgb', tb_logger)
    luna16_best_ckpt = find_best_ckpt('best_luna16_ct_loss')
    covid_best_ckpt = find_best_ckpt('best_covid_ct_loss')
    div2k_best_ckpt = find_best_ckpt('best_div2k_rgb_loss')
    voc2012_best_ckpt = find_best_ckpt('best_voc2012_rgb_loss')
    tb_logger.close_all()
    print('\n🎉 所有训练和测试任务完成！')
    print('\n🎉 所有训练和测试任务完成！')
    return None
