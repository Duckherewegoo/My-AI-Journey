import os
import random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torch.optim.lr_scheduler import CosineAnnealingLR, ReduceLROnPlateau
from torchvision import transforms
from PIL import Image
import cv
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

 ===================== . 配置参数（适配DeepLesion灰度图） =====================


class Config:
     数据路径
    train_data_root = "/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/train/HR/"   替换为你的训练集路径
    val_data_root = "/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/val/HR/"       替换为你的验证集路径
     训练参数
    batch_size = 
    epochs = 
    lr = e-
    weight_decay = e-
    patience =    早停耐心值
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
     数据增强参数（DIVK核心：渐进式增强）
    max_rotation =    最大旋转角度
    max_scale = .     最大缩放比例
    min_scale = .     最小缩放比例
    crop_size =      裁剪尺寸（灰度图固定单通道）
     保存路径
    save_dir = "./output_deeplesion/deeplesion_train_bravo_ckpt"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

 ===================== . 数据集定义（DeepLesion灰度图） =====================


class DeepLesionDataset(Dataset):
    def __init__(self, data_root, crop_size, is_train=True):
        self.data_root = data_root
        self.crop_size = crop_size
        self.is_train = is_train
         遍历所有灰度图文件（假设为png格式，可根据实际调整）
        self.img_paths = [os.path.join(data_root, f) for f in os.listdir(data_root)
                          if f.endswith((".png", ".jpg", ".jpeg"))]
        assert len(self.img_paths) > , "数据集路径下无有效图片文件！"

    def __len__(self):
        return len(self.img_paths)

    def _random_augment(self, img):
        """
        迁移DIVK数据增强思想：随机旋转、缩放、翻转、裁剪（适配灰度图）
        """
         随机旋转
        angle = random.uniform(-Config.max_rotation, Config.max_rotation)
        rows, cols = img.shape
        M = cv.getRotationMatrixD((cols / , rows / ), angle, )
        img = cv.warpAffine(img, M, (cols, rows),
                             borderMode=cv.BORDER_REFLECT)

         随机缩放
        scale = random.uniform(Config.min_scale, Config.max_scale)
        new_rows, new_cols = int(rows  scale), int(cols  scale)
        img = cv.resize(img, (new_cols, new_rows),
                         interpolation=cv.INTER_LINEAR)

         随机水平/垂直翻转
        if random.random() > .:
            img = cv.flip(img, )   水平翻转
        if random.random() > .:
            img = cv.flip(img, )   垂直翻转

         随机中心裁剪（保证尺寸一致）
        rows, cols = img.shape
        start_row = random.randint(
            , rows - self.crop_size) if rows > self.crop_size else 
        start_col = random.randint(
            , cols - self.crop_size) if cols > self.crop_size else 
        img = img[start_row:start_row + self.crop_size,
                  start_col:start_col + self.crop_size]

        return img

    def __getitem__(self, idx):
        img_path = self.img_paths[idx]
         读取灰度图（强制单通道）
        img = cv.imread(img_path, cv.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"无法读取图片：{img_path}")

         训练阶段增强，验证阶段仅裁剪
        if self.is_train:
            img = self._random_augment(img)
        else:
             验证集：中心裁剪
            rows, cols = img.shape
            start_row = (
                rows - self.crop_size) //  if rows > self.crop_size else 
            start_col = (
                cols - self.crop_size) //  if cols > self.crop_size else 
            img = img[start_row:start_row + self.crop_size,
                      start_col:start_col + self.crop_size]

         归一化 + 转换为tensor（单通道，shape: [, H, W]）
        img = img.astype(np.float) / .
        img = torch.from_numpy(img).unsqueeze()   单通道扩展维度

         模拟"增强任务"：以轻度模糊作为输入，原始图作为标签（可替换为你的实际任务，如超分/去噪）
         DIVK核心：明确的输入-标签对，保证监督信号
        blur_kernel = np.ones((, ), np.float) / 
        img_blur = cv.filterD(img.squeeze().numpy(), -, blur_kernel)
        img_blur = torch.from_numpy(img_blur).unsqueeze()

        return img_blur, img   输入（模糊图）、标签（清晰图）

 ===================== . 模型定义（轻量型CNN，适配灰度图） =====================
 迁移DIVK的网络设计思想：残差连接 + 密集卷积，保证梯度回传和特征复用


class DeepLesionEnhanceNet(nn.Module):
    def __init__(self, in_channels=, out_channels=):
        super().__init__()
         特征提取
        self.feat = nn.Sequential(
            nn.Convd(in_channels, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
        )
         残差融合
        self.residual = nn.Convd(, out_channels, kernel_size=, padding=)
        self.skip = nn.Convd(in_channels, out_channels, kernel_size=)   跳跃连接

    def forward(self, x):
        feat = self.feat(x)
        res = self.residual(feat)
        skip = self.skip(x)
        return res + skip   残差输出

 ===================== . 损失函数（DIVK核心：MSE+感知损失，适配灰度图） =====================


class PerceptualLoss(nn.Module):
    """简化版感知损失（灰度图适配）"""

    def __init__(self):
        super().__init__()
         提取浅层特征作为感知度量
        self.feature_extractor = nn.Sequential(
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True)
        ).to(Config.device)
         冻结特征提取器
        for param in self.feature_extractor.parameters():
            param.requires_grad = False

    def forward(self, pred, target):
        pred_feat = self.feature_extractor(pred)
        target_feat = self.feature_extractor(target)
        return nn.MSELoss()(pred_feat, target_feat)

 联合损失：MSE（保证PSNR） + 感知损失（保证视觉效果）


class JointLoss(nn.Module):
    def __init__(self):
        super().__init__()
        self.mse_loss = nn.MSELoss()
        self.perceptual_loss = PerceptualLoss()

    def forward(self, pred, target):
        mse = self.mse_loss(pred, target)
        perceptual = .  self.perceptual_loss(pred, target)   权重可调
        return mse + perceptual

 ===================== . 训练工具函数（计算PSNR） =====================


def calculate_psnr(pred, target):
    """计算灰度图PSNR（单位：dB）"""
    pred = pred.clamp(, ).detach().cpu().numpy()
    target = target.clamp(, ).detach().cpu().numpy()
    mse = np.mean((pred - target)  )
    if mse == :
        return float('inf')
    return   np.log( / mse)

 ===================== . 核心训练流程（迁移DIVK训练策略） =====================


def train():
     . 构建数据集和加载器
    train_dataset = DeepLesionDataset(
        Config.train_data_root, Config.crop_size, is_train=True)
    val_dataset = DeepLesionDataset(
        Config.val_data_root, Config.crop_size, is_train=False)
    train_loader = DataLoader(
        train_dataset, batch_size=Config.batch_size, shuffle=True, num_workers=)
    val_loader = DataLoader(
        val_dataset, batch_size=Config.batch_size, shuffle=False, num_workers=)

     . 初始化模型、优化器、损失函数、调度器
    model = DeepLesionEnhanceNet().to(Config.device)
    criterion = JointLoss().to(Config.device)
    optimizer = optim.Adam(model.parameters(), lr=Config.lr,
                           weight_decay=Config.weight_decay)
     DIVK核心：余弦退火学习率（比固定LR更易收敛）
    scheduler = CosineAnnealingLR(optimizer, T_max=Config.epochs, eta_min=e-)
     早停策略
    best_psnr = .
    early_stop_count = 

     . 训练循环
    for epoch in range(Config.epochs):
         训练阶段
        model.train()
        train_loss = .
        train_psnr = .
        pbar = tqdm(
            train_loader, desc=f"Epoch {epoch+}/{Config.epochs} [Train]")
        for img_blur, img_gt in pbar:
            img_blur = img_blur.to(Config.device)
            img_gt = img_gt.to(Config.device)

             前向传播
            pred = model(img_blur)
            loss = criterion(pred, img_gt)

             反向传播
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

             计算指标
            train_loss += loss.item()
            batch_psnr = calculate_psnr(pred, img_gt)
            train_psnr += batch_psnr

             更新进度条
            pbar.set_postfix({"loss": train_loss / (pbar.n + ),
                             "psnr": train_psnr / (pbar.n + )})

         验证阶段
        model.eval()
        val_loss = .
        val_psnr = .
        with torch.no_grad():
            pbar = tqdm(
                val_loader, desc=f"Epoch {epoch+}/{Config.epochs} [Val]")
            for img_blur, img_gt in pbar:
                img_blur = img_blur.to(Config.device)
                img_gt = img_gt.to(Config.device)

                pred = model(img_blur)
                loss = criterion(pred, img_gt)

                val_loss += loss.item()
                batch_psnr = calculate_psnr(pred, img_gt)
                val_psnr += batch_psnr

                pbar.set_postfix(
                    {"loss": val_loss / (pbar.n + ), "psnr": val_psnr / (pbar.n + )})

         学习率调度
        scheduler.step()

         早停 + 保存最佳模型
        avg_val_psnr = val_psnr / len(val_loader)
        if avg_val_psnr > best_psnr:
            best_psnr = avg_val_psnr
            early_stop_count = 
             保存最佳模型
            torch.save({
                "epoch": epoch + ,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "best_psnr": best_psnr,
            }, os.path.join(Config.save_dir, "best_model.pth"))
            print(f"保存最佳模型，当前验证集PSNR：{avg_val_psnr:.f} dB")
        else:
            early_stop_count += 
            print(
                f"早停计数：{early_stop_count}/{Config.patience}，当前最佳PSNR：{best_psnr:.f} dB")
            if early_stop_count >= Config.patience:
                print("触发早停，训练结束！")
                break

    print(f"训练完成，最佳验证集PSNR：{best_psnr:.f} dB")


 ===================== . 执行训练 =====================
if __name__ == "__main__":
    train()
