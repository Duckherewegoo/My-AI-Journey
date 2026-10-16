import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import transforms
import numpy as np
from tqdm import tqdm

 ========== 核心配置（适配你的路径） ==========
 预训练权重路径
DEEPLESION_CKPT = "/path/to/deeplesion_edsr_pretrain.pth"   DeepLesion预训练权重
DIVK_CKPT = "/path/to/divk_edsr_pretrain.pth"             DIVK预训练权重

 数据集路径
LUNA_DATA_DIR = "/home/dake/Documents/Projects/datasets/LUNA/sr_dataset"
VOC_DATA_DIR = "/path/to/VOC/sr_dataset"

 训练配置（保证泛化性的关键）
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
SCALE =    超分倍数（和之前一致）
BATCH_SIZE = 
LR = e-   续训用低学习率，避免覆盖预训练特征
EPOCHS = 
FREEZE_BACKBONE_EPOCHS =    前轮冻结主干，只训练适配层

 ========== 数据加载（适配CT+通用图像） ==========
 . LUNA（CT灰度图）数据加载


class LUNADataset(torch.utils.data.Dataset):
    def __init__(self, data_dir, transform=None):
        self.img_paths = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".png")]
        self.transform = transform

    def __getitem__(self, idx):
        img_path = self.img_paths[idx]
        img = Image.open(img_path).convert('L')   灰度图（通道）
        if self.transform:
            img = self.transform(img)
         生成低分辨率图（下采样）
        lr_img = transforms.Resize((img.size() // SCALE, img.size() // SCALE), interpolation=Image.BICUBIC)(img)
        return lr_img, img   LR→HR

    def __len__(self):
        return len(self.img_paths)

 . VOC（RGB图）数据加载


class VOCDataset(torch.utils.data.Dataset):
    def __init__(self, data_dir, transform=None):
        self.img_paths = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".jpg")]
        self.transform = transform

    def __getitem__(self, idx):
        img_path = self.img_paths[idx]
        img = Image.open(img_path).convert('RGB')   RGB图（通道）
        if self.transform:
            img = self.transform(img)
         生成低分辨率图
        lr_img = transforms.Resize((img.size() // SCALE, img.size() // SCALE), interpolation=Image.BICUBIC)(img)
        return lr_img, img

    def __len__(self):
        return len(self.img_paths)


 数据增强（提升泛化性）
ct_transform = transforms.Compose([
    transforms.RandomCrop(),   适配CT切片
    transforms.RandomHorizontalFlip(p=.),
    transforms.ToTensor()
])

rgb_transform = transforms.Compose([
    transforms.RandomCrop(),   适配VOC
    transforms.RandomHorizontalFlip(p=.),
    transforms.ToTensor()
])

 构建DataLoader
 LUNA续训（继承DeepLesion预训练）
luna_train_set = LUNADataset(os.path.join(LUNA_DATA_DIR, "train"), ct_transform)
luna_train_loader = DataLoader(luna_train_set, batch_size=BATCH_SIZE, shuffle=True)

 VOC续训（继承DIVK预训练）
voc_train_set = VOCDataset(os.path.join(VOC_DATA_DIR, "train"), rgb_transform)
voc_train_loader = DataLoader(voc_train_set, batch_size=BATCH_SIZE, shuffle=True)

 ========== EDSR模型（适配预训练权重加载） ==========


class EDSR(nn.Module):
    def __init__(self, in_channels=, scale=, num_blocks=):
        super(EDSR, self).__init__()
        self.scale = scale
         特征提取主干
        self.conv = nn.Convd(in_channels, , kernel_size=, padding=)
        self.res_blocks = nn.Sequential([self._res_block() for _ in range(num_blocks)])
        self.conv = nn.Convd(, , kernel_size=, padding=)
         上采样层（适配不同scale）
        self.upsample = nn.Sequential(
            nn.Convd(,   scale  scale, kernel_size=, padding=),
            nn.PixelShuffle(scale),
            nn.Convd(, in_channels, kernel_size=, padding=)
        )

    def _res_block(self, channels):
        return nn.Sequential(
            nn.Convd(channels, channels, kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(channels, channels, kernel_size=, padding=)
        )

    def forward(self, x):
        residual = self.conv(x)
        out = self.res_blocks(residual)
        out = self.conv(out) + residual
        out = self.upsample(out)
        return out

 ========== 加载预训练权重（核心：复用+适配） ==========


def load_pretrained_weights(model, pretrain_ckpt, in_channels):
    """
    加载预训练权重，适配不同输入通道（CT:通道/RGB:通道）
    """
    pretrain_dict = torch.load(pretrain_ckpt, map_location=DEVICE)
    model_dict = model.state_dict()

     过滤不匹配的层（输入通道/输出层）
    pretrain_dict = {k: v for k, v in pretrain_dict.items() if
                     k in model_dict and model_dict[k].shape == v.shape and
                     not k.startswith("upsample")}   不加载上采样层

     更新模型权重
    model_dict.update(pretrain_dict)
    model.load_state_dict(model_dict)
    print(f" 加载预训练权重：共匹配{len(pretrain_dict)}层")
    return model

 ========== 训练函数（续训逻辑） ==========


def train_continual(model, train_loader, pretrain_ckpt, dataset_type="ct"):
     . 加载预训练权重
    model = load_pretrained_weights(model, pretrain_ckpt, in_channels= if dataset_type == "ct" else )

     . 冻结主干（前轮）
    for param in model.res_blocks.parameters():
        param.requires_grad = False

     . 优化器
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=LR)
    criterion = nn.LLoss()   LLoss比MSE更适合超分，PSNR更高

     . 训练循环
    model.train()
    for epoch in range(EPOCHS):
         解冻主干（第轮后）
        if epoch == FREEZE_BACKBONE_EPOCHS:
            for param in model.res_blocks.parameters():
                param.requires_grad = True
            optimizer = optim.Adam(model.parameters(), lr=LR)
            print(" 解冻主干网络，继续训练")

        epoch_loss = .
        pbar = tqdm(train_loader, desc=f"Epoch {epoch+}/{EPOCHS}")
        for lr_img, hr_img in pbar:
            lr_img, hr_img = lr_img.to(DEVICE), hr_img.to(DEVICE)

             前向传播
            sr_img = model(lr_img)
            loss = criterion(sr_img, hr_img)

             反向传播
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            pbar.set_postfix({"Loss": loss.item()})

         保存续训权重
        avg_loss = epoch_loss / len(train_loader)
        print(f"Epoch {epoch+} 平均损失：{avg_loss:.f}")
        os.makedirs("./continual_ckpt", exist_ok=True)
        torch.save(model.state_dict(), f"./continual_ckpt/edsr_{dataset_type}_epoch{epoch+}.pth")


 ========== 启动续训 ==========
if __name__ == "__main__":
     . 续训LUNA（继承DeepLesion预训练，CT灰度图）
    print("===== 开始续训LUNA（继承DeepLesion预训练） =====")
    ct_model = EDSR(in_channels=, scale=SCALE).to(DEVICE)
    train_continual(ct_model, luna_train_loader, DEEPLESION_CKPT, dataset_type="luna_ct")

     . 续训VOC（继承DIVK预训练，RGB图）
    print("\n===== 开始续训VOC（继承DIVK预训练） =====")
    rgb_model = EDSR(in_channels=, scale=SCALE).to(DEVICE)
    train_continual(rgb_model, voc_train_loader, DIVK_CKPT, dataset_type="voc_rgb")

    print(" 多数据集续训完成！模型兼具CT和通用图像超分能力")
