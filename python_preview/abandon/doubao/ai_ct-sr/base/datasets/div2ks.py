"""
    DIV2K 数据集接口（自然图像超分辨率）。
    支持 train/val/test 三阶段，YCbCr 分离（仅 Y 通道超分）
"""
import os
import numpy as np
import torchvision.transforms as transforms
from torch.utils.data.dataset import Dataset
from torchvision.transforms import InterpolationMode
from PIL import Image

from base.utils.transforms import AddGaussianNoise


class DIVKDataset(Dataset):
    def __init__(self, hr_dir: str, crop_size: int = 128,
                 noise_std: float = 1.0 / 255.0,
                 phase: str = 'train',
                 scale_factor: int = 4) -> None:
        """DIV2K 数据集接口

        Args:
            hr_dir (str): 对应阶段（train/val/test）的高分图像根路径
            crop_size (int): Patch 切片大小（scale_factor 的倍数，仅训练阶段生效）
            noise_std (float): 注入的高斯噪声标准差（0~1）
            phase ('train' | 'val' | 'test'): 数据阶段
            scale_factor (int): 超分缩放因子，默认 4
        """
        super().__init__()

        self.hr_dir = hr_dir
        self.crop_size = crop_size
        self.noise_std = noise_std
        self.phase = phase
        self.scale_factor = scale_factor

        # 阶段校验
        assert self.phase in ('train', 'val', 'test'), \
            f'无效的阶段 {phase}，仅支持 train/val/test'

        # 加载图像文件（过滤非图像）
        self.hr_files = [
            os.path.join(self.hr_dir, x)
            for x in sorted(os.listdir(hr_dir))
            if x.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))
        ]
        assert len(self.hr_files) > 0, f'在 {hr_dir} 中未找到任何图像文件'

        # 训练增强：随机裁剪 + 随机翻转
        self.train_aug_transform = transforms.Compose([
            transforms.RandomCrop(crop_size, padding=8, pad_if_needed=True),
            transforms.RandomHorizontalFlip(0.5),
        ])

        # LR 变换：噪声 + 下采样 + ToTensor
        # - train 阶段：固定下采样到 crop_size // scale_factor
        # - val/test 阶段：按原图等比下采样
        self.lr_transform = transforms.Compose([
            AddGaussianNoise(noise_std),
            transforms.Lambda(
                lambda x: transforms.Resize(
                    size=(crop_size // scale_factor) if self.phase == 'train'
                    else (x.size[0] // scale_factor,
                          x.size[1] // scale_factor),
                    interpolation=InterpolationMode.BICUBIC
                )(x)
            ),
            transforms.ToTensor()
        ])

        # HR 变换：仅 ToTensor（保持原尺寸或裁剪后尺寸）
        self.hr_transform = transforms.Compose([transforms.ToTensor()])

    def __getitem__(self, index):
        """
        返回格式：
        - train:      (y_lr, y_hr)                       ← 2 元组
        - val/test:   (y_lr, y_hr, cb_lr, cr_lr, filename)  ← 5 元组
        """
        hr_file = self.hr_files[index]

        # 读图并转 YCbCr
        try:
            image_pil = Image.open(hr_file).convert('RGB').convert('YCbCr')
        except Exception as e:
            raise RuntimeError(f'读取图像失败 {hr_file}: {e}')

        image_np = np.array(image_pil)              # (H, W, 3) → Y, Cb, Cr

        # Y 通道（模型输入）
        y_channel = Image.fromarray(image_np[:, :, 0])

        # 训练阶段增强
        if self.phase == 'train':
            aug_y = self.train_aug_transform(y_channel)
        else:
            aug_y = y_channel

        # LR / HR Y 通道张量
        y_lr = self.lr_transform(aug_y)
        y_hr = self.hr_transform(aug_y)

        # 训练阶段只返回 Y 通道（减少传输开销）
        if self.phase == 'train':
            return y_lr, y_hr

        # val/test 阶段返回完整 Y/Cb/Cr + 文件名
        filename = os.path.splitext(os.path.basename(hr_file))[0]

        cb_channel = Image.fromarray(image_np[:, :, 1])
        cr_channel = Image.fromarray(image_np[:, :, 2])
        cb_lr = self.lr_transform(cb_channel)
        cr_lr = self.lr_transform(cr_channel)

        return y_lr, y_hr, cb_lr, cr_lr, filename

    def __len__(self):
        return len(self.hr_files)


# ===================== 使用示例 =====================
if __name__ == '__main__':
    # 训练集
    train_dataset = DIVKDataset(
        hr_dir='./DIV2K/train',
        crop_size=128,
        noise_std=1.0 / 255.0,
        phase='train',
    )
    # 验证集
    val_dataset = DIVKDataset(
        hr_dir='./DIV2K/val',
        crop_size=128,
        noise_std=1.0 / 255.0,
        phase='val',
    )
    # 测试集
    test_dataset = DIVKDataset(
        hr_dir='./DIV2K/test',
        crop_size=128,          # test 阶段该参数无效，仅为兼容
        noise_std=1.0 / 255.0,
        phase='test',
    )

    print(f'训练集数量：{len(train_dataset)}')
    print(f'验证集数量：{len(val_dataset)}')
    print(f'测试集数量：{len(test_dataset)}')

    # 测试加载
    if len(test_dataset) > 0:
        y_lr, y_hr, cb_lr, cr_lr, filename = test_dataset[0]
        print(f'\n测试集示例 - 文件名：{filename}')
        print(f'Y-LR 形状：{y_lr.shape}, Y-HR 形状：{y_hr.shape}')
        print(f'Cb-LR 形状：{cb_lr.shape}, Cr-LR 形状：{cr_lr.shape}')
