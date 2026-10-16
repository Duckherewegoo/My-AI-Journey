 -- coding: utf- --
"""
极简测试脚本：定位 noise_std 未定义的具体行
"""
import os
import torch
import traceback
import inspect
from PIL import Image
from torch.utils.data.dataset import Dataset
import torchvision.transforms as transforms
from torchvision.transforms import InterpolationMode

 -------------------------- . 仅保留必要的 AddGaussianNoise（简化版） --------------------------
class AddGaussianNoise(object):
    def __init__(self, sigma, prob=.):
        self.sigma = sigma
        self.prob = prob

    def __call__(self, img):
        import random
        import numpy as np
        if random.uniform(, ) < self.prob:
            clean_image = np.array(img).copy()
            noise_mask = np.random.randn(clean_image.shape)  self.sigma
            result = np.clip(clean_image + noise_mask, , )
            return Image.fromarray(result.astype('uint'))
        return img

 -------------------------- . 极简版 DeepLesionDataset（仅保留核心逻辑） --------------------------
class DeepLesionDataset(Dataset):
    def __init__(self, hr_dir, crop_size, noise_std, phase, scale_factor=):
        super().__init__()
         仅保留核心参数赋值（删除所有冗余代码）
        self.hr_dir = hr_dir
        self.crop_size = crop_size
        self.phase = phase.lower()
        self.noise_std = noise_std   关键行：必须保留
        self.scale_factor = scale_factor

         仅保留必要的文件加载（简化）
        self.hr_files = [os.path.join(hr_dir, f) for f in os.listdir(hr_dir) if f.endswith(('.png', '.jpg'))][:]   只加载前个文件
        assert len(self.hr_files) > , "无有效图像文件"

         核心：LR变换链（仅保留触发错误的关键逻辑）
        self.lr_transform = transforms.Compose([
            AddGaussianNoise(sigma=self.noise_std),   这里用self.noise_std，出错会定位到这行
            transforms.Resize(size=crop_size//scale_factor, interpolation=InterpolationMode.BICUBIC),
            transforms.ToTensor()
        ])
        self.hr_transform = transforms.Compose([transforms.ToTensor()])

    def __getitem__(self, index):
        img = Image.open(self.hr_files[index]).convert('L')
        lr = self.lr_transform(img)
        hr = self.hr_transform(img)
        return lr, hr

    def __len__(self):
        return len(self.hr_files)

 -------------------------- . 核心测试逻辑（逐行校验 + 打印行号） --------------------------
if __name__ == "__main__":
     配置（仅保留核心参数）
    config = {
        "dataset": {
            "train_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/train/HR/",
            "crop_size": ,
            "scale_factor": ,
            "noise_std": .,
        }
    }

     ========== 测试步骤：校验配置 ==========
    print(" 步骤：校验配置参数")
    try:
        noise_std = config["dataset"]["noise_std"]
        print(f" 配置中的 noise_std: {noise_std} (行号：{inspect.currentframe().f_lineno})")
    except Exception as e:
        print(f" 步骤失败（行号：{inspect.currentframe().f_lineno}）：{type(e).__name__}: {e}")
        traceback.print_exc()
        exit()

     ========== 测试步骤：初始化数据集（核心） ==========
    print("\n 步骤：初始化数据集（逐行校验）")
    try:
         打印当前行号，定位初始化时的错误
        print(f" 开始初始化数据集（行号：{inspect.currentframe().f_lineno}）")
        train_set = DeepLesionDataset(
            hr_dir=config["dataset"]["train_hr_dir"],
            crop_size=config["dataset"]["crop_size"],
            noise_std=config["dataset"]["noise_std"],
            phase="train",
            scale_factor=config["dataset"]["scale_factor"],
        )
        print(f" 数据集初始化成功（行号：{inspect.currentframe().f_lineno}）")
    except Exception as e:
        print(f" 步骤失败（行号：{inspect.currentframe().f_lineno}）：{type(e).__name__}: {e}")
        print(" 错误堆栈（含具体行号）：")
        traceback.print_exc()
        exit()

     ========== 测试步骤：加载样本 ==========
    print("\n 步骤：加载第一个样本")
    try:
        lr, hr = train_set[]
        print(f" 样本加载成功（行号：{inspect.currentframe().f_lineno}）")
        print(f" LR形状: {lr.shape}, HR形状: {hr.shape}")
    except Exception as e:
        print(f" 步骤失败（行号：{inspect.currentframe().f_lineno}）：{type(e).__name__}: {e}")
        print(" 错误堆栈（含具体行号）：")
        traceback.print_exc()
        exit()

    print("\n 所有测试通过！无任何错误！")

