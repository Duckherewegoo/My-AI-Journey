 train_deeplesion_multi.py
import os
import random
import shutil
import numpy as np
import torch
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, ConcatDataset
from torch.optim.lr_scheduler import CosineAnnealingLR
from torchvision import transforms
import cv
from tqdm import tqdm
import warnings
from model import DeepLesionEnhanceNet, JointLoss, calculate_psnr   导入model.py的模块

warnings.filterwarnings('ignore')

 ===================== . 配置参数（多数据集路径 + 基础训练参数） =====================


class Config:
     核心数据集（主体）：DeepLesion_Key_slices
    key_train_root = "/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/train/HR/"
    key_val_root = "/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/val/HR/"
    key_test_root = "/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/test/HR/"

     补充数据集：DeepLesion/lung（划分后路径）
    lung_train_root = "/home/dake/Documents/Projects/datasets/DeepLesion/deeplesion_category_split/lung/train/"
    lung_val_root = "/home/dake/Documents/Projects/datasets/DeepLesion/deeplesion_category_split/lung/val/"
    lung_test_root = "/home/dake/Documents/Projects/datasets/DeepLesion/deeplesion_category_split/lung/test/"

     补充数据集：LUNA
    luna_train_root = "/home/dake/Documents/Projects/datasets/LUNA/sr_slice_dataset/train/"
    luna_val_root = "/home/dake/Documents/Projects/datasets/LUNA/sr_slice_dataset/val/"
    luna_test_root = "/home/dake/Documents/Projects/datasets/LUNA/sr_slice_dataset/test/"

     补充数据集: COVID
    covid_train_root = "/home/dake/Documents/Projects/datasets/COVID-CT/COVID-CT-Images/positive"

     训练参数
    batch_size = 
    epochs = 
    lr = e-
    weight_decay = e-
    patience =    早停耐心值
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

     数据增强参数（适配灰度图）
    max_rotation = 
    max_scale = .
    min_scale = .
    crop_size = 

     保存路径
    save_dir = "./output_deeplesion/deeplesion_multi_train_ckpt"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

 ===================== . 通用数据集类（适配所有灰度医学影像） =====================


class MedicalImageDataset(Dataset):
    def __init__(self, data_roots, crop_size, is_train=True):
        """
        data_roots: 数据集根路径列表（支持多路径融合）
        crop_size: 裁剪尺寸
        is_train: 是否训练阶段（控制数据增强）
        """
        self.crop_size = crop_size
        self.is_train = is_train
        self.img_paths = []

         加载多路径下的所有灰度图
        for root in data_roots:
            if os.path.exists(root):
                img_paths = [os.path.join(root, f) for f in os.listdir(root)
                             if f.endswith((".png", ".jpg", ".jpeg"))]
                self.img_paths.extend(img_paths)

        assert len(self.img_paths) > , "所有数据集路径下无有效图片文件！"
         打乱路径（融合多数据集后打乱）
        random.shuffle(self.img_paths)

    def _random_augment(self, img):
        """灰度图数据增强（迁移DIVK思想，适配医学影像）"""
         随机旋转
        angle = random.uniform(-Config.max_rotation, Config.max_rotation)
        rows, cols = img.shape
        M = cv.getRotationMatrixD((cols / , rows / ), angle, )
        img = cv.warpAffine(img, M, (cols, rows), borderMode=cv.BORDER_REFLECT)

         随机缩放
        scale = random.uniform(Config.min_scale, Config.max_scale)
        new_rows, new_cols = int(rows  scale), int(cols  scale)
        img = cv.resize(img, (new_cols, new_rows), interpolation=cv.INTER_LINEAR)

         随机翻转
        if random.random() > .:
            img = cv.flip(img, )   水平
        if random.random() > .:
            img = cv.flip(img, )   垂直

         随机裁剪
        rows, cols = img.shape
        start_row = random.randint(, rows - self.crop_size) if rows > self.crop_size else 
        start_col = random.randint(, cols - self.crop_size) if cols > self.crop_size else 
        img = img[start_row:start_row + self.crop_size, start_col:start_col + self.crop_size]

        return img

    def __len__(self):
        return len(self.img_paths)

    def __getitem__(self, idx):
        img_path = self.img_paths[idx]
         强制读取单通道灰度图
        img = cv.imread(img_path, cv.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"无法读取图片：{img_path}")

         训练增强/验证仅中心裁剪
        if self.is_train:
            img = self._random_augment(img)
        else:
            rows, cols = img.shape
            start_row = (rows - self.crop_size) //  if rows > self.crop_size else 
            start_col = (cols - self.crop_size) //  if cols > self.crop_size else 
            img = img[start_row:start_row + self.crop_size, start_col:start_col + self.crop_size]

         归一化 + 转tensor（单通道 [, H, W]）
        img = img.astype(np.float) / .
        img = torch.from_numpy(img).unsqueeze()

         构建输入-标签对（模糊图为输入，原图为标签，适配增强/超分任务）
        blur_kernel = np.ones((, ), np.float) / 
        img_blur = cv.filterD(img.squeeze().numpy(), -, blur_kernel)
        img_blur = torch.from_numpy(img_blur).unsqueeze()

        return img_blur, img


 ===================== . 核心训练流程 =====================
def train():
     训练集：Key（主体） + lung + LUNA + covid
    train_dataset = MedicalImageDataset(
        data_roots=[Config.key_train_root, Config.lung_train_root, Config.luna_train_root, Config.covid_train_root],
        crop_size=Config.crop_size,
        is_train=True
    )
     验证集：Key + lung + LUNA
    val_dataset = MedicalImageDataset(
        data_roots=[Config.key_val_root, Config.lung_val_root, Config.luna_val_root],
        crop_size=Config.crop_size,
        is_train=False
    )

     数据加载器
    train_loader = DataLoader(
        train_dataset, batch_size=Config.batch_size, shuffle=True, num_workers=, pin_memory=True
    )
    val_loader = DataLoader(
        val_dataset, batch_size=Config.batch_size, shuffle=False, num_workers=, pin_memory=True
    )

     初始化模型、损失、优化器、调度器
    model = DeepLesionEnhanceNet().to(Config.device)
    criterion = JointLoss(Config.device).to(Config.device)
    optimizer = optim.Adam(model.parameters(), lr=Config.lr, weight_decay=Config.weight_decay)
    scheduler = CosineAnnealingLR(optimizer, T_max=Config.epochs, eta_min=e-)

     早停 + 最佳模型保存
    best_psnr = .
    early_stop_count = 

     训练循环
    for epoch in range(Config.epochs):
         训练阶段
        model.train()
        train_loss = .
        train_psnr = .
        pbar = tqdm(train_loader, desc=f"Epoch {epoch+}/{Config.epochs} [Train]")
        for img_blur, img_gt in pbar:
            img_blur, img_gt = img_blur.to(Config.device), img_gt.to(Config.device)

             前向+反向
            pred = model(img_blur)
            loss = criterion(pred, img_gt)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

             指标计算
            train_loss += loss.item()
            train_psnr += calculate_psnr(pred, img_gt)
            pbar.set_postfix({"loss": train_loss / (pbar.n + ), "psnr": train_psnr / (pbar.n + )})

         验证阶段
        model.eval()
        val_loss = .
        val_psnr = .
        with torch.no_grad():
            pbar = tqdm(val_loader, desc=f"Epoch {epoch+}/{Config.epochs} [Val]")
            for img_blur, img_gt in pbar:
                img_blur, img_gt = img_blur.to(Config.device), img_gt.to(Config.device)

                pred = model(img_blur)
                loss = criterion(pred, img_gt)

                val_loss += loss.item()
                val_psnr += calculate_psnr(pred, img_gt)
                pbar.set_postfix({"loss": val_loss / (pbar.n + ), "psnr": val_psnr / (pbar.n + )})

         学习率更新
        scheduler.step()

         早停判断
        avg_val_psnr = val_psnr / len(val_loader)
        if avg_val_psnr > best_psnr:
            best_psnr = avg_val_psnr
            early_stop_count = 
             保存最佳模型
            torch.save({
                "epoch": epoch + ,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "best_psnr": best_psnr
            }, os.path.join(Config.save_dir, "best_model.pth"))
            print(f"保存最佳模型 | 验证集PSNR: {avg_val_psnr:.f} dB")
        else:
            early_stop_count += 
            print(f"早停计数: {early_stop_count}/{Config.patience} | 最佳PSNR: {best_psnr:.f} dB")
            if early_stop_count >= Config.patience:
                print("触发早停，训练终止！")
                break

    print(f"训练完成 | 最佳验证集PSNR: {best_psnr:.f} dB")


if __name__ == "__main__":
    train()
