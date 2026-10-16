import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
import cv
import numpy as np
from PIL import Image
import os
import random

 ===================== . 模型定义（和你提供的LUMWCNN完全一致） =====================


class LUMWCNN(nn.Module):
    """带强制倍上采样的超分模型（确保输出x）"""

    def __init__(self, in_channels=, upscale_factor=):
        super().__init__()
        self.upscale_factor = upscale_factor

         基础特征提取
        self.features = nn.Sequential(
            nn.Convd(in_channels, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True)
        )

         强制倍上采样模块
        self.upsample = nn.Sequential(
            nn.Convd(,   (upscale_factor), kernel_size=, padding=),
            nn.PixelShuffle(upscale_factor),
            nn.Convd(, in_channels, kernel_size=, padding=),
            nn.Sigmoid()
        )

    def forward(self, x):
        features = self.features(x)
        out = self.upsample(features)
        return out

 ===================== . 简单数据集（用于快速训练） =====================


class SimpleSRDataset(Dataset):
    """简单的超分数据集（生成x低分辨率→x高分辨率）"""

    def __init__(self, num_samples=, img_size=(, )):
        self.num_samples = num_samples
        self.img_size = img_size
        self.lr_size = (img_size[] // , img_size[] // )

         数据预处理
        self.transform = transforms.Compose([
            transforms.ToTensor(),
        ])

    def __len__(self):
        return self.num_samples

    def __getitem__(self, idx):
         生成随机图像（模拟超分数据）
        hr_img = np.random.randint(, , (self.img_size[], self.img_size[], ), dtype=np.uint)
        lr_img = cv.resize(hr_img, self.lr_size, interpolation=cv.INTER_CUBIC)

         转换为张量
        hr_tensor = self.transform(Image.fromarray(hr_img))
        lr_tensor = self.transform(Image.fromarray(lr_img))

        return lr_tensor, hr_tensor

 ===================== . 训练函数 =====================


def train_lumwcnn():
     配置
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    epochs = 
    batch_size = 
    lr = e-
    save_path = './output_divk/ckp_rgb/new_best_model.pth'

     创建保存目录
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

     . 初始化模型（和你提供的完全一致）
    model = LUMWCNN(in_channels=, upscale_factor=).to(device)

     . 数据集和数据加载器
    dataset = SimpleSRDataset(num_samples=)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

     . 损失函数和优化器
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)

     . 训练
    model.train()
    best_loss = float('inf')

    print(f" 开始训练LUMWCNN模型...")
    print(f" 设备：{device} | 批次大小：{batch_size} | 训练轮数：{epochs}")

    for epoch in range(epochs):
        total_loss = .
        for batch_idx, (lr_imgs, hr_imgs) in enumerate(dataloader):
            lr_imgs = lr_imgs.to(device)
            hr_imgs = hr_imgs.to(device)

             前向传播
            outputs = model(lr_imgs)
            loss = criterion(outputs, hr_imgs)

             反向传播
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()

             打印进度
            if (batch_idx + ) %  == :
                print(f"Epoch [{epoch+}/{epochs}], Batch [{batch_idx+}/{len(dataloader)}], Loss: {loss.item():.f}")

         计算平均损失
        avg_loss = total_loss / len(dataloader)
        print(f"Epoch [{epoch+}/{epochs}], Average Loss: {avg_loss:.f}")

         保存最佳模型
        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save({
                'epoch': epoch + ,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'loss': best_loss,
            }, save_path)
            print(f" 保存最佳模型：{save_path} (Loss: {best_loss:.f})")

    print(" 训练完成！")
    return model, save_path

 ===================== . 推理函数（%匹配） =====================


def infer_with_new_model(model_path, image_path, output_path):
    """使用新训练的模型进行推理（%匹配）"""
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

     . 加载模型（和训练时完全一致）
    model = LUMWCNN(in_channels=, upscale_factor=).to(device)
    ckpt = torch.load(model_path, map_location=device)
    model.load_state_dict(ckpt['model_state_dict'])
    model.eval()
    print(" 模型加载成功（%匹配）！")

     . 加载图像
    img = Image.open(image_path).convert('RGB')
    lr_size = (img.size[] //   , img.size[] //   )   确保是的倍数
    img = img.resize(lr_size, Image.BICUBIC)

     . 预处理
    transform = transforms.ToTensor()
    lr_tensor = transform(img).unsqueeze().to(device)

     . 推理
    with torch.no_grad():
        hr_tensor = model(lr_tensor)

     . 后处理
    hr_img = hr_tensor.squeeze().cpu().numpy().transpose(, , )
    hr_img = (hr_img  ).clip(, ).astype(np.uint)

     . 保存
    cv.imwrite(output_path, cv.cvtColor(hr_img, cv.COLOR_RGBBGR))
    print(f" 超分完成！")
    print(f" 输入尺寸：{lr_size} →  输出尺寸：{hr_img.shape[:]}")
    print(f" 保存路径：{output_path}")


 ===================== 主函数 =====================
if __name__ == '__main__':
     步骤：训练模型（生成%匹配的权重）
    model, model_path = train_lumwcnn()

     步骤：使用新模型推理
    INPUT_IMAGE = './Hachimi.jpg'     你的测试图
    OUTPUT_IMAGE = 'test_hr.jpg'   输出图
    infer_with_new_model(model_path, INPUT_IMAGE, OUTPUT_IMAGE)
