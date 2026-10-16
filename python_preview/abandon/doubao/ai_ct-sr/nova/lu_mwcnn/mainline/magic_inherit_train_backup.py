import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import transforms
import numpy as np
from tqdm import tqdm
from PIL import Image
import sys
import os.path as path
import torch.nn.functional as F
from torch.utils.tensorboard.writer import SummaryWriter
import lpips
import warnings
warnings.filterwarnings('ignore')

 ========== 全局配置（请根据你的路径修改！） ==========
 预训练权重路径
DEEPLESION_CKPT = "./output_deeplesion/deeplesion_resume_ckpt/best_model.pth"
DIVK_CKPT = "./output_divk/divk_resume_ckpt/best_model.pth"

 数据集路径
LUNA_DATA_DIR = "/home/dake/Documents/Projects/datasets/LUNA/sr_slice_dataset/"
VOC_DATA_DIR = "/home/dake/Documents/Projects/datasets/VOC/sr_split/"
COVID_DATA_DIR = "/home/dake/Documents/Projects/datasets/COVID-CT/COVID-CT-Images/"

 训练配置（固定）
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
SCALE = 
BATCH_SIZE = 
LR = e-
EPOCHS = 
FREEZE_BACKBONE_EPOCHS = 
EARLY_STOPPING_PATIENCE = 
EARLY_STOPPING_MIN_DELTA = e-
CHECKPOINT_DIR = "./continual_ckpt"
os.makedirs(CHECKPOINT_DIR, exist_ok=True)

 ========== 小波变换模块 ==========
class DWT_Haar(nn.Module):
    def forward(self, x):
        B, C, H, W = x.shape
        assert H %  ==  and W %  == , f"输入尺寸{H}x{W}必须是的倍数"
        x = x.reshape(B, C, H // , , W // , )
        x = x.permute(, , , , , ).contiguous()
        return x.view(B, C  , H // , W // ).to(x.device)

class IWT_Haar(nn.Module):
    def forward(self, x):
        B, C, H, W = x.shape
        assert C %  == , f"输入通道数{C}必须是的倍数"
        x = x.view(B, C // , , , H, W)
        x = x.permute(, , , , , ).contiguous()
        return x.view(B, C // , H  , W  ).to(x.device)

 ========== 卷积模块 ==========
class Convd(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, kernel_size: int, act: bool = True) -> None:
        super(Convd, self).__init__()
        layer_list = [nn.Convd(in_ch, out_ch, kernel_size, padding=kernel_size//)]
        if act:
            layer_list.append(nn.ReLU())
        self.model = nn.Sequential(layer_list)

    def forward(self, x):
        return self.model(x).to(x.device)

 ========== LUMWCNN主模型 ==========
class LUMWCNN(nn.Module):
    def __init__(self, in_channels: int = , device=None, scale=) -> None:
        super(LUMWCNN, self).__init__()
        self.device = device or torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.in_channels = in_channels
        self.scale = scale
        assert self.in_channels in [, ], "in_channels仅支持/"

        self.DWT = DWT_Haar().to(self.device)
        self.IWT = IWT_Haar().to(self.device)

         左分支
        self.l_conv = nn.Sequential(Convd(self.in_channels, , ), Convd(, , )).to(self.device)
        self.l_conv = nn.Sequential(Convd(, , ), Convd(, , )).to(self.device)
        self.l_conv = nn.Sequential(Convd(, , ), Convd(, , )).to(self.device)

         右分支
        self.r_conv = nn.Sequential(Convd(, , ), Convd(, , )).to(self.device)
        self.r_conv = nn.Sequential(Convd(, , ), Convd(, , )).to(self.device)
        self.r_conv = nn.Sequential(Convd(, , ), Convd(, self.in_channels, )).to(self.device)

         上采样
        if self.scale == :
            self.upsample = nn.Sequential(nn.Convd(in_channels, in_channels, , ), nn.PixelShuffle()).to(self.device)
        elif self.scale == :
            self.upsample = nn.Sequential(
                nn.Convd(in_channels, in_channels, , ), nn.PixelShuffle(),
                nn.Convd(in_channels, in_channels, , ), nn.PixelShuffle()
            ).to(self.device)

        self.pads = []

    def _align_tensor_size(self, tensor_a, tensor_b):
        min_h = min(tensor_a.shape[], tensor_b.shape[])
        min_w = min(tensor_a.shape[], tensor_b.shape[])
        return tensor_a[:, :, :min_h, :min_w], tensor_b[:, :, :min_h, :min_w]

    def wavelet_pad(self, x):
        pad_h =  if x.shape[-]% != else 
        pad_w =  if x.shape[-]% != else 
        self.pads.append([pad_w, pad_h])
        return F.pad(x, (pad_w,,pad_h,), 'constant', )

    def wavelet_shave(self, x):
        if not self.pads:
            return x
        pad_w, pad_h = self.pads.pop()
        if pad_w: x = x[:, :, :, :]
        if pad_h: x = x[:, :, :, :]
        return x

    def forward(self, x):
        x = x.to(self.device)

         通道适配
        if x.shape[]== and self.in_channels==:
            x = x.repeat(,,,)
        elif x.shape[]== and self.in_channels==:
            x = torch.mean(x, dim=, keepdim=True)

         左分支
        x_l = self.l_conv(x)
        x_l_pad = self.wavelet_pad(x_l)
        _x_l = self.DWT(x_l_pad)
        x_l = self.l_conv(_x_l)
        x_l_pad = self.wavelet_pad(x_l)
        _x_l = self.DWT(x_l_pad)
        x_l = self.l_conv(_x_l)

         右分支
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

         上采样
        y = self.upsample(x_r)
        return y

 ========== 早停机制 ==========
class EarlyStopping:
    def __init__(self, patience=, min_delta=e-, mode='min', verbose=True):
        self.patience = patience
        self.min_delta = min_delta
        self.mode = mode
        self.verbose = verbose
        self.counter = 
        self.best_score = None
        self.early_stop = False

    def __call__(self, score):
        if self.best_score is None:
            self.best_score = score
        else:
            improve = score < (self.best_score - self.min_delta) if self.mode=='min' else score > (self.best_score + self.min_delta)
            if improve:
                self.best_score = score
                self.counter = 
            else:
                self.counter += 
                if self.verbose:
                    print(f"EarlyStopping counter: {self.counter}/{self.patience}")
                if self.counter >= self.patience:
                    self.early_stop = True
                    if self.verbose:
                        print("Early stopping triggered!")
        return self.early_stop

 ========== TB日志器（修正log_dir参数） ==========
class TBLogger:
    def __init__(self, log_dir="./tb_logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.writers = {}
        self.lpips_model = lpips.LPIPS(net='vgg').eval().to(DEVICE)

    def get_writer(self, dataset_type):
        if dataset_type not in self.writers:
            writer_dir = os.path.join(self.log_dir, dataset_type)
            self.writers[dataset_type] = SummaryWriter(log_dir=writer_dir)
        return self.writers[dataset_type]

    
    def calculate_metrics(self, sr_img, hr_img):
        sr_img = sr_img.float().to(DEVICE)
        hr_img = hr_img.float().to(DEVICE)

         PSNR
        mse = F.mse_loss(sr_img, hr_img)
        psnr =   torch.log(. / mse) if mse != else float('inf')

         SSIM（修复变量未定义错误）
        def ssim(x, y):
            pad = 
            x = F.pad(x, (pad,pad,pad,pad), 'reflect')
            y = F.pad(y, (pad,pad,pad,pad), 'reflect')
             生成高斯核
            win = torch.exp(-(torch.arange().to(x.device)-) / (.))
            win = win.unsqueeze()win.unsqueeze()
            win = win.unsqueeze().unsqueeze().repeat(x.shape[],,,)

             正确顺序定义变量
            mu_x = F.convd(x, win, groups=x.shape[], padding=)
            mu_y = F.convd(y, win, groups=y.shape[], padding=)
            mu_xy = mu_x  mu_y
            mu_x = mu_x 
            mu_y = mu_y 
            
            sigma_x = F.convd(x, win, groups=x.shape[], padding=) - mu_x
            sigma_y = F.convd(y, win, groups=y.shape[], padding=) - mu_y
            sigma_xy = F.convd(xy, win, groups=x.shape[], padding=) - mu_xy
            C, C = (.), (.)
            ssim_map = ((mu_xy+C)(sigma_xy+C)) / ((mu_x+mu_y+C)(sigma_x+sigma_y+C))
            return ssim_map.mean()

        ssim_val = ssim(sr_img, hr_img)

         LPIPS
        if sr_img.shape[]==:
            sr_lpips = sr_img.repeat(,,,)
            hr_lpips = hr_img.repeat(,,,)
        else:
            sr_lpips, hr_lpips = sr_img, hr_img
        lpips_val = self.lpips_model(sr_lpips, hr_lpips).mean()

        return psnr.item(), ssim_val.item(), lpips_val.item()

    def log_epoch_metrics(self, dataset_type, epoch, loss, psnr, ssim, lpips, lr):
        writer = self.get_writer(dataset_type)
        writer.add_scalar('train/epoch_loss', loss, epoch)
        writer.add_scalar('train/epoch_psnr', psnr, epoch)
        writer.add_scalar('train/epoch_ssim', ssim, epoch)
        writer.add_scalar('train/epoch_lpips', lpips, epoch)
        writer.add_scalar('train/lr', lr, epoch)

    def log_weights(self, dataset_type, model, epoch):
        writer = self.get_writer(dataset_type)
        for name, param in model.named_parameters():
            writer.add_histogram(f'weights/{name}', param, epoch)
            if param.grad is not None:
                writer.add_histogram(f'grads/{name}', param.grad, epoch)

    def close_all(self):
        for writer in self.writers.values():
            writer.close()

 ========== 数据集定义 ==========
class ResizeIfSmaller(object):
    def __init__(self, min_size):
        self.min_size = min_size

    def __call__(self, img):
        w, h = img.size
        scale = max(self.min_size/w, self.min_size/h, .)
        new_w = int(wscale)
        new_h = int(hscale)
        new_w = new_w if new_w%== else new_w+
        new_h = new_h if new_h%== else new_h+
        if new_w !=w or new_h!=h:
            img = img.resize((new_w, new_h), Image.BICUBIC)
        return img

class LUNADataset(torch.utils.data.Dataset):
    def __init__(self, data_dir, transform=None):
        self.img_paths = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".png")]
        self.transform = transform

    def __getitem__(self, idx):
        img = Image.open(self.img_paths[idx]).convert('L')
        if self.transform:
            img = self.transform(img)
        hr_h, hr_w = img.size(), img.size()
        lr_h, lr_w = (hr_h//SCALE)SCALE, (hr_w//SCALE)SCALE
        img = img[:, :lr_h, :lr_w]
        lr_img = transforms.Resize((hr_h//SCALE, hr_w//SCALE), Image.BICUBIC)(img)
        return lr_img, img

    def __len__(self):
        return len(self.img_paths)

class COVIDDataset(torch.utils.data.Dataset):
    def __init__(self, data_dir, transform=None):
        self.img_paths = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".png")]
        self.transform = transform

    def __getitem__(self, idx):
        img = Image.open(self.img_paths[idx]).convert('L')
        if self.transform:
            img = self.transform(img)
        hr_h, hr_w = img.size(), img.size()
        lr_h, lr_w = (hr_h//SCALE)SCALE, (hr_w//SCALE)SCALE
        img = img[:, :lr_h, :lr_w]
        lr_img = transforms.Resize((hr_h//SCALE, hr_w//SCALE), Image.BICUBIC)(img)
        return lr_img, img

    def __len__(self):
        return len(self.img_paths)

class VOCDataset(torch.utils.data.Dataset):
    def __init__(self, data_dir, transform=None):
        self.img_paths = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".jpg")]
        self.transform = transform

    def __getitem__(self, idx):
        try:
            img = Image.open(self.img_paths[idx]).convert('RGB')
            w, h = img.size
            if w< or h< or w%!= or h%!=:
                scale = max(/w, /h, .)
                new_w = int(wscale)
                new_h = int(hscale)
                new_w = new_w if new_w%== else new_w+
                new_h = new_h if new_h%== else new_h+
                img = img.resize((new_w, new_h), Image.BICUBIC)
            if self.transform:
                img = self.transform(img)
            hr_h, hr_w = img.size(), img.size()
            lr_h, lr_w = (hr_h//SCALE)SCALE, (hr_w//SCALE)SCALE
            img = img[:, :lr_h, :lr_w]
            lr_img = transforms.Resize((hr_h//SCALE, hr_w//SCALE), Image.BICUBIC)(img)
            return lr_img, img
        except:
            return self.__getitem__()

    def __len__(self):
        return len(self.img_paths)

 ========== 数据加载 ==========
ct_transform = transforms.Compose([
    ResizeIfSmaller(),
    transforms.RandomCrop(),
    transforms.RandomHorizontalFlip(p=.),
    transforms.ToTensor()
])

rgb_transform = transforms.Compose([
    ResizeIfSmaller(),
    transforms.RandomCrop(),
    transforms.RandomHorizontalFlip(p=.),
    transforms.ToTensor()
])

 构建DataLoader
luna_train_set = LUNADataset(os.path.join(LUNA_DATA_DIR, "train"), ct_transform)
luna_train_loader = DataLoader(luna_train_set, batch_size=BATCH_SIZE, shuffle=True, num_workers=)

covid_train_set = COVIDDataset(os.path.join(COVID_DATA_DIR, "postive"), ct_transform)
covid_train_loader = DataLoader(covid_train_set, batch_size=BATCH_SIZE, shuffle=True, num_workers=)

voc_train_set = VOCDataset(os.path.join(VOC_DATA_DIR, "train/img"), rgb_transform)
voc_train_loader = DataLoader(voc_train_set, batch_size=BATCH_SIZE, shuffle=True, num_workers=)

 ========== 权重加载（兼容DeepLesion/DIVK） ==========
def load_pretrained_weights(model, pretrain_ckpt, in_channels):
    if not os.path.exists(pretrain_ckpt):
        raise FileNotFoundError(f"预训练权重不存在：{pretrain_ckpt}")

    checkpoint = torch.load(pretrain_ckpt, map_location=DEVICE, weights_only=False)
    pretrain_dict = checkpoint["model_state_dict"] if "model_state_dict" in checkpoint else checkpoint
    
     统一处理：移除module前缀 + 过滤BN参数 + layers→model映射
    pretrain_dict = {k.replace('module.', ''): v for k, v in pretrain_dict.items()}
    pretrain_dict = {k.replace('.layers.', '.model.'): v for k, v in pretrain_dict.items()}
    pretrain_tensor_dict = {
        k: v for k, v in pretrain_dict.items()
        if isinstance(v, torch.Tensor) and not any(x in k for x in ['running_mean', 'running_var', 'num_batches_tracked'])
    }

     通道适配
    target_key = 'l_conv..model..weight'
    if target_key in pretrain_tensor_dict:
        pretrain_in_ch = pretrain_tensor_dict[target_key].shape[]
        if pretrain_in_ch != in_channels:
            print(f"️  通道适配：{pretrain_in_ch}→{in_channels}")
            if pretrain_in_ch == and in_channels==:
                pretrain_tensor_dict[target_key] = pretrain_tensor_dict[target_key].repeat(,,,)
            elif pretrain_in_ch == and in_channels==:
                pretrain_tensor_dict[target_key] = pretrain_tensor_dict[target_key].mean(dim=, keepdim=True)

     匹配参数
    model_dict = model.state_dict()
    matched_dict = {k:v for k,v in pretrain_tensor_dict.items() if k in model_dict and model_dict[k].shape==v.shape}
    model_dict.update(matched_dict)
    model.load_state_dict(model_dict, strict=False)
    print(f" 加载预训练权重：匹配{len(matched_dict)}层")
    return model

 ========== 断点加载（修复优化器冲突） ==========
def load_checkpoint(model, optimizer, dataset_type):
    checkpoint_path = os.path.join(CHECKPOINT_DIR, f"{dataset_type}_checkpoint.pth")
    if not os.path.exists(checkpoint_path):
        print(f"️  无断点文件，从头训练")
        return model, optimizer, , float('inf'), ., ., float('inf')
    
    checkpoint = torch.load(checkpoint_path, map_location=DEVICE)
    model.load_state_dict(checkpoint['model_state_dict'])
    
     兼容优化器参数组不匹配
    opt_state = checkpoint['optimizer_state_dict']
    new_opt_state = optimizer.state_dict()
    new_opt_state['state'] = opt_state['state']
    if 'param_groups' in opt_state:
        new_opt_state['param_groups'][]['lr'] = opt_state['param_groups'][]['lr']
    optimizer.load_state_dict(new_opt_state)

    start_epoch = checkpoint['epoch']
    best_loss = checkpoint['best_loss']
    best_psnr = checkpoint['best_psnr']
    best_ssim = checkpoint['best_ssim']
    best_lpips = checkpoint['best_lpips']
    
    print(f" 加载断点：从第{start_epoch+}轮开始")
    return model, optimizer, start_epoch, best_loss, best_psnr, best_ssim, best_lpips

 ========== 训练函数 ==========
def train_continual(model, train_loader, pretrain_ckpt, dataset_type, tb_logger):
     加载预训练权重
    checkpoint_path = os.path.join(CHECKPOINT_DIR, f"{dataset_type}_checkpoint.pth")
    in_channels =  if "ct" in dataset_type else 
    model = load_pretrained_weights(model, pretrain_ckpt, in_channels)

     冻结主干
    freeze_layers = [model.l_conv, model.l_conv, model.l_conv]
    for layer in freeze_layers:
        for param in layer.parameters():
            param.requires_grad = False
    print(f" 前{FREEZE_BACKBONE_EPOCHS}轮冻结主干")

     初始化优化器 + 加载断点
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=LR)
    model, optimizer, start_epoch, best_loss, best_psnr, best_ssim, best_lpips = load_checkpoint(model, optimizer, dataset_type)

     早停 + 损失函数
    early_stopping = EarlyStopping(patience=EARLY_STOPPING_PATIENCE, min_delta=EARLY_STOPPING_MIN_DELTA)
    criterion = nn.LLoss()

     训练循环
    model.train()
    for epoch in range(start_epoch, EPOCHS):
         解冻主干（仅一次）
        if epoch == FREEZE_BACKBONE_EPOCHS:
            for layer in freeze_layers:
                for param in layer.parameters():
                    param.requires_grad = True
            optimizer = optim.Adam(model.parameters(), lr=LR)
            print(" 解冻主干，全量训练")

         本轮指标初始化
        epoch_loss, epoch_psnr, epoch_ssim, epoch_lpips, cnt = ., ., ., ., 
        pbar = tqdm(train_loader, desc=f"[{dataset_type}] Epoch {epoch+}/{EPOCHS}")

        for lr_img, hr_img in pbar:
            try:
                lr_img, hr_img = lr_img.to(DEVICE), hr_img.to(DEVICE)
                sr_img = model(lr_img)
                sr_img, hr_img = model._align_tensor_size(sr_img, hr_img)
                loss = criterion(sr_img, hr_img)

                 反向传播
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                 计算指标
                psnr, ssim_val, lpips_val = tb_logger.calculate_metrics(sr_img, hr_img)
                epoch_loss += loss.item()
                epoch_psnr += psnr
                epoch_ssim += ssim_val
                epoch_lpips += lpips_val
                cnt += 

                 更新进度条
                pbar.set_postfix({"Loss": f"{loss.item():.f}", "PSNR": f"{psnr:.f}"})
            except Exception as e:
                print(f"️  批次出错：{e}，跳过")
                continue

         计算本轮平均指标
        if cnt >:
            avg_loss = epoch_loss/cnt
            avg_psnr = epoch_psnr/cnt
            avg_ssim = epoch_ssim/cnt
            avg_lpips = epoch_lpips/cnt
        else:
            avg_loss, avg_psnr, avg_ssim, avg_lpips = ,,,

         记录TB日志
        current_lr = optimizer.param_groups[]['lr']
        tb_logger.log_epoch_metrics(dataset_type, epoch+, avg_loss, avg_psnr, avg_ssim, avg_lpips, current_lr)
        if (epoch+)% ==:
            tb_logger.log_weights(dataset_type, model, epoch+)

         打印结果
        print(f"\n[{dataset_type}] Epoch {epoch+}：Loss={avg_loss:.f}, PSNR={avg_psnr:.f}, SSIM={avg_ssim:.f}, LPIPS={avg_lpips:.f}")

         保存断点
        torch.save({
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'loss': avg_loss,
            'best_loss': best_loss,
            'best_psnr': best_psnr,
            'best_ssim': best_ssim,
            'best_lpips': best_lpips
        }, checkpoint_path)

         保存最优权重
        if avg_loss < best_loss and avg_loss>:
            best_loss, best_psnr, best_ssim, best_lpips = avg_loss, avg_psnr, avg_ssim, avg_lpips
            torch.save({
                'epoch': epoch+,
                'model_state_dict': model.state_dict(),
                'best_loss': best_loss,
                'best_psnr': best_psnr,
                'best_ssim': best_ssim,
                'best_lpips': best_lpips
            }, os.path.join(CHECKPOINT_DIR, f"lumwcnn_{dataset_type}_best.pth"))
            print(f" 保存最优权重：Loss={best_loss:.f}")

         早停判断
        if early_stopping(avg_loss):
            print(f" {dataset_type} 早停")
            break

 ========== 主函数 ==========
if __name__ == "__main__":
    print(f" 设备：{DEVICE} | GPU：{torch.cuda.get_device_name() if DEVICE.type=='cuda' else 'CPU'}")
    tb_logger = TBLogger(log_dir="./tb_logs")

    try:
         . 训练LUNA
        print("\n===== 训练LUNA =====")
        ct_model = LUMWCNN(in_channels=, device=DEVICE, scale=SCALE)
        train_continual(ct_model, luna_train_loader, DEEPLESION_CKPT, "luna_ct", tb_logger)

         . 训练COVID
        print("\n===== 训练COVID =====")
        covid_model = LUMWCNN(in_channels=, device=DEVICE, scale=SCALE)
        train_continual(covid_model, covid_train_loader, DEEPLESION_CKPT, "covid_ct", tb_logger)

         . 训练VOC
        print("\n===== 训练VOC =====")
        rgb_model = LUMWCNN(in_channels=, device=DEVICE, scale=SCALE)
        train_continual(rgb_model, voc_train_loader, DIVK_CKPT, "voc_rgb", tb_logger)

    finally:
        tb_logger.close_all()
    print("\n 所有数据集训练完成！")
