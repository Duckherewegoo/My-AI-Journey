'''
    DIVK 数据集接口（自然图像超分辨率）。
    by zgShu @ -
'''

import torchvision.transforms as transforms
from torch.utils.data.dataset import Dataset
from PIL import Image
import os
import numpy as np
from utils.transforms import AddGaussianNoise


class DIVKDataset(Dataset):
    def __init__(self, hr_dir, crop_size, noise_std, phase) -> None:
        """DIVK 数据集接口（自然图像超分辨率）

        Args:
            hr_dir (str): 高分图像路径
            crop_size (int): Patch 切片大小（的倍数）
            noise_std (float): 注入的高斯噪声的标准差
            phase ('train' | 'val'): 阶段
        """
        super(DIVKDataset, self).__init__()

        self.hr_dir = hr_dir
        self.crop_size = crop_size
        self.phase = phase

        assert self.phase == 'train' or self.phase == 'val', '无效的阶段'

        self.hr_files = [os.path.join(self.hr_dir, x) for x in sorted(os.listdir(hr_dir))]

         训练阶段：随机裁剪、随机翻转、注入噪声
        self.train_public_transform = transforms.Compose([
            transforms.RandomCrop(crop_size, padding=, pad_if_needed=True),
            transforms.RandomHorizontalFlip(.),   %概率水平翻转
        ])

         验证阶段：不进行特别的处理，使用 BatchSize 为  来在全图上进行验证

        self.lr_transform = transforms.Compose([
            AddGaussianNoise(noise_std),   注入噪声
            transforms.Resize(crop_size // , interpolation=Image.BICUBIC) if self.phase == 'train' else transforms.
            Lambda(lambda x: transforms.Resize((x.size[] // , x.size[] // ), interpolation=Image.BICUBIC)(x)),
            transforms.ToTensor()
        ])

        self.hr_transform = transforms.Compose([transforms.ToTensor()])

    def __getitem__(self, index):
         模型只接受 Y 通道
        image_PIL = Image.open(self.hr_files[index]).convert('RGB').convert('YCbCr')
        image_np = np.array(image_PIL)

        y = Image.fromarray(image_np[:, :, ])   HW, -, Y, PIL
        x = self.train_public_transform(y) if self.phase == 'train' else y

        y_lr = self.lr_transform(x)   CHW, -, Y, Tensor
        y_hr = self.hr_transform(x)   CHW, -, Y, Tensor

        if self.phase == 'train':
            return y_lr, y_hr
        else:
            filename = ''.join(os.path.basename(self.hr_files[index]).split('.')[:-])
            cb_lr = self.lr_transform(Image.fromarray(image_np[:, :, ]))
            cr_lr = self.lr_transform(Image.fromarray(image_np[:, :, ]))
            return y_lr, y_hr, cb_lr, cr_lr, filename

    def __len__(self):
        return len(self.hr_files)
