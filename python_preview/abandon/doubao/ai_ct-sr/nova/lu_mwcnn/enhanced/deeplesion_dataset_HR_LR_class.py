 deeplesion.py 中的数据集类示例
import os
from PIL import Image
import torch
from torch.utils.data import Dataset
import torchvision.transforms as transforms

class DeepLesionDataset(Dataset):
    def __init__(self, hr_dir, lr_dir, crop_size=, scale_factor=, mode='train'):
        self.hr_dir = hr_dir
        self.lr_dir = lr_dir
        self.crop_size = crop_size
        self.scale_factor = scale_factor
        self.mode = mode
        
         获取图像文件名（假设HR和LR有相同的文件名）
        self.hr_images = sorted([f for f in os.listdir(hr_dir) if f.endswith(('.png', '.jpg', '.jpeg'))])
        self.lr_images = sorted([f for f in os.listdir(lr_dir) if f.endswith(('.png', '.jpg', '.jpeg'))])
        
         确保文件名匹配
        assert self.hr_images == self.lr_images, "HR和LR图像文件名不匹配"
        
         数据增强变换
        if mode == 'train':
            self.transform = transforms.Compose([
                transforms.RandomCrop(crop_size),
                transforms.RandomHorizontalFlip(),
                transforms.RandomVerticalFlip(),
                transforms.ToTensor(),
            ])
        else:
            self.transform = transforms.Compose([
                transforms.CenterCrop(crop_size),
                transforms.ToTensor(),
            ])

    def __len__(self):
        return len(self.hr_images)

    def __getitem__(self, idx):
        hr_path = os.path.join(self.hr_dir, self.hr_images[idx])
        lr_path = os.path.join(self.lr_dir, self.lr_images[idx])
        
        hr_img = Image.open(hr_path).convert('L')   转换为灰度
        lr_img = Image.open(lr_path).convert('L')
        
         应用变换
        hr_tensor = self.transform(hr_img)
        lr_tensor = self.transform(lr_img)
        
        return lr_tensor, hr_tensor, self.hr_images[idx]