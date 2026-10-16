import os
import sys
import time
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Subset
from torchvision import transforms
import numpy as np
from tqdm import tqdm
from PIL import Image
import os.path as path
import torch.nn.functional as F
from torch.utils.tensorboard.writer import SummaryWriter
import lpips
import warnings
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts, CosineAnnealingLR
from torchmetrics.image import StructuralSimilarityIndexMeasure

warnings.filterwarnings('ignore')

 ==============================================================================
 . 全局配置区（所有可配置参数集中管理）
 ==============================================================================
 权重文件路径
DEEPLESION_CKPT = "./output_deeplesion/goat/best_luna_ct_psnr_epoch_.pth"


 数据集路径
LUNA_DATA_DIR = "/home/dake/Documents/Projects/datasets/LUNA/sr_slice_dataset/"
VOC_DATA_DIR = "/home/dake/Documents/Projects/datasets/VOC/sr_split/"
COVID_DATA_DIR = "/home/dake/Documents/Projects/datasets/COVID-CT/COVID-CT-Images/"
DIVK_DATA_DIR = "/home/dake/Documents/Projects/datasets/DIVK_HR/"
DEEPLESION_DATA_DIR = "/home/dake/Documents/Projects/datasets/DeepLesion/deeplesion_category_split/lung/"
DEEPLESION_KEY_DATA_DIR = "/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/" 


 训练超参数
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
SCALE =    超分缩放因子
BATCH_SIZE = 
LR = e-   初始学习率
WEIGHT_DECAY = e-   L正则化系数
EPOCHS =    最大训练轮数
FREEZE_BACKBONE_EPOCHS =    主干网络冻结轮数
EARLY_STOPPING_PATIENCE =    早停耐心值
EARLY_STOPPING_MIN_DELTA = e-   早停最小提升阈值

 输出路径
CHECKPOINT_DIR = "./continual_ckpt"   模型断点保存目录
OUTPUT_DETAIL_DIR = "./output_detail"   日志输出目录
TB_LOG_DIR = "./tb_logs"   TensorBoard日志目录
TEST_OUTPUT_DIR = "./test_output"   测试结果保存目录

 创建必要目录
os.makedirs(CHECKPOINT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DETAIL_DIR, exist_ok=True)
os.makedirs(TB_LOG_DIR, exist_ok=True)
os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)   新增测试输出目录

 ==============================================================================
 . 工具类（日志、早停、指标计算）
 ==============================================================================
class Logger:
    """日志重定向类：同时输出到终端和文件"""
    def __init__(self, log_file):
        self.terminal = sys.stdout
        self.log = open(log_file, "a", encoding="utf-")
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
    """早停机制：基于PSNR/SSIM/LPIPS多指标判断"""
    def __init__(self, patience=, min_delta=e-, verbose=True):
        self.patience = patience
        self.min_delta = min_delta
        self.verbose = verbose
        self.counter = 
        self.best_psnr = -float('inf')
        self.best_ssim = -float('inf')
        self.best_lpips = float('inf')
        self.early_stop = False

    def reset_counter(self):
        """重置早停计数器"""
        self.counter = 
        if self.verbose:
            print(f" 早停计数器已重置为")

    def __call__(self, psnr, ssim, lpips):
        """
        每轮训练后调用，判断是否触发早停
        Args:
            psnr: 当前轮PSNR值
            ssim: 当前轮SSIM值
            lpips: 当前轮LPIPS值
        Returns:
            bool: 是否触发早停
        """
         判断各指标是否有有效提升
        psnr_improved = psnr > (self.best_psnr + self.min_delta)
        ssim_improved = ssim > (self.best_ssim + self.min_delta)
        lpips_improved = lpips < (self.best_lpips - self.min_delta)
        any_improved = psnr_improved or ssim_improved or lpips_improved

         更新最佳指标
        if psnr_improved:
            self.best_psnr = psnr
        if ssim_improved:
            self.best_ssim = ssim
        if lpips_improved:
            self.best_lpips = lpips

         更新计数器
        if any_improved:
            self.counter = 
        else:
            self.counter += 
            if self.verbose:
                print(f"️ EarlyStopping counter: {self.counter}/{self.patience} | "
                      f"最佳PSNR: {self.best_psnr:.f} | 最佳SSIM: {self.best_ssim:.f} | 最佳LPIPS: {self.best_lpips:.f}")
            if self.counter >= self.patience:
                self.early_stop = True
                if self.verbose:
                    print("️ Early stopping triggered!（多指标均无有效提升）")
        return self.early_stop


class TBLogger:
    """TensorBoard日志器：负责指标计算和日志写入（修复SSIM维度错误）"""
    def __init__(self, log_dir=TB_LOG_DIR):
        self.log_dir = log_dir
        self.writers = {}
         初始化LPIPS模型
        self.lpips_model = lpips.LPIPS(net='vgg').eval().to(DEVICE)

         初始化SSIM度量，它会自动处理不同通道数
        self.ssim_metric = StructuralSimilarityIndexMeasure(
            kernel_size=,
            sigma=.,
            data_range=.,
            k=.,
            k=.
        ).to(DEVICE)

     不再需要手动窗口
     self._ssim_win = self._create_ssim_window(, .).to(DEVICE)

    def compute_ssim(self, preds, targets):
        """计算SSIM，自动处理RGB和灰度图"""
        return self.ssim_metric(preds, targets)

    def get_writer(self, dataset_type):
        """获取指定数据集的TensorBoard写入器"""
        if dataset_type not in self.writers:
            writer_dir = os.path.join(self.log_dir, dataset_type)
            self.writers[dataset_type] = SummaryWriter(log_dir=writer_dir)
            print(f" 初始化TensorBoard日志器: {writer_dir}")
        return self.writers[dataset_type]

    def calculate_metrics(self, sr_img, hr_img):
        """
        计算超分图像的评估指标：PSNR/SSIM/LPIPS
        Args:
            sr_img: 超分图像 (B,C,H,W)
            hr_img: 高清原图 (B,C,H,W)
        Returns:
            tuple: (psnr, ssim, lpips)
        """
         先移动到设备
        sr_img = sr_img.float().to(DEVICE)
        hr_img = hr_img.float().to(DEVICE)

        B, C, H, W = sr_img.shape

         通道数校验
        if hr_img.shape[] != C:
             可以自动处理通道不匹配的情况
            if hr_img.shape[] ==  and C == :
                 灰度HR转RGB
                hr_img = hr_img.repeat(, , , )
            elif hr_img.shape[] ==  and C == :
                 RGB HR转灰度
                hr_img = .  hr_img[:, :, :, :] + .  hr_img[:, :, :, :] + .  hr_img[:, :, :, :]
            else:
                raise ValueError(f"HR通道数{hr_img.shape[]}与SR通道数{C}不匹配")

         ===== 关键前置处理 =====
         ① 确保值范围在[,]
        sr_img = torch.clamp(sr_img, ., .)
        hr_img = torch.clamp(hr_img, ., .)
             ② 确保是float
        sr_img = sr_img.to(torch.float)
        hr_img = hr_img.to(torch.float)
         ③ 确保两个图像尺寸完全一致
        if sr_img.shape != hr_img.shape:
             自动对齐尺寸
            if sr_img.shape[:] != hr_img.shape[:]:
                hr_img = F.interpolate(
                    hr_img, size=sr_img.shape[:], mode='bilinear', align_corners=False
                )

         计算PSNR
        mse = F.mse_loss(sr_img, hr_img)
        psnr =   torch.log(. / (mse + e-))

         计算SSIM
        ssim_val = self.ssim_metric(sr_img, hr_img)   使用torchmetrics的SSIM
         计算LPIPS
        if sr_img.shape[] == :
             灰度图转RGB
            sr_lpips = sr_img.repeat(, , , )
            hr_lpips = hr_img.repeat(, , , )
        else:
            sr_lpips, hr_lpips = sr_img, hr_img

         LPIPS需要图像归一化到[-, ]
        sr_lpips = (sr_lpips - .)  
        hr_lpips = (hr_lpips - .)  

         确保在[-, ]范围内
        sr_lpips = torch.clamp(sr_lpips, -., .)
        hr_lpips = torch.clamp(hr_lpips, -., .)

        lpips_val = self.lpips_model(sr_lpips, hr_lpips).mean()

        return psnr.item(), ssim_val.item(), lpips_val.item()

    def log_epoch_metrics(self, dataset_type, epoch, loss, psnr, ssim, lpips, lr):
        """记录单轮训练的指标到TensorBoard"""
        writer = self.get_writer(dataset_type)
        writer.add_scalar('train/epoch_loss', loss, epoch)
        writer.add_scalar('train/epoch_psnr', psnr, epoch)
        writer.add_scalar('train/epoch_ssim', ssim, epoch)
        writer.add_scalar('train/epoch_lpips', lpips, epoch)
        writer.add_scalar('train/lr', lr, epoch)
        print(f" TensorBoard日志记录 - Epoch {epoch}: Loss={loss:.f}, PSNR={psnr:.f}, SSIM={ssim:.f}, LPIPS={lpips:.f}, LR={lr:.f}")

    def log_weights(self, dataset_type, model, epoch):
        """记录模型权重和梯度分布到TensorBoard"""
        writer = self.get_writer(dataset_type)
        for name, param in model.named_parameters():
            writer.add_histogram(f'weights/{name}', param, epoch)
            if param.grad is not None:
                writer.add_histogram(f'grads/{name}', param.grad, epoch)
        print(f" TensorBoard权重日志记录 - Epoch {epoch}: 已记录{len(list(model.named_parameters()))}层参数和梯度")

    def close_all(self):
        """关闭所有TensorBoard写入器"""
        for writer in self.writers.values():
            writer.close()
        print(" 所有TensorBoard日志器已关闭")

def calculate_metrics_batch(self, sr_img, hr_img, batch_size=):
    """
    分批计算指标，避免内存溢出
    """
    psnr_list, ssim_list, lpips_list = [], [], []

     分批计算
    for i in range(, sr_img.shape[], batch_size):
        end_idx = min(i + batch_size, sr_img.shape[])
        sr_batch = sr_img[i:end_idx]
        hr_batch = hr_img[i:end_idx]

        psnr, ssim, lpips = self.calculate_metrics(sr_batch, hr_batch)
        psnr_list.append(psnr)
        ssim_list.append(ssim)
        lpips_list.append(lpips)

    return np.mean(psnr_list), np.mean(ssim_list), np.mean(lpips_list)

def validate_metrics_calculation(self, sr_img, hr_img):
    """
    验证指标计算的正确性
    """
    print("=== 指标计算验证 ===")
    print(f"输入形状: SR={sr_img.shape}, HR={hr_img.shape}")
    print(f"值范围: SR=[{sr_img.min():.f}, {sr_img.max():.f}], "
          f"HR=[{hr_img.min():.f}, {hr_img.max():.f}]")

     计算指标
    psnr, ssim, lpips = self.calculate_metrics(sr_img, hr_img)

    print(f"计算结果: PSNR={psnr:.f}, SSIM={ssim:.f}, LPIPS={lpips:.f}")

     验证自相似性
    if torch.allclose(sr_img, hr_img, rtol=e-):
        print("SR和HR相同，预期: PSNR=∞, SSIM≈., LPIPS≈.")
        print(f"实际: PSNR={psnr:.f}, SSIM={ssim:.f}, LPIPS={lpips:.f}")

    return psnr, ssim, lpips

 ==============================================================================
 . 模型组件（小波变换、卷积模块、主模型、损失函数）
 ==============================================================================
class DWT_Haar(nn.Module):
    """哈尔小波变换模块（下采样）"""
    def forward(self, x):
        B, C, H, W = x.shape
        assert H %  ==  and W %  == , f"输入尺寸{H}x{W}必须是的倍数"
        x = x.reshape(B, C, H // , , W // , )
        x = x.permute(, , , , , ).contiguous()
        return x.view(B, C  , H // , W // )   【修改】移除冗余的.to(x.device)

class IWT_Haar(nn.Module):
    """哈尔小波逆变换模块（上采样）"""
    def forward(self, x):
        B, C, H, W = x.shape
        assert C %  == , f"输入通道数{C}必须是的倍数"
        x = x.view(B, C // , , , H, W)
        x = x.permute(, , , , , ).contiguous()
        return x.view(B, C // , H  , W  )   【修改】移除冗余的.to(x.device)

class Convd(nn.Module):
    """带Dropout和ReLU的卷积模块"""
    def __init__(self, in_ch: int, out_ch: int, kernel_size: int, act: bool = True, dropout: float = .) -> None:
        super(Convd, self).__init__()
        layer_list = [nn.Convd(in_ch, out_ch, kernel_size, padding=kernel_size//)]   原代码padding正确，保留
        if dropout > :
            layer_list.append(nn.Dropoutd(dropout))
        if act:
            layer_list.append(nn.ReLU())
        self.model = nn.Sequential(layer_list)

    def forward(self, x):
        return self.model(x)   【修改】移除冗余的.to(x.device)

class LUMWCNN(nn.Module):
    """LUMWCNN主模型：基于小波变换的超分网络（修复版）"""
    def __init__(self, in_channels: int = , device=None, scale=, dropout: float = .) -> None:
        super(LUMWCNN, self).__init__()
        self.device = device or torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.in_channels = in_channels
        self.scale = scale
        assert self.in_channels in [, ], "in_channels仅支持/"

         小波变换层
        self.DWT = DWT_Haar()
        self.IWT = IWT_Haar()

         左侧编码路径
        self.l_conv = nn.Sequential(
            Convd(self.in_channels, , , dropout=dropout), 
            Convd(, , , dropout=dropout)
        )
        self.l_conv = nn.Sequential(
            Convd(, , , dropout=dropout),     =
            Convd(, , , dropout=dropout)
        )
        self.l_conv = nn.Sequential(
            Convd(, , , dropout=dropout),     =
            Convd(, , , dropout=dropout)
        )

         右侧解码路径
        self.r_conv = nn.Sequential(
            Convd(, , , dropout=dropout), 
            Convd(, , , dropout=dropout)
        )
        self.r_conv = nn.Sequential(
            Convd(, , , dropout=dropout), 
            Convd(, , , dropout=dropout)
        )
        self.r_conv = nn.Sequential(
            Convd(, , , dropout=dropout), 
            Convd(, self.in_channels, , dropout=.)
        )

         上采样模块（PixelShuffle）【关键修复：移除groups参数或设为】
        if self.scale == :
            self.upsample = nn.Sequential(
                nn.Convd(in_channels, in_channels, , , padding=, groups=),   明确设置groups=
                nn.PixelShuffle()
            )
        elif self.scale == :
            self.upsample = nn.Sequential(
                nn.Convd(in_channels, in_channels, , , padding=, groups=),   明确设置groups=
                nn.PixelShuffle(),
                nn.Convd(in_channels, in_channels, , , padding=, groups=),   明确设置groups=
                nn.PixelShuffle()
            )

        self.pads = []   记录小波变换的padding信息

    def _align_tensor_size(self, tensor_a, tensor_b):
        """对齐两个张量的尺寸（取最小高宽）"""
        min_h = min(tensor_a.shape[], tensor_b.shape[])
        min_w = min(tensor_a.shape[], tensor_b.shape[])
        return tensor_a[:, :, :min_h, :min_w], tensor_b[:, :, :min_h, :min_w]

    def wavelet_pad(self, x):
        """小波变换前的padding（保证尺寸为的倍数）【修改：修复padding方向】"""
        pad_h =  if x.shape[-]% != else 
        pad_w =  if x.shape[-]% != else 
        self.pads.append([pad_w, pad_h])
         F.pad参数：(left, right, top, bottom) → 改为右侧/底部padding，匹配shave逻辑
        return F.pad(x, (, pad_w, , pad_h), 'constant', )

    def wavelet_shave(self, x):
        """小波逆变换后的去padding【修改：修复shave方向】"""
        if not self.pads:
            return x
        pad_w, pad_h = self.pads.pop()
         去掉右侧pad_w列、底部pad_h行（对应padding的位置）
        if pad_w: 
            x = x[:, :, :, :-pad_w]
        if pad_h: 
            x = x[:, :, :-pad_h, :]
        return x

    def forward(self, x):
        x = x.to(self.device)

         通道数适配（→ 或 →）—— 原逻辑正确，保留
        if x.shape[]== and self.in_channels==:
            x = x.repeat(,,,)
        elif x.shape[]== and self.in_channels==:
            x = torch.mean(x, dim=, keepdim=True)

         编码路径（原逻辑正确，保留）
        x_l = self.l_conv(x)
        x_l_pad = self.wavelet_pad(x_l)
        _x_l = self.DWT(x_l_pad)
        x_l = self.l_conv(_x_l)
        x_l_pad = self.wavelet_pad(x_l)
        _x_l = self.DWT(x_l_pad)
        x_l = self.l_conv(_x_l)

         解码路径（带残差连接）—— 原逻辑正确，保留
        _after_r_conv = self.r_conv(x_l)
        lhs = self.IWT(_after_r_conv)
        lhs_shave = self.wavelet_shave(lhs)
        lhs_shave, x_l = self._align_tensor_size(lhs_shave, x_l)
        x_r = lhs_shave + x_l

        _after_r_conv = self.r_conv(x_r)
        _x_r = self.IWT(_after_r_conv)
        _x_r_shave = self.wavelet_shave(_x_r)
        _x_r_shave, x_l = self._align_tensor_size(_x_r_shave, x_l)
        x_r = _x_r_shave + x_l

        x_r = self.r_conv(x_r)
        x_r, x = self._align_tensor_size(x_r, x)
        x_r = x_r + x

         上采样+值域约束（关键：保证输出在[,]）
        y = self.upsample(x_r)
        y = torch.clamp(y, ., .)
        return y

class JointLoss(nn.Module):
    """联合损失函数：MSE(主导) + SSIM + LPIPS（修复版）"""
    def __init__(self, lpips_model, alpha=., beta=., gamma=.):
        super(JointLoss, self).__init__()
        self.alpha = alpha   MSE权重
        self.beta = beta     SSIM损失权重
        self.gamma = gamma   LPIPS损失权重
        self.mse_loss = nn.MSELoss()
        self.lpips_model = lpips_model.eval()
        
         初始化torchmetrics的SSIM，不再用手动实现
        self.ssim_metric = StructuralSimilarityIndexMeasure(
            kernel_size=,
            sigma=.,
            data_range=.,
            k=.,
            k=.
        )

    def ssim_loss(self, x, y):
        """使用torchmetrics计算SSIM损失（ - SSIM）"""
         确保设备一致
        self.ssim_metric = self.ssim_metric.to(x.device)
        
         计算SSIM
        ssim_val = self.ssim_metric(x, y)
        return . - ssim_val

    def forward(self, sr, hr):
        """
        计算联合损失
        Args:
            sr: 超分图像
            hr: 高清原图
        Returns:
            float: 加权联合损失值
        """
         确保通道一致
        if sr.shape[] != hr.shape[]:
            if sr.shape[] ==  and hr.shape[] == :
                 灰度SR，RGB HR -> 转换HR为灰度
                hr = .  hr[:, :, :, :] + .  hr[:, :, :, :] + .  hr[:, :, :, :]
            elif sr.shape[] ==  and hr.shape[] == :
                 RGB SR，灰度HR -> 复制HR为RGB
                hr = hr.repeat(, , , )
        
        mse = self.mse_loss(sr, hr)
        ssim = self.ssim_loss(sr, hr)
        
         LPIPS需要通道输入
        if sr.shape[] == :
            sr_lpips = sr.repeat(, , , )
            hr_lpips = hr.repeat(, , , )
        else:
            sr_lpips, hr_lpips = sr, hr
        lpips = self.lpips_model(sr_lpips, hr_lpips).mean()
        
         加权求和
        total_loss = self.alpha  mse + self.beta  ssim + self.gamma  lpips
        return total_loss

 ==============================================================================
 . 数据处理（数据增强、数据集定义、数据加载）
 ==============================================================================
class CTEnhanceTransform:
    """CT影像专用数据增强：旋转+平移+归一化+高斯噪声"""
    def __init__(self, rotate_range=, translate_range=., noise_std=.):
        self.rotate_range = rotate_range
        self.translate_range = translate_range
        self.noise_std = noise_std

    def __call__(self, img):
         随机旋转
        angle = np.random.uniform(-self.rotate_range, self.rotate_range)
        img = img.rotate(angle, resample=Image.BICUBIC, fillcolor=)
        
         随机平移
        w, h = img.size
        dx = int(np.random.uniform(-self.translate_range, self.translate_range)  w)
        dy = int(np.random.uniform(-self.translate_range, self.translate_range)  h)
        img = Image.fromarray(np.roll(np.array(img), (dy, dx), axis=(, )))
        
         CT值归一化（关键：[-,] → [,]）
        img_np = np.array(img, dtype=np.float)
        img_np = (img_np - (-)) / ( - (-))
        img_np = np.clip(img_np, ., .)
        img = Image.fromarray((img_np  ).astype(np.uint))
        
         随机高斯噪声
        if np.random.rand() < .:
            img_np = np.array(img, dtype=np.float) / .
            noise = np.random.normal(, self.noise_std, img_np.shape)
            img_np = np.clip(img_np + noise, , )
            img = Image.fromarray((img_np  ).astype(np.uint))
        
        return img

class ResizeIfSmaller(object):
    """将图像缩放到最小尺寸（保证尺寸为的倍数）（你的原代码，无修改）"""
    def __init__(self, min_size):
        self.min_size = min_size

    def __call__(self, img):
        w, h = img.size
        scale = max(self.min_size/w, self.min_size/h, .)
        new_w = int(wscale)
        new_h = int(hscale)
         保证尺寸为的倍数
        new_w = new_w if new_w%== else new_w+
        new_h = new_h if new_h%== else new_h+
        if new_w !=w or new_h!=h:
            img = img.resize((new_w, new_h), Image.BICUBIC)
        return img


class LUNADataset(torch.utils.data.Dataset):
    """LUNA CT数据集加载器"""
    def __init__(self, data_dir, transform=None, is_test=False):
        self.img_paths = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".png")]
        self.transform = transform
        self.is_test = is_test
        print(f" LUNA数据集加载: 共{len(self.img_paths)}张图片 (测试模式: {is_test})")

    def __getitem__(self, idx):
        img = Image.open(self.img_paths[idx]).convert('L')
        if self.transform:
            img = self.transform(img)
         测试模式不裁剪，保持原图尺寸（仅保证是缩放因子倍数）
        if self.is_test:
            hr_h, hr_w = img.size(), img.size()
            lr_h = (hr_h // SCALE)  SCALE
            lr_w = (hr_w // SCALE)  SCALE
            img = img[:, :lr_h, :lr_w]
            lr_img = transforms.Resize((hr_h//SCALE, hr_w//SCALE), Image.BICUBIC)(img)
        else:
             保证尺寸是缩放因子的倍数
            hr_h, hr_w = img.size(), img.size()
            lr_h, lr_w = (hr_h//SCALE)SCALE, (hr_w//SCALE)SCALE
            img = img[:, :lr_h, :lr_w]
             生成低分辨率图像
            lr_img = transforms.Resize((hr_h//SCALE, hr_w//SCALE), Image.BICUBIC)(img)
        return lr_img, img

    def __len__(self):
        return len(self.img_paths)


class COVIDDataset(torch.utils.data.Dataset):
    """COVID- CT数据集加载器"""
    def __init__(self, data_dir, transform=None, is_test=False):
        self.img_paths = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".png")]
        self.transform = transform
        self.is_test = is_test
        print(f" COVID数据集加载: 共{len(self.img_paths)}张图片 (测试模式: {is_test})")

    def __getitem__(self, idx):
        img = Image.open(self.img_paths[idx]).convert('L')
        if self.transform:
            img = self.transform(img)
         测试模式不裁剪，保持原图尺寸（仅保证是缩放因子倍数）
        if self.is_test:
            hr_h, hr_w = img.size(), img.size()
            lr_h = (hr_h // SCALE)  SCALE
            lr_w = (hr_w // SCALE)  SCALE
            img = img[:, :lr_h, :lr_w]
            lr_img = transforms.Resize((hr_h//SCALE, hr_w//SCALE), Image.BICUBIC)(img)
        else:
             保证尺寸是缩放因子的倍数
            hr_h, hr_w = img.size(), img.size()
            lr_h, lr_w = (hr_h//SCALE)SCALE, (hr_w//SCALE)SCALE
            img = img[:, :lr_h, :lr_w]
             生成低分辨率图像
            lr_img = transforms.Resize((hr_h//SCALE, hr_w//SCALE), Image.BICUBIC)(img)
        return lr_img, img

    def __len__(self):
        return len(self.img_paths)

class DIVKDataset(torch.utils.data.Dataset):
    """DIVK RGB数据集加载器（修复版）"""
    def __init__(self, data_dir, transform=None, is_test=False):
        self.img_paths = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".png")]
        self.transform = transform
        self.is_test = is_test
        self.scale = SCALE
         过滤空路径，避免加载失败
        self.img_paths = [p for p in self.img_paths if os.path.exists(p)]
        print(f" DIVK数据集加载: 共{len(self.img_paths)}张图片 (测试模式: {is_test})")
         预加载第张图片作为备用（避免递归错误）
        self.backup_img = self._load_backup_img()

    def _load_backup_img(self):
        """加载备用图片，避免递归错误"""
        if not self.img_paths:
            raise ValueError("数据集目录下无有效图片！")
        try:
            img = Image.open(self.img_paths[]).convert('RGB')
            if self.transform:
                img = self.transform(img)
             生成对应的低分辨率图
            lr_img = F.interpolate(img.unsqueeze(), scale_factor=/self.scale, 
                                  mode='bicubic', align_corners=False).squeeze()
            return lr_img, img
        except Exception as e:
            raise ValueError(f"备用图片加载失败: {e}")

    def __getitem__(self, idx):
        try:
            img = Image.open(self.img_paths[idx]).convert('RGB')
            if self.transform:
                img = self.transform(img)   transform已包含尺寸处理，无需额外resize
            
             保证尺寸是scale的倍数（仅对tensor操作）
            _, h, w = img.shape
            new_h = (h // self.scale)  self.scale
            new_w = (w // self.scale)  self.scale
            img = img[:, :new_h, :new_w]
            
             生成低分辨率图像（tensor用F.interpolate，而非PIL的Resize）
            lr_img = F.interpolate(img.unsqueeze(), size=(new_h//self.scale, new_w//self.scale),
                                  mode='bicubic', align_corners=False).squeeze()
            return lr_img, img
        except Exception as e:
            print(f"️  批次{idx}出错：{e}，使用备用图片替代，跳过")
            return self.backup_img

    def __len__(self):
        return len(self.img_paths)


class VOCDataset(torch.utils.data.Dataset):
    """VOC RGB数据集加载器（修复版）"""
    def __init__(self, data_dir, transform=None, is_test=False):
        self.img_paths = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".jpg")]
        self.transform = transform
        self.is_test = is_test
        self.scale = SCALE
         过滤空路径，避免加载失败
        self.img_paths = [p for p in self.img_paths if os.path.exists(p)]
        print(f" VOC数据集加载: 共{len(self.img_paths)}张图片 (测试模式: {is_test})")
         预加载第张图片作为备用（避免递归错误）
        self.backup_img = self._load_backup_img()

    def _load_backup_img(self):
        """加载备用图片，避免递归错误"""
        if not self.img_paths:
            raise ValueError("数据集目录下无有效图片！")
        try:
            img = Image.open(self.img_paths[]).convert('RGB')
            if self.transform:
                img = self.transform(img)
             生成对应的低分辨率图
            lr_img = F.interpolate(img.unsqueeze(), scale_factor=/self.scale, 
                                  mode='bicubic', align_corners=False).squeeze()
            return lr_img, img
        except Exception as e:
            raise ValueError(f"备用图片加载失败: {e}")

    def __getitem__(self, idx):
        try:
            img = Image.open(self.img_paths[idx]).convert('RGB')
            if self.transform:
                img = self.transform(img)   transform已包含尺寸处理，无需额外resize
            
             保证尺寸是scale的倍数（仅对tensor操作）
            _, h, w = img.shape
            new_h = (h // self.scale)  self.scale
            new_w = (w // self.scale)  self.scale
            img = img[:, :new_h, :new_w]
            
             生成低分辨率图像（tensor用F.interpolate，而非PIL的Resize）
            lr_img = F.interpolate(img.unsqueeze(), size=(new_h//self.scale, new_w//self.scale),
                                  mode='bicubic', align_corners=False).squeeze()
            return lr_img, img
        except Exception as e:
            print(f"️  批次{idx}出错：{e}，使用备用图片替代，跳过")
            return self.backup_img

    def __len__(self):
        return len(self.img_paths)

 数据增强流水线定义
ct_transform = transforms.Compose([
    ResizeIfSmaller(),
    CTEnhanceTransform(rotate_range=, translate_range=., noise_std=.),
    transforms.RandomCrop(),
    transforms.ToTensor()
])

 测试用CT变换（无数据增强，仅归一化+转Tensor）
ct_test_transform = transforms.Compose([
    ResizeIfSmaller(),
    transforms.ToTensor()
])

 简化变换定义（删除重复定义）
rgb_transform = transforms.Compose([
    ResizeIfSmaller(),
    transforms.RandomCrop(),
    transforms.RandomHorizontalFlip(p=.),
    transforms.ToTensor(),
    transforms.Normalize(mean=[., ., .], std=[., ., .])   RGB标准化（可选）
])

 测试用RGB变换（无数据增强）
rgb_test_transform = transforms.Compose([
    ResizeIfSmaller(),
    transforms.ToTensor(),
    transforms.Normalize(mean=[., ., .], std=[., ., .])
])
 加载数据集
def load_datasets(luna_sample_ratio=.):
    """
    加载所有训练数据集（适配H+RTX Mobile，支持LUNA采样）
    Args:
        luna_sample_ratio: LUNA训练集采样比例（.=%，.=全量），COVID/VOC/DivK全量
    Returns:
        dict: 包含各数据集的DataLoader，key为luna_ct/covid_ct/voc_rgb
    """
    print(" 开始加载训练数据集（适配H+RTX Mobile）...")
    print(f" 采样配置：LUNA采样比例={luna_sample_ratio}，COVID/VOC/DIVK全量训练")

     ====================== . LUNA CT训练集（支持采样） ======================
    luna_train_set = LUNADataset(
        os.path.join(LUNA_DATA_DIR, "train"),
        ct_transform
    )
     仅对LUNA采样（万+样本量太大）
    if luna_sample_ratio < .:
        original_size = len(luna_train_set)
        sample_size = int(original_size  luna_sample_ratio)
         随机采样（比取前N张更均匀，避免模型学偏）
        sampled_indices = torch.randperm(original_size)[:sample_size]  
        luna_train_set = Subset(luna_train_set, sampled_indices)
        print(f" LUNA训练集采样：{original_size} → {sample_size} 张")
     H+RTX最优配置
    luna_train_loader = DataLoader(
        luna_train_set,
        batch_size=BATCH_SIZE,
        shuffle=True,                训练集必须打乱
        num_workers=,               适配核CPU，拉满数据加载速度
        pin_memory=True,             加速CPU→GPU拷贝，移动端GPU收益大
        persistent_workers=True,     子进程存活，避免每轮重建
        prefetch_factor=,           提前加载批，GPU完全不等
        drop_last=True               丢弃不完整批次，避免显存波动
    )

     ====================== . COVID CT训练集（全量） ======================
    covid_train_set = COVIDDataset(
        os.path.join(COVID_DATA_DIR, "postive"),
        ct_transform
    )
    covid_train_loader = DataLoader(
        covid_train_set,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=,
        pin_memory=True,
        persistent_workers=True,
        prefetch_factor=,
        drop_last=True
    )
    print(f" COVID训练集加载：共{len(covid_train_set)}张（全量）")
    
    divk_train_set = DIVKDataset(
        os.path.join(DIVK_DATA_DIR, "train"),
        rgb_transform
    )
    divk_train_loader = DataLoader(
        divk_train_set,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=,
        pin_memory=True,
        persistent_workers=True,
        prefetch_factor=,
        drop_last=True
    )
    print(f" DIVK训练集加载：共{len(divk_train_set)}张（全量）")

     ====================== . VOC RGB训练集（全量） ======================
    voc_train_set = VOCDataset(
        os.path.join(VOC_DATA_DIR, "train/img"),
        rgb_transform
    )
    voc_train_loader = DataLoader(
        voc_train_set,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=,
        pin_memory=True,
        persistent_workers=True,
        prefetch_factor=,
        drop_last=True
    )
    print(f" VOC训练集加载：共{len(voc_train_set)}张（全量）")

    print(" 所有训练数据集加载完成（适配H+RTX Mobile）")
    return {
        "luna_ct": luna_train_loader,
        "covid_ct": covid_train_loader,
        "divk_rgb": divk_train_loader,
        "voc_rgb": voc_train_loader
    }


def load_test_datasets(sample_ratio=.):
    """
    加载所有测试数据集（适配H+RTX Mobile，支持采样）
    Args:
        sample_ratio: 测试集采样比例（.=%，.=全量），仅对LUNA生效（样本量太大）
    Returns:
        dict: 包含各数据集的DataLoader，key为luna_ct/covid_ct/voc_rgb
    """
    print(" 开始加载测试数据集（适配H+RTX Mobile）...")
    print(f" 采样配置：LUNA采样比例={sample_ratio}，COVID/VOC全量测试")

     ====================== . LUNA CT测试集（支持采样） ======================
    luna_test_set = LUNADataset(
        os.path.join(LUNA_DATA_DIR, "test"),
        ct_test_transform,
        is_test=True
    )
     仅对LUNA做采样（样本量太大）
    if sample_ratio < .:
        original_size = len(luna_test_set)
        sample_size = int(original_size  sample_ratio)
         取前N张（也可以用随机采样：torch.randperm(original_size)[:sample_size]）
        sampled_indices = list(range(sample_size))  
        luna_test_set = Subset(luna_test_set, sampled_indices)
        print(f" LUNA测试集采样：{original_size} → {sample_size} 张")
     创建适配硬件的DataLoader
    luna_test_loader = DataLoader(
        luna_test_set,
        batch_size=,                 单张推理，适配移动端GPU显存
        shuffle=False,                测试集绝对不打乱，保证结果可复现
        num_workers=,                适配H 核：测试集用核，不抢占CPU资源
        pin_memory=True,              加速CPU→GPU数据拷贝，移动端GPU收益显著
        persistent_workers=True,      子进程全程存活，仅创建一次，减少耗时
        prefetch_factor=,            提前加载批数据，避免GPU空等
         测试集保留所有样本，不设置drop_last
    )

     ====================== . COVID CT测试集（全量） ======================
    covid_test_set = COVIDDataset(
        os.path.join(COVID_DATA_DIR, "test"),
        ct_test_transform,
        is_test=True
    )
    covid_test_loader = DataLoader(
        covid_test_set,
        batch_size=,
        shuffle=False,
        num_workers=,
        pin_memory=True,
        persistent_workers=True,
        prefetch_factor=
    )
    print(f" COVID测试集加载：共{len(covid_test_set)}张（全量）")
    
    divk_test_set = VOCDataset(
        os.path.join(DIVK_DATA_DIR, "test"),
        rgb_test_transform,
        is_test=True
    )
    divk_test_loader = DataLoader(
        divk_test_set,
        batch_size=,
        shuffle=False,
        num_workers=,
        pin_memory=True,
        persistent_workers=True,
        prefetch_factor=
    )
    print(f" DIVK测试集加载：共{len(divk_test_set)}张（全量）")

     ====================== . VOC RGB测试集（全量） ======================
    voc_test_set = VOCDataset(
        os.path.join(VOC_DATA_DIR, "test/img"),
        rgb_test_transform,
        is_test=True
    )
    voc_test_loader = DataLoader(
        voc_test_set,
        batch_size=,
        shuffle=False,
        num_workers=,
        pin_memory=True,
        persistent_workers=True,
        prefetch_factor=
    )
    print(f" VOC测试集加载：共{len(voc_test_set)}张（全量）")

    print(" 所有测试数据集加载完成（适配H+RTX Mobile）")
    return {
        "luna_ct": luna_test_loader,
        "covid_ct": covid_test_loader,
        "divk_rgb": divk_test_loader,
        "voc_rgb": voc_test_loader
    }
 ==============================================================================
 . 模型加载/保存工具（预训练权重、断点续训）
 ==============================================================================

 在文件顶部或其他适当位置添加这些函数
def get_dataset_checkpoint_dir(dataset_type):
    """获取数据集检查点目录"""
    dir_path = os.path.join(CHECKPOINT_DIR, dataset_type)
    os.makedirs(dir_path, exist_ok=True)
    return dir_path

def get_best_checkpoint_dir(dataset_type):
    """获取最佳模型目录"""
    dir_path = os.path.join(CHECKPOINT_DIR, f"best_{dataset_type}")
    os.makedirs(dir_path, exist_ok=True)
    return dir_path

def get_emergency_checkpoint_dir():
    """获取紧急模型目录"""
    dir_path = os.path.join(CHECKPOINT_DIR, "emergency")
    os.makedirs(dir_path, exist_ok=True)
    return dir_path

def load_pretrained_weights(model, pretrain_ckpt, in_channels):
    """加载预训练权重（适配通道数）- 修复版"""
     如果预训练权重路径为None，则跳过加载
    if pretrain_ckpt is None:
        print(f"️ 预训练权重路径为None，跳过加载预训练权重")
        return model
    
    if not os.path.exists(pretrain_ckpt):
        raise FileNotFoundError(f" 预训练权重不存在：{pretrain_ckpt}")

     加载权重文件
    checkpoint = torch.load(pretrain_ckpt, map_location=DEVICE, weights_only=False)
    pretrain_dict = checkpoint["model_state_dict"] if "model_state_dict" in checkpoint else checkpoint
    
     清理权重键名（适配DataParallel等情况）
    pretrain_dict = {k.replace('module.', ''): v for k, v in pretrain_dict.items()}
    pretrain_dict = {k.replace('.layers.', '.model.'): v for k, v in pretrain_dict.items()}
    
     过滤非张量权重（避免BN层参数问题）
    pretrain_tensor_dict = {
        k: v for k, v in pretrain_dict.items()
        if isinstance(v, torch.Tensor) and not any(x in k for x in [
            'running_mean', 'running_var', 'num_batches_tracked'
        ])
    }

     获取预训练模型的输入通道数
    target_key = 'l_conv..model..weight'
    if target_key in pretrain_tensor_dict:
        pretrain_in_ch = pretrain_tensor_dict[target_key].shape[]
    else:
         如果找不到标准键，尝试查找其他可能的第一个卷积层
        for k in pretrain_tensor_dict.keys():
            if 'conv' in k and 'weight' in k and pretrain_tensor_dict[k].dim() == :
                pretrain_in_ch = pretrain_tensor_dict[k].shape[]
                target_key = k
                print(f"️ 使用替代键检测通道数: {k}")
                break
        else:
            pretrain_in_ch = None
    
     如果检测到通道数不匹配，进行转换
    if pretrain_in_ch is not None and pretrain_in_ch != in_channels:
        print(f"️ 通道适配：{pretrain_in_ch}→{in_channels}")
        
         需要转换的层列表
        layers_to_convert = []
        
         . 查找所有需要转换的卷积层
        for k, v in pretrain_tensor_dict.items():
            if 'weight' in k and v.dim() == :   卷积权重
                 检查是否是输入层（输入通道数等于模型输入通道数）
                if v.shape[] == pretrain_in_ch:
                    layers_to_convert.append(k)
                 检查上采样模块的卷积层
                elif 'upsample' in k and v.shape[] in [pretrain_in_ch, pretrain_in_ch  ]:
                     注意：上采样模块的输入通道可能是 in_channels 或 in_channels
                    layers_to_convert.append(k)
        
        print(f" 需要转换的层: {len(layers_to_convert)} 个")
        
         . 执行转换
        for k in layers_to_convert:
            v = pretrain_tensor_dict[k]
            if v.shape[] == pretrain_in_ch:
                 输入通道转换
                if pretrain_in_ch ==  and in_channels == :
                     ->通道：重复次
                    pretrain_tensor_dict[k] = v.repeat(, , , ) / .
                    print(f"   转换 {k}: {[, v.shape[:]]} → {[, v.shape[:]]}")
                elif pretrain_in_ch ==  and in_channels == :
                     ->通道：取平均
                    pretrain_tensor_dict[k] = v.mean(dim=, keepdim=True)
                    print(f"   转换 {k}: {[, v.shape[:]]} → {[, v.shape[:]]}")
            elif 'upsample' in k and v.shape[] == pretrain_in_ch  :
                 上采样模块的特殊处理
                if pretrain_in_ch ==  and in_channels == :
                     ->通道，输出通道也要相应变化
                    new_out_channels = in_channels  
                     重新构造权重
                    new_weight = torch.zeros(
                        new_out_channels, in_channels, 
                        v.shape[], v.shape[],
                        device=v.device, dtype=v.dtype
                    )
                     将原权重分配到新权重的对应位置
                    for i in range():
                        new_weight[i:(i+), i:i+, :, :] = v / .
                    pretrain_tensor_dict[k] = new_weight
                    print(f"   转换 {k}: {list(v.shape)} → {list(new_weight.shape)}")
                elif pretrain_in_ch ==  and in_channels == :
                     ->通道，输出通道也要变化
                    new_out_channels = in_channels  
                     对输入通道取平均
                    new_weight = v.view(, , , v.shape[], v.shape[]).mean(dim=)
                    pretrain_tensor_dict[k] = new_weight
                    print(f"   转换 {k}: {list(v.shape)} → {list(new_weight.shape)}")

     匹配模型权重
    model_dict = model.state_dict()
    matched_dict = {}
    shape_mismatch = []
    key_not_found = []
    
    for k, v in pretrain_tensor_dict.items():
        if k in model_dict:
            if model_dict[k].shape == v.shape:
                matched_dict[k] = v
            else:
                shape_mismatch.append((k, v.shape, model_dict[k].shape))
        else:
            key_not_found.append(k)
    
     更新模型字典
    model_dict.update(matched_dict)
    model.load_state_dict(model_dict, strict=False)
    
     打印加载结果
    print(f"\n 预训练权重加载完成")
    print(f"   匹配层数: {len(matched_dict)}")
    print(f"   形状不匹配: {len(shape_mismatch)}")
    print(f"   键未找到: {len(key_not_found)}")
    
    if shape_mismatch:
        print(f"\n️ 形状不匹配的层 (前个):")
        for k, saved_shape, model_shape in shape_mismatch[:]:
            print(f"   {k}: 保存{saved_shape} ≠ 模型{model_shape}")
    
    if key_not_found and len(matched_dict) < :
        print(f"\n️ 键未找到的示例 (前个):")
        for k in key_not_found[:]:
            print(f"   {k}")
    
    return model

def load_checkpoint(model, optimizer, scheduler, dataset_type):
    """加载训练断点（修复版）- 解决通道数检测问题"""
     扫描数据集目录中的断点文件
    dataset_dir = get_dataset_checkpoint_dir(dataset_type)
    ckpt_files = [f for f in os.listdir(dataset_dir) 
                  if f.startswith(f"{dataset_type}_epoch_") and f.endswith(".pth")]
    
    if not ckpt_files:
        print(f" 在{dataset_dir}中未找到断点文件")
         尝试在旧目录中查找
        old_ckpt_files = [f for f in os.listdir(CHECKPOINT_DIR) 
                          if f.startswith(f"{dataset_type}_epoch_") and f.endswith(".pth")]
        if old_ckpt_files:
            print(f"️ 在旧目录中找到{len(old_ckpt_files)}个检查点，将迁移到新目录")
            dataset_dir = CHECKPOINT_DIR
            ckpt_files = old_ckpt_files
        else:
            print(f"️ 无断点文件，从头训练{dataset_type}")
            return model, optimizer, scheduler, , float('inf'), ., ., float('inf')
    
    print(f" 扫描到{dataset_dir}中的epoch文件：{ckpt_files}")
    
     解析断点轮数
    parsed_ckpts = []
    for f in ckpt_files:
        try:
            epoch_num = int(f.replace(f"{dataset_type}_epoch_", "").replace(".pth", ""))
            parsed_ckpts.append((epoch_num, f))
        except:
            continue
    parsed_ckpts.sort(key=lambda x: x[])
    print(f" 成功解析的ckpt文件：{parsed_ckpts}")
    
     无断点文件
    if not parsed_ckpts:
        print(f"️ 无断点文件，从头训练{dataset_type}")
        return model, optimizer, scheduler, , float('inf'), ., ., float('inf')
    
     加载最新断点
    latest_epoch, latest_file = parsed_ckpts[-]
    latest_ckpt_path = os.path.join(dataset_dir, latest_file)
    print(f" 自动找到最新断点文件：{latest_ckpt_path} (epoch {latest_epoch})")
    
    checkpoint = torch.load(latest_ckpt_path, map_location=DEVICE)
    
     检查保存的模型通道数
    saved_model_state = checkpoint['model_state_dict']
    
      修复: 更智能地查找第一个卷积层
    saved_channels = None
    first_conv_key = None
    
     优先查找已知的卷积层键名
    possible_conv_keys = [
        'l_conv..model..weight',   主路径第一个卷积
        'l_conv..weight',           可能的简化键名
        'l_conv.weight',             可能的简化键名
        'conv.weight',               可能的简化键名
    ]
    
    for key in possible_conv_keys:
        if key in saved_model_state:
            first_conv_key = key
            break
    
     如果没找到，遍历所有键
    if not first_conv_key:
        for key in saved_model_state.keys():
            if 'weight' in key and 'conv' in key and len(saved_model_state[key].shape) == :
                first_conv_key = key
                print(f" 找到替代的卷积层键: {key}")
                break
    
    if first_conv_key:
        saved_weight = saved_model_state[first_conv_key]
        if len(saved_weight.shape) >= :   确保是卷积权重 [out_c, in_c, h, w]
            saved_channels = saved_weight.shape[]   输入通道数
            print(f" 保存的模型输入通道数: {saved_channels} (来自权重 {first_conv_key} 形状 {list(saved_weight.shape)})")
        else:
            print(f"️ 权重 {first_conv_key} 不是有效的卷积权重，形状: {list(saved_weight.shape)}")
    else:
        print("️ 无法确定保存模型的输入通道数")
         尝试通过模型的其他方式获取
        if hasattr(model, 'in_channels'):
            saved_channels = model.in_channels
            print(f" 使用模型默认输入通道数: {saved_channels}")
    
     检查当前模型通道数
    if hasattr(model, 'in_channels'):
        current_channels = model.in_channels
    else:
         尝试从模型的第一个卷积层获取
        for name, param in model.named_parameters():
            if 'weight' in name and 'conv' in name and len(param.shape) == :
                current_channels = param.shape[]
                print(f" 从模型参数推断当前输入通道数: {current_channels} (来自 {name})")
                break
        else:
            current_channels =  if 'rgb' in dataset_type else 
            print(f" 无法推断，使用数据集默认: {current_channels}")
    
    print(f" 当前模型输入通道数: {current_channels}")
    
     如果通道数不匹配，需要调整
    if saved_channels is not None and saved_channels != current_channels:
        print(f"️ 通道数不匹配: 保存的模型是{saved_channels}通道，当前模型是{current_channels}通道")
        
        if saved_channels ==  and current_channels == :
            print(" 从灰度模型(通道)转换为RGB模型(通道)...")
            new_model_state = {}
            
            for key, param in saved_model_state.items():
                if 'weight' in key and param.dim() == :
                     卷积权重处理
                    if param.shape[] == :
                         输入通道为，扩展到（取平均）
                        param = param.repeat(, , , ) / .
                        print(f"   扩展: {key} 从 {list(saved_model_state[key].shape)} 到 {list(param.shape)}")
                    new_model_state[key] = param
                else:
                    new_model_state[key] = param
            
            saved_model_state = new_model_state
            
        elif saved_channels ==  and current_channels == :
            print(" 从RGB模型(通道)转换为灰度模型(通道)...")
            new_model_state = {}
            
            for key, param in saved_model_state.items():
                if 'weight' in key and param.dim() == :
                     卷积权重处理
                    if param.shape[] == :
                         输入通道为，转换为（取平均）
                        param = param.mean(dim=, keepdim=True)
                        print(f"   转换: {key} 从 {list(saved_model_state[key].shape)} 到 {list(param.shape)}")
                    new_model_state[key] = param
                else:
                    new_model_state[key] = param
            
            saved_model_state = new_model_state
        
        print(" 通道转换完成")
    
     关键修复: 检查模型状态字典的键是否匹配
    model_keys = set(model.state_dict().keys())
    checkpoint_keys = set(saved_model_state.keys())
    
    print(f" 模型键数量: {len(model_keys)}, 检查点键数量: {len(checkpoint_keys)}")
    
     检查不匹配的键
    missing_in_checkpoint = model_keys - checkpoint_keys
    extra_in_checkpoint = checkpoint_keys - model_keys
    
    if missing_in_checkpoint:
        print(f"️ 检查点缺少以下模型键: {list(missing_in_checkpoint)[:]}")
        if len(missing_in_checkpoint) > :
            print(f"   ... 还有 {len(missing_in_checkpoint) - } 个")
    
    if extra_in_checkpoint:
        print(f"️ 检查点包含额外键: {list(extra_in_checkpoint)[:]}")
        if len(extra_in_checkpoint) > :
            print(f"   ... 还有 {len(extra_in_checkpoint) - } 个")
    
     加载模型参数
    try:
        model.load_state_dict(saved_model_state, strict=False)
        print(" 模型参数加载成功 (strict=False)")
    except Exception as e:
        print(f"️ 模型参数加载失败: {e}")
        print(" 尝试非严格加载...")
         尝试手动加载匹配的参数
        model_dict = model.state_dict()
        matched_keys = []
        for key, param in saved_model_state.items():
            if key in model_dict and model_dict[key].shape == param.shape:
                model_dict[key] = param
                matched_keys.append(key)
        
        model.load_state_dict(model_dict, strict=False)
        print(f" 手动加载了 {len(matched_keys)} 个参数")
    
     恢复优化器状态
    try:
        saved_optimizer_state = checkpoint['optimizer_state_dict']
        
         检查参数组数量
        if len(optimizer.param_groups) != len(saved_optimizer_state['param_groups']):
            print(f"️ 参数组数量不匹配: 当前{len(optimizer.param_groups)} != 保存{len(saved_optimizer_state['param_groups'])}")
            raise ValueError("参数组数量不匹配")
        
         检查每个参数组的参数数量
        param_count_mismatch = False
        for i, (current_group, saved_group) in enumerate(zip(optimizer.param_groups, saved_optimizer_state['param_groups'])):
            if len(current_group['params']) != len(saved_group['params']):
                print(f"️ 参数组{i}参数数量不匹配: 当前{len(current_group['params'])} != 保存{len(saved_group['params'])}")
                param_count_mismatch = True
        
        if param_count_mismatch:
            raise ValueError("参数组参数数量不匹配")
        
         尝试直接加载优化器状态
        optimizer.load_state_dict(saved_optimizer_state)
        print(f" 优化器状态加载成功")
        
    except (ValueError, KeyError, RuntimeError) as e:
        print(f"️ 优化器状态加载失败：{e}")
        print(" 重新初始化优化器，但恢复学习率")
        
         重新初始化优化器
        optimizer = optim.Adam(
            filter(lambda p: p.requires_grad, model.parameters()), 
            lr=LR, 
            weight_decay=WEIGHT_DECAY
        )
        
         尝试从保存的优化器状态中恢复学习率
        if 'optimizer_state_dict' in checkpoint:
            saved_optimizer = checkpoint['optimizer_state_dict']
            if 'param_groups' in saved_optimizer and len(saved_optimizer['param_groups']) > :
                 从保存的优化器中获取学习率
                saved_lr = saved_optimizer['param_groups'][].get('lr', LR)
                 设置到新优化器
                optimizer.param_groups[]['lr'] = saved_lr
                print(f" 从检查点恢复学习率: {saved_lr}")
    
     恢复调度器状态
    try:
        scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
        print(f" 调度器状态加载成功")
    except (KeyError, ValueError, RuntimeError) as e:
        print(f"️ 调度器状态加载失败：{e}，重新初始化调度器")
        scheduler = CosineAnnealingWarmRestarts(optimizer, T_=, T_mult=, eta_min=e-)
    
     恢复训练状态
    start_epoch = checkpoint.get('epoch', )
    best_loss = checkpoint.get('best_loss', float('inf'))
    best_psnr = checkpoint.get('best_psnr', .)
    best_ssim = checkpoint.get('best_ssim', .)
    best_lpips = checkpoint.get('best_lpips', float('inf'))
    
     如果检查点中保存的是已完成轮数，下一轮应该是 start_epoch + 
     但根据您的日志，检查点中的 epoch= 表示已完成轮
    next_epoch = start_epoch + 
    
     打印恢复信息
    print(f"\n===== 从断点恢复：{latest_ckpt_path} =====")
    print(f" 检查点轮次: {start_epoch}")
    print(f" 从第 {next_epoch} 轮开始训练")
    print(f" 恢复的最佳指标 - Loss: {best_loss:.f} | PSNR: {best_psnr:.f} | SSIM: {best_ssim:.f} | LPIPS: {best_lpips:.f}")
    
    return model, optimizer, scheduler, next_epoch, best_loss, best_psnr, best_ssim, best_lpips

def save_checkpoint(model, optimizer, scheduler, epoch, best_loss, best_psnr, best_ssim, best_lpips, dataset_type):
    """
    保存训练断点（新目录结构）
    Args:
        model: 模型实例
        optimizer: 优化器实例
        scheduler: 学习率调度器实例
        epoch: 已完成的训练轮次
        best_loss/best_psnr/best_ssim/best_lpips: 最佳指标
        dataset_type: 数据集类型
    """
     获取数据集检查点目录
    dataset_dir = get_dataset_checkpoint_dir(dataset_type)
    ckpt_path = os.path.join(dataset_dir, f"{dataset_type}_epoch_{epoch}.pth")
    
     保存状态
    checkpoint = {
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': scheduler.state_dict(),
        'best_loss': best_loss,
        'best_psnr': best_psnr,
        'best_ssim': best_ssim,
        'best_lpips': best_lpips
    }
    
    torch.save(checkpoint, ckpt_path)
    
     清理旧断点（仅保留最近个，避免磁盘占用）
    ckpt_files = [f for f in os.listdir(dataset_dir) 
                  if f.startswith(f"{dataset_type}_epoch_") and f.endswith(".pth")]
    
    if len(ckpt_files) > :
        parsed_ckpts = []
        for f in ckpt_files:
            try:
                epoch_num = int(f.replace(f"{dataset_type}_epoch_", "").replace(".pth", ""))
                parsed_ckpts.append((epoch_num, f))
            except:
                continue
        parsed_ckpts.sort(key=lambda x: x[])
        for _, old_file in parsed_ckpts[:-]:
            old_path = os.path.join(dataset_dir, old_file)
            os.remove(old_path)
            print(f"️ 清理旧断点文件：{old_path}")
    
    print(f" 断点已保存：{ckpt_path}（已完成第{epoch}轮训练）")


 ==============================================================================
 . 核心训练流程
 ==============================================================================

def train_continual(model, train_loader, pretrain_ckpt, dataset_type, tb_logger):
    """
    持续训练函数修复版 - 解决通道数检查问题
    """
     初始化日志
    log_file = os.path.join(OUTPUT_DETAIL_DIR, f"{dataset_type}_train_log.txt")
    logger = Logger(log_file)
    sys.stdout = logger
    print(f" 开始记录{dataset_type}训练日志到：{log_file}")

     数据集配置
    expected_channels =  if "ct" in dataset_type else 
    
     获取各个目录路径
    dataset_dir = get_dataset_checkpoint_dir(dataset_type)
    best_dir = get_best_checkpoint_dir(dataset_type)
    emergency_dir = get_emergency_checkpoint_dir()
    
     提前定义所有需要的变量
    emergency_ckpt_path = os.path.join(emergency_dir, f"{dataset_type}_emergency_model.pth")
    completed_epoch = 
    best_loss = float('inf')
    best_psnr = .
    best_ssim = .
    best_lpips = float('inf')
    epoch = 

    try:
          修复: 改进通道数检查逻辑
        print(f"\n 开始通道数检查...")
        print(f"  数据集类型: {dataset_type}")
        print(f"  期望通道数: {expected_channels}")

         检查模型当前通道数
        if hasattr(model, 'in_channels'):
            current_channels = model.in_channels
            print(f"  模型in_channels属性: {current_channels}")
        else:
             尝试从模型权重推断
            for name, param in model.named_parameters():
                if 'weight' in name and 'conv' in name and len(param.shape) == :
                    current_channels = param.shape[]
                    print(f"  从权重推断通道数: {current_channels} (来自 {name})")
                    break
            else:
                current_channels = expected_channels
                print(f"  无法推断，使用期望通道数: {current_channels}")

         检查模型第一个卷积层
        model_state = model.state_dict()
        first_conv_key = None
        for key in model_state.keys():
            if 'weight' in key and 'conv' in key and len(model_state[key].shape) == :
                first_conv_key = key
                weight_shape = list(model_state[key].shape)
                print(f"  模型第一个卷积层: {key}, 形状: {weight_shape}, 输入通道: {weight_shape[]}")
                current_channels = weight_shape[]   使用实际的权重形状
                break

        print(f"  最终确定的模型当前通道数: {current_channels}")

        if current_channels != expected_channels:
            print(f"️ 模型通道数不匹配！模型是{current_channels}通道，但数据集需要{expected_channels}通道")
            print(f" 调整模型通道数...")

             重新创建正确通道数的模型
            model = LUMWCNN(
                in_channels=expected_channels,
                device=DEVICE,
                scale=SCALE,
                dropout=.
            ).to(DEVICE)

            print(f" 已重新初始化模型为{expected_channels}通道")

        lpips_model = lpips.LPIPS(net='vgg').eval().to(DEVICE)

        print(f"\n===== 开始训练{dataset_type} =====")
        print(f" 数据集配置 - 输入通道: {expected_channels} | 缩放因子: {SCALE} | 批次大小: {BATCH_SIZE} | 初始LR: {LR} | L正则化: {WEIGHT_DECAY}")
        print(f" 早停配置 - Patience: {EARLY_STOPPING_PATIENCE} | Min Delta: {EARLY_STOPPING_MIN_DELTA}")
        print(f" 训练配置 - 总轮数: {EPOCHS} | 冻结主干轮数: {FREEZE_BACKBONE_EPOCHS}")

         加载预训练权重
        if pretrain_ckpt is not None and os.path.exists(pretrain_ckpt):
            print(f" 加载预训练权重: {pretrain_ckpt}")
            model = load_pretrained_weights(model, pretrain_ckpt, expected_channels)
        elif pretrain_ckpt is not None:
            print(f"️ 预训练权重文件不存在: {pretrain_ckpt}，从头开始训练")
        else:
            print(f"️ 无预训练权重，从头开始训练")

         冻结主干网络
        freeze_layers = [model.l_conv, model.l_conv, model.l_conv]
        for layer in freeze_layers:
            for param in layer.parameters():
                param.requires_grad = False
        print(f" 前{FREEZE_BACKBONE_EPOCHS}轮冻结主干网络")

         初始化优化器
        optimizer = optim.Adam(
            filter(lambda p: p.requires_grad, model.parameters()), 
            lr=LR, 
            weight_decay=WEIGHT_DECAY
        )

         初始化学习率调度器
        scheduler = CosineAnnealingWarmRestarts(optimizer, T_=, T_mult=, eta_min=e-)

          使用修复版的load_checkpoint
        model, optimizer, scheduler, completed_epoch, best_loss, best_psnr, best_ssim, best_lpips = load_checkpoint(
            model, optimizer, scheduler, dataset_type
        )

         注意: completed_epoch 是下一轮要开始的轮数
        print(f" 断点加载完成 - 下一轮开始轮数: {completed_epoch} | 总轮数: {EPOCHS}")
        print(f" 历史最佳指标 - Loss: {best_loss:.f} | PSNR: {best_psnr:.f} | SSIM: {best_ssim:.f} | LPIPS: {best_lpips:.f}")

         初始化早停和损失函数
        early_stopping = EarlyStopping(
            patience=EARLY_STOPPING_PATIENCE, 
            min_delta=EARLY_STOPPING_MIN_DELTA
        )
        criterion = JointLoss(lpips_model, alpha=., beta=., gamma=.)

         开始训练
        model.train()
        for epoch in range(completed_epoch, EPOCHS):
            current_train_epoch = epoch +    显示给用户的轮数

             解冻主干网络
            if epoch == FREEZE_BACKBONE_EPOCHS:
                for layer in freeze_layers:
                    for param in layer.parameters():
                        param.requires_grad = True
                 重新初始化优化器和调度器
                optimizer = optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
                scheduler = CosineAnnealingWarmRestarts(optimizer, T_=, T_mult=, eta_min=e-)
                early_stopping.reset_counter()
                print(f"\n 第{current_train_epoch}轮解冻主干，开始全量训练 | 重置学习率调度器和早停计数器")

             初始化本轮指标
            epoch_loss, epoch_psnr, epoch_ssim, epoch_lpips, cnt = ., ., ., ., 
            pbar = tqdm(train_loader, desc=f"[{dataset_type}] Epoch {current_train_epoch}/{EPOCHS}")

             批次训练
            for batch_idx, (lr_img, hr_img) in enumerate(pbar):
                try:
                    lr_img, hr_img = lr_img.to(DEVICE, non_blocking=True), hr_img.to(DEVICE, non_blocking=True)
                    sr_img = model(lr_img)
                    sr_img, hr_img = model._align_tensor_size(sr_img, hr_img)
                    loss = criterion(sr_img, hr_img)

                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()

                    scheduler.step(epoch + batch_idx/len(train_loader))

                    psnr, ssim_val, lpips_val = tb_logger.calculate_metrics(sr_img, hr_img)
                    epoch_loss += loss.item()
                    epoch_psnr += psnr
                    epoch_ssim += ssim_val
                    epoch_lpips += lpips_val
                    cnt += 

                    current_lr = optimizer.param_groups[]['lr']
                    pbar.set_postfix({
                        "Loss": f"{loss.item():.f}", 
                        "PSNR": f"{psnr:.f}",
                        "SSIM": f"{ssim_val:.f}",
                        "LPIPS": f"{lpips_val:.f}",
                        "LR": f"{current_lr:.f}",
                        "Batch": f"{batch_idx+}/{len(train_loader)}"
                    })
                except Exception as e:
                    print(f"\n️  批次{batch_idx}出错：{e}，跳过")
                    continue

             计算本轮平均指标
            if cnt > :
                avg_loss = epoch_loss / cnt
                avg_psnr = epoch_psnr / cnt
                avg_ssim = epoch_ssim / cnt
                avg_lpips = epoch_lpips / cnt
            else:
                avg_loss, avg_psnr, avg_ssim, avg_lpips = , , , 
                print(f"\n️  Epoch {current_train_epoch}无有效批次，指标均为")

            current_lr = optimizer.param_groups[]['lr']

             打印本轮结果
            print(f"\n[{dataset_type}] Epoch {current_train_epoch}/{EPOCHS}：")
            print(f"  Loss={avg_loss:.f} | PSNR={avg_psnr:.f} | SSIM={avg_ssim:.f} | LPIPS={avg_lpips:.f}")
            print(f"  当前学习率：{current_lr:.f} | 已处理批次：{cnt}/{len(train_loader)}")

             保存检查点
            epoch_ckpt_path = os.path.join(dataset_dir, f"{dataset_type}_epoch_{current_train_epoch}.pth")
            torch.save({
                'epoch': current_train_epoch,    修复: 保存当前轮数
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'scheduler_state_dict': scheduler.state_dict(),
                'loss': avg_loss,
                'best_loss': best_loss,
                'best_psnr': best_psnr,
                'best_ssim': best_ssim,
                'best_lpips': best_lpips
            }, epoch_ckpt_path)
            print(f" 保存本轮检查点：{epoch_ckpt_path}")

             更新最佳指标
            if avg_loss < best_loss and avg_loss > :
                best_loss = avg_loss
                best_loss_path = os.path.join(best_dir, f"best_{dataset_type}_loss_epoch_{current_train_epoch}.pth")
                torch.save({
                    "epoch": current_train_epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "best_loss": best_loss,
                    "current_metrics": {
                        "psnr": avg_psnr,
                        "ssim": avg_ssim,
                        "lpips": avg_lpips
                    }
                }, best_loss_path)
                print(f" 保存最佳Loss模型：{best_loss_path} | 最佳Loss={best_loss:.f}")

            if avg_psnr > best_psnr and avg_psnr > :
                best_psnr = avg_psnr
                best_psnr_path = os.path.join(best_dir, f"best_{dataset_type}_psnr_epoch_{current_train_epoch}.pth")
                torch.save({
                    "epoch": current_train_epoch,
                    "model_state_dict": model.state_dict(),
                    "best_psnr": best_psnr,
                    "current_metrics": {
                        "loss": avg_loss,
                        "ssim": avg_ssim,
                        "lpips": avg_lpips
                    }
                }, best_psnr_path)
                print(f" 保存最佳PSNR模型：{best_psnr_path} | 最佳PSNR={best_psnr:.f} dB")

            if avg_ssim > best_ssim and avg_ssim > :
                best_ssim = avg_ssim
                best_ssim_path = os.path.join(best_dir, f"best_{dataset_type}_ssim_epoch_{current_train_epoch}.pth")
                torch.save({
                    "epoch": current_train_epoch,
                    "model_state_dict": model.state_dict(),
                    "best_ssim": best_ssim,
                    "current_metrics": {
                        "loss": avg_loss,
                        "psnr": avg_psnr,
                        "lpips": avg_lpips
                    }
                }, best_ssim_path)
                print(f" 保存最佳SSIM模型：{best_ssim_path} | 最佳SSIM={best_ssim:.f}")

            if avg_lpips < best_lpips and avg_lpips > :
                best_lpips = avg_lpips
                best_lpips_path = os.path.join(best_dir, f"best_{dataset_type}_lpips_epoch_{current_train_epoch}.pth")
                torch.save({
                    "epoch": current_train_epoch,
                    "model_state_dict": model.state_dict(),
                    "best_lpips": best_lpips,
                    "current_metrics": {
                        "loss": avg_loss,
                        "psnr": avg_psnr,
                        "ssim": avg_ssim
                    }
                }, best_lpips_path)
                print(f" 保存最佳LPIPS模型：{best_lpips_path} | 最佳LPIPS={best_lpips:.f}")

             记录TensorBoard日志
            tb_logger.log_epoch_metrics(dataset_type, current_train_epoch, avg_loss, avg_psnr, avg_ssim, avg_lpips, current_lr)
            print(f" TensorBoard日志记录 - Epoch {current_train_epoch}: Loss={avg_loss:.f}, PSNR={avg_psnr:.f}, SSIM={avg_ssim:.f}, LPIPS={avg_lpips:.f}, LR={current_lr:.f}")

             早停判断
            if early_stopping(avg_psnr, avg_ssim, avg_lpips):
                print(f" 触发早停，停止{dataset_type}训练")
                print(f" 早停时最佳指标 - Loss: {best_loss:.f} | PSNR: {best_psnr:.f} | SSIM: {best_ssim:.f} | LPIPS: {best_lpips:.f}")
                break

             紧急保存
            if current_train_epoch %  == :
                torch.save({
                    'epoch': current_train_epoch,
                    'model_state_dict': model.state_dict(),
                    'optimizer_state_dict': optimizer.state_dict(),
                    'scheduler_state_dict': scheduler.state_dict(),
                    'current_best': {
                        "loss": best_loss,
                        "psnr": best_psnr,
                        "ssim": best_ssim,
                        "lpips": best_lpips
                    }
                }, emergency_ckpt_path)
                print(f" 保存紧急备份模型：{emergency_ckpt_path} | 累计训练{current_train_epoch}轮")

         训练结束
        print(f"\n {dataset_type}训练完成！")
        print(f" 最终最佳指标 - Loss: {best_loss:.f} | PSNR: {best_psnr:.f} dB | SSIM: {best_ssim:.f} | LPIPS: {best_lpips:.f}")

    except Exception as e:
        print(f"\n {dataset_type}训练出错：{str(e)}")
        import traceback
        traceback.print_exc()

         紧急保存
        torch.save({
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict() if 'optimizer' in locals() else None,
            'scheduler_state_dict': scheduler.state_dict() if 'scheduler' in locals() else None,
            'error': str(e),
            'error_type': type(e).__name__,
            'epoch': epoch,
            'current_best': {
                "loss": best_loss,
                "psnr": best_psnr,
                "ssim": best_ssim,
                "lpips": best_lpips
            }
        }, emergency_ckpt_path)
        print(f" 训练异常，已保存紧急备份模型：{emergency_ckpt_path}")

    finally:
        print(f"\n {dataset_type}训练日志已关闭，保存到：{log_file}")
        logger.close()
        sys.stdout = logger.terminal

 ==============================================================================
 . 新增测试模块
 ==============================================================================
def save_image(tensor, save_path):
    """将张量保存为图像"""
     张量转PIL图像
    tensor = tensor.squeeze().cpu()   去除batch维度
    tensor = torch.clamp(tensor, ., .)
    if tensor.shape[] == :
         单通道CT图像
        img = transforms.ToPILImage()(tensor).convert('L')
    else:
         三通道RGB图像
        img = transforms.ToPILImage()(tensor)
    img.save(save_path)
    print(f" 图像已保存：{save_path}")


def test_model(model_path, dataset_type, tb_logger, sample_ratio=.):
    """
    适配H+RTX Mobile的测试函数
    Args:
        model_path: 模型权重路径
        dataset_type: 测试数据集类型（luna_ct/covid_ct/voc_rgb）
        tb_logger: TensorBoard日志器
        sample_ratio: 测试集采样比例（.=%，.=全量，LUNA建议设.）
    """
     初始化日志
    test_log_file = os.path.join(OUTPUT_DETAIL_DIR, f"{dataset_type}_test_log.txt")
    test_logger = Logger(test_log_file)
    sys.stdout = test_logger
    print(f"\n===== 开始测试{dataset_type}模型（适配H+RTX Mobile） =====")
    print(f" 测试日志保存到：{test_log_file}")
    print(f" 测试模型路径：{model_path} | 测试集采样比例：{sample_ratio}")

     加载测试数据集
    test_loaders = load_test_datasets()
    test_loader = test_loaders[dataset_type]
    
      核心优化：测试集采样（LUNA建议设.，快速出结果）
    if sample_ratio < . and dataset_type == "luna_ct":
         提取测试集的所有样本路径，采样后重新构建数据集
        full_test_set = test_loader.dataset
        sample_size = int(len(full_test_set)  sample_ratio)
        sampled_indices = list(range(sample_size))   取前N张，也可以随机采样
        sampled_test_set = torch.utils.data.Subset(full_test_set, sampled_indices)
         重新创建适配硬件的DataLoader
        test_loader = DataLoader(
            sampled_test_set,
            batch_size=,
            shuffle=False,
            num_workers=,                适配H：测试集用核，不抢资源
            pin_memory=True,              加速CPU→GPU拷贝（移动端GPU收益大）
            persistent_workers=True,      子进程全程存活，只创建一次
            prefetch_factor=             提前加载批，GPU不等待
        )
        print(f" LUNA测试集采样：{len(full_test_set)} → {sample_size} 张")

     初始化模型（ 核心优化：显存友好模式）
    in_channels =  if "ct" in dataset_type else 
    model = LUMWCNN(in_channels=in_channels, scale=SCALE).to(DEVICE)
    
     加载模型权重（避免显存峰值）
    checkpoint = torch.load(model_path, map_location=DEVICE, weights_only=True)
    if "model_state_dict" in checkpoint:
        model.load_state_dict(checkpoint["model_state_dict"])
    else:
        model.load_state_dict(checkpoint)
    
      核心优化：测试模式（禁用梯度+推理优化）
    model.eval()   关闭BN/Dropout，避免测试波动
    torch.cuda.empty_cache()   清空显存缓存
    torch.backends.cudnn.benchmark = True   开启cudnn优化，推理更快

     初始化测试指标
    total_psnr, total_ssim, total_lpips, total_cnt = ., ., ., 
    test_pbar = tqdm(test_loader, desc=f"测试 {dataset_type} (适配H+RTX)")

     创建测试输出子目录
    dataset_test_dir = os.path.join(TEST_OUTPUT_DIR, dataset_type)
    os.makedirs(dataset_test_dir, exist_ok=True)

      核心优化：无梯度推理（显存占用减半）
    with torch.no_grad():
        for idx, (lr_img, hr_img) in enumerate(test_pbar):
            try:
                lr_img, hr_img = lr_img.to(DEVICE, non_blocking=True), hr_img.to(DEVICE, non_blocking=True)
                 模型推理（non_blocking=True加速拷贝）
                sr_img = model(lr_img)
                 对齐尺寸
                sr_img, hr_img = model._align_tensor_size(sr_img, hr_img)
                
                 计算指标
                psnr, ssim_val, lpips_val = tb_logger.calculate_metrics(sr_img, hr_img)
                total_psnr += psnr
                total_ssim += ssim_val
                total_lpips += lpips_val
                total_cnt += 

                 更新进度条
                test_pbar.set_postfix({
                    "PSNR": f"{psnr:.f}",
                    "SSIM": f"{ssim_val:.f}",
                    "LPIPS": f"{lpips_val:.f}",
                    "累计PSNR": f"{total_psnr/total_cnt:.f}"
                })

                  核心优化：批量保存结果（每张存次，节省时间/空间）
                if idx ==  or idx %  == :
                    img_name = f"test_{idx:d}"
                     保存低分辨率图
                    lr_save_path = os.path.join(dataset_test_dir, f"{img_name}_lr.png")
                    save_image(lr_img, lr_save_path)
                     保存超分图
                    sr_save_path = os.path.join(dataset_test_dir, f"{img_name}_sr.png")
                    save_image(sr_img, sr_save_path)
                     保存高清原图
                    hr_save_path = os.path.join(dataset_test_dir, f"{img_name}_hr.png")
                    save_image(hr_img, hr_save_path)

            except Exception as e:
                print(f"\n️  测试样本{idx}出错：{e}，跳过")
                continue
            finally:
                 每轮清理显存，避免移动端GPU溢出
                torch.cuda.empty_cache()

     计算平均指标
    if total_cnt > :
        avg_psnr = total_psnr / total_cnt
        avg_ssim = total_ssim / total_cnt
        avg_lpips = total_lpips / total_cnt
    else:
        avg_psnr = avg_ssim = avg_lpips = .

     打印测试结果
    print(f"\n===== {dataset_type}测试完成（适配H+RTX） =====")
    print(f" 测试样本数：{total_cnt}")
    print(f" 平均指标 - PSNR: {avg_psnr:.f} | SSIM: {avg_ssim:.f} | LPIPS: {avg_lpips:.f}")
    
     记录测试指标到TensorBoard
    tb_logger.get_writer(f"{dataset_type}_test")
    tb_logger.log_epoch_metrics(f"{dataset_type}_test", , , avg_psnr, avg_ssim, avg_lpips, )

     收尾：清理资源
    torch.cuda.empty_cache()
    test_logger.close()
    sys.stdout = test_logger.terminal
    print(f" {dataset_type}测试完成，显存已清理")

  测试各数据集的最佳模型（核心修改：LUNA测试采样%+容错处理
def find_best_ckpt(prefix):
    """容错版找最佳模型：避免找不到文件报错"""
    ckpt_list = [f for f in os.listdir(CHECKPOINT_DIR) if f.startswith(prefix)]
    if not ckpt_list:
        print(f"️  未找到{prefix}开头的模型文件，跳过测试")
        return None
    return ckpt_list[-]   取最后一个（最新的）最佳模型


 ==============================================================================
 . 主函数（训练+测试入口）
 ==============================================================================
if __name__ == "__main__":
     ========== 硬件优化：强制使用RTX独显（适配你的H+RTX Mobile） ==========
    os.environ["CUDA_VISIBLE_DEVICES"] = ""   屏蔽AMD核显，只用NVIDIA独显
    torch.backends.cudnn.benchmark = True      开启cudnn优化，训练/推理更快
    torch.cuda.empty_cache()                   初始化显存

     初始化TensorBoard日志器
    tb_logger = TBLogger()

     ========== . 加载训练数据集（核心修改：LUNA采样%，压减训练时长） ==========
     luna_sample_ratio=.：只训%的LUNA样本，单轮分钟左右；后续想全量训改.即可
    train_loaders = load_datasets(luna_sample_ratio=.)

     . 初始化模型
    model = LUMWCNN(scale=SCALE).to(DEVICE)

     . 依次训练各数据集（流程不变，适配采样后的loader）
     训练LUNA CT数据集（采样后分钟/轮，效率拉满）
    train_continual(model, train_loaders["luna_ct"], DEEPLESION_CKPT, "luna_ct", tb_logger)
     训练COVID CT数据集（样本少，全量训仅需几分钟）
    train_continual(model, train_loaders["covid_ct"], DEEPLESION_CKPT, "covid_ct", tb_logger)
    训练divk数据集（这次是真rgb模型和完整模型状态参数)
    train_continual(model, train_loaders["divk_rgb"], None, "divk_rgb", tb_logger) 
     训练VOC RGB数据集（样本少，全量训仅需十几分钟）
    train_continual(model, train_loaders["voc_rgb"], _, "voc_rgb", tb_logger)

   
     查找各数据集最佳模型（容错版）
    luna_best_ckpt = find_best_ckpt("best_luna_ct_loss")
    covid_best_ckpt = find_best_ckpt("best_covid_ct_loss")
    divk_best_ckpt = find_best_ckpt("best_divk_rgb_loss")
    voc_best_ckpt = find_best_ckpt("best_voc_rgb_loss")

     测试LUNA模型（采样%，快速出结果，适配你的硬件）
    '''
    if luna_best_ckpt:
        test_model(
            os.path.join(CHECKPOINT_DIR, luna_best_ckpt),
            "luna_ct",
            tb_logger,
            sample_ratio=.   测试采样%，分钟出结果
        )
    '''
     测试COVID模型（全量，样本少）
    if covid_best_ckpt:
        test_model(os.path.join(CHECKPOINT_DIR, covid_best_ckpt), "covid_ct", tb_logger)
    if divk_best_ckpt:
        test_model(os.path.join(CHECKPOINT_DIR, divk_best_ckpt), "divk_rgb", tb_logger)
     测试VOC模型（全量，样本少）
    if voc_best_ckpt:
        test_model(os.path.join(CHECKPOINT_DIR, voc_best_ckpt), "voc_rgb", tb_logger)

     关闭TensorBoard日志器
    tb_logger.close_all()
    print("\n 所有训练和测试任务完成！")
