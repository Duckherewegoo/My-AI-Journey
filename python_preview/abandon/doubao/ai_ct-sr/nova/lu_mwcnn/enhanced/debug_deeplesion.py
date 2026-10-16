!/usr/bin/env python
 -- coding: utf- --
"""
DeepLesionDataset 调试脚本：定位 noise_std 未定义问题（最终无类型错误版）
"""
import os
import torch
from torch.utils.data.dataset import Dataset
from PIL import Image, UnidentifiedImageError
import torchvision.transforms as transforms
from torchvision.transforms import InterpolationMode
from typing import Tuple, Union   新增：精确类型注解

 -------------------------- . 模拟你的 AddGaussianNoise 类 --------------------------
class AddGaussianNoise(object):
    """添加高斯噪声（和你真实代码一致）"""
    def __init__(self, sigma: float, prob: float = .):
        assert isinstance(sigma, float) and isinstance(prob, float)
        self.sigma = sigma
        self.prob = prob

    def __call__(self, img: Image.Image) -> Image.Image:
        """明确输入输出都是PIL.Image，消除类型模糊"""
        import random
        import numpy as np
        if random.uniform(, ) < self.prob:
            clean_image = np.array(img).copy()
            noise_mask = np.random.randn(clean_image.shape)  self.sigma
            result = clean_image + noise_mask
            result[result > ] = 
            result[result < ] = 
            return Image.fromarray(result.astype('uint'))
        else:
            return img

 -------------------------- . 无类型错误的 DeepLesionDataset 类 --------------------------
class DeepLesionDataset(Dataset):
    def __init__(self, hr_dir: str, crop_size: int, noise_std: float, phase: str, scale_factor: int = ) -> None:
        super().__init__()

         ===================== 调试关键点：打印初始化参数 =====================
        print(f"\n=== 数据集初始化参数检查 ===")
        print(f"hr_dir: {hr_dir}")
        print(f"crop_size: {crop_size}")
        print(f"noise_std（传入值）: {noise_std}")
        print(f"phase: {phase}")
        print(f"scale_factor: {scale_factor}")

         基础参数赋值（核心：必须保留）
        self.hr_dir = hr_dir
        self.crop_size = crop_size
        self.phase = phase.lower()
        self.noise_std = noise_std   绝对不能注释！
        self.scale_factor = scale_factor

         ===================== 调试关键点：验证self变量是否创建 =====================
        print(f"\n=== self变量检查 ===")
        print(f"self.noise_std: {getattr(self, 'noise_std', '未定义！')}")
        print(f"self.scale_factor: {getattr(self, 'scale_factor', '未定义！')}")

         参数校验
        assert self.phase in ('train', 'val'), f"阶段仅支持train/val，当前：{phase}"
        assert crop_size % self.scale_factor == , f"crop_size {crop_size} 必须是缩放因子 {scale_factor} 的倍数"
        assert os.path.exists(hr_dir), f"HR目录不存在：{hr_dir}"
        assert noise_std >= , f"噪声标准差不能为负数：{noise_std}"

         筛选有效图像文件
        print(f"\n=== 开始加载HR文件 ===")
        self.hr_files = self._get_valid_image_files(hr_dir)
        print(f"[train] 加载数据集完成 - HR文件数: {len(self.hr_files)}, 缩放因子: {self.scale_factor}")
        assert len(self.hr_files) > , f"HR目录下无有效图像：{hr_dir}"

         训练阶段数据增广
        pad_value = 
        self.train_public_transform = transforms.Compose([
            transforms.RandomCrop(
                size=crop_size,
                padding=,
                pad_if_needed=True,
                fill=pad_value
            ),
            transforms.RandomHorizontalFlip(p=.),
            transforms.RandomVerticalFlip(p=.)
        ])

         ===================== 调试关键点：验证AddGaussianNoise参数 =====================
        print(f"\n=== LR变换链初始化（重点检查noise_std） ===")
        try:
            self.lr_transform = transforms.Compose([
                AddGaussianNoise(sigma=self.noise_std, prob=.),   用self.noise_std
                transforms.Resize(
                    size=crop_size // self.scale_factor if self.phase == 'train' 
                    else lambda x: (int(x.size[] / self.scale_factor), int(x.size[] / self.scale_factor)),
                    interpolation=InterpolationMode.BICUBIC
                ),
                transforms.ToTensor()   最后一步强制转Tensor，避免返回PIL
            ])
            print(" LR变换链初始化成功（noise_std参数正常）")
        except Exception as e:
            print(f" LR变换链初始化失败：{type(e).__name__}: {e}")
            raise

        self.hr_transform = transforms.Compose([transforms.ToTensor()])   强制转Tensor

    def _get_valid_image_files(self, dir_path: str) -> list[str]:
        """明确返回字符串列表"""
        valid_ext = ('.png', '.jpg', '.jpeg', '.tif', '.tiff')
        valid_files = []
        for fname in sorted(os.listdir(dir_path)):
            fpath = os.path.join(dir_path, fname)
            if not os.path.isfile(fpath):
                continue
            if not fname.lower().endswith(valid_ext):
                continue
            try:
                with Image.open(fpath) as img:
                    img.verify()
                valid_files.append(fpath)
            except (UnidentifiedImageError, IOError):
                print(f"警告：跳过无效图像 {fpath}")
                continue
        return valid_files

    def __getitem__(self, index: int) -> Union[
        Tuple[torch.Tensor, torch.Tensor],   train阶段：仅个Tensor
        Tuple[torch.Tensor, torch.Tensor, str]   val阶段：个Tensor + 字符串
    ]:
        """精确类型注解，消除静态检查错误"""
        fpath = self.hr_files[index]
        try:
            image_PIL = Image.open(fpath).convert('L')
        except Exception as e:
            raise RuntimeError(f"读取图像失败 {fpath}：{str(e)}") from e

        x = self.train_public_transform(image_PIL) if self.phase == 'train' else image_PIL
        
         ===================== 调试关键点：强制确保返回Tensor =====================
        print(f"\n=== 测试第{index}个样本的变换链执行 ===")
        try:
            y_lr = self.lr_transform(x)
            y_hr = self.hr_transform(x)
             强制校验类型（确保是Tensor而非PIL）
            assert isinstance(y_lr, torch.Tensor), f"LR应为Tensor，当前：{type(y_lr)}"
            assert isinstance(y_hr, torch.Tensor), f"HR应为Tensor，当前：{type(y_hr)}"
            print(f" 样本变换成功 - LR类型: {type(y_lr)}, HR类型: {type(y_hr)}")
        except Exception as e:
            print(f" 样本变换失败：{type(e).__name__}: {e}")
            raise

         严格区分训练/验证阶段返回值，避免解包错误
        if self.phase == 'train':
            return y_lr, y_hr   train阶段：仅返回个Tensor（类型注解匹配）
        else:
            filename = os.path.splitext(os.path.basename(fpath))[]
            return y_lr, y_hr, filename   val阶段：返回个值

    def __len__(self) -> int:
        return len(self.hr_files)

 -------------------------- . 模拟配置 + 执行调试（无类型错误） --------------------------
if __name__ == "__main__":
     . 复制你的真实配置
    config = {
        "lr": e-,
        "epochs": ,
        "batch_size": ,
        "val_every": ,
        "num_workers": min(os.cpu_count() or , ),
        "device": "cuda:" if torch.cuda.is_available() else "cpu",
        "keep_checkpoints": ,
        "early_stopping": {
            "enabled": True,
            "patience": ,
            "min_delta": e-,
            "min_improvement": .,
            "warmup_epochs": ,
            "strategy": "composite",
        },
        "output_path": r"/home/dake/Documents/Projects/Graduation_Projects/codes/nova/lu_mwcnn/output_deeplesion",
        "dataset": {
            "train_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/train/HR/",
            "val_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/val/HR",
            "test_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/test/HR",
            "interface": "deeplesions.DeepLesionDataset",
            "crop_size": ,
            "scale_factor": ,
            "noise_std": .,
        },
    }
    config["noise_std"] = config["dataset"]["noise_std"]
    config["grad_clip_norm"] = .
    config["psnr_max"] = .
    config["gradient_check_interval"] = 

     . 调试：打印配置中的noise_std
    print("=")
    print(" 第一步：验证配置中的noise_std")
    print(f"config['dataset']['noise_std']: {config['dataset']['noise_std']}")
    print(f"config['noise_std']: {config['noise_std']}")
    print("=")

     . 初始化数据集（强制指定phase='train'，确保返回个值）
    try:
        print("\n 第二步：初始化DeepLesionDataset（train阶段）")
        train_set = DeepLesionDataset(
            hr_dir=config["dataset"]["train_hr_dir"],
            crop_size=config["dataset"]["crop_size"],
            noise_std=config["dataset"]["noise_std"],
            phase="train",   强制train阶段，仅返回个值
            scale_factor=config["dataset"]["scale_factor"],
        )

         . 测试加载第一个样本（仅解包个值，完全匹配类型注解）
        print("\n 第三步：测试加载第一个样本（train阶段）")
        lr: torch.Tensor
        hr: torch.Tensor
        lr, hr = train_set[]   显式标注类型，消除静态检查错误
        print(f"\n 调试完成！无报错 - LR形状: {lr.shape}, HR形状: {hr.shape}")

    except Exception as e:
        print(f"\n 调试失败！错误详情：")
        print(f"错误类型：{type(e).__name__}")
        print(f"错误信息：{e}")
         打印完整堆栈（方便定位具体行）
        import traceback
        traceback.print_exc()
