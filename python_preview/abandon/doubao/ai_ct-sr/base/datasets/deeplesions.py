"""
    DeepLesion 数据集接口（医学图像超分辨率）
    整合版：统一返回格式、全数字补全、3060 8GB 适配
"""
import os
import random
import logging
import numpy as np
import torch
from PIL import Image, ImageEnhance, UnidentifiedImageError
from torchvision import transforms
from torchvision.transforms import InterpolationMode
from torch.utils.data.dataset import Dataset
from typing import Optional, List, Tuple, Union


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')


# ===================== 数据增强：高斯噪声 =====================
class AddGaussianNoise:
    """对 PIL 灰度图加高斯噪声（训练 LR 分支专用）"""

    def __init__(self, sigma: float = 0.01, prob: float = 0.5):
        self.sigma = sigma
        self.prob = prob

    def __call__(self, img):
        if np.random.rand() >= self.prob:
            return img
        img_np = np.array(img).astype(np.float32)
        noise = np.random.normal(0.0, self.sigma, img_np.shape)
        img_np = np.clip(img_np + noise, 0.0, 255.0).astype(np.uint8)
        return Image.fromarray(img_np)

    def __repr__(self):
        return f"AddGaussianNoise(sigma={self.sigma}, prob={self.prob})"


# ===================== 数据集 =====================
class DeepLesionDataset(Dataset):
    """
    DeepLesion 医学图像超分数据集
    - train: 数据增强 + 随机裁剪
    - val/test: 中心裁剪 + 全图评测
    - 统一返回 2 元组 (y_lr, y_hr)；filename 通过 get_filename_list() 单独获取
    """

    def __init__(self,
                 hr_dir: str,
                 crop_size: int = 128,
                 noise_std: float = 0.01,
                 phase: str = 'train',
                 lr_dir: Optional[str] = None,
                 scale_factor: int = 4,
                 normalize: bool = True,
                 augment: bool = True,
                 max_rotation: float = 15.0,
                 max_scale: float = 1.2,
                 min_scale: float = 0.8):
        super().__init__()

        # ===== 参数绑定 =====
        self.hr_dir = hr_dir
        self.lr_dir = lr_dir
        self.crop_size = crop_size
        self.scale_factor = scale_factor
        self.noise_std = noise_std
        self.normalize = normalize
        self.phase = str(phase).strip().lower()
        self.augment = augment and (self.phase == 'train')
        self.max_rotation = max_rotation
        self.max_scale = max_scale
        self.min_scale = min_scale

        # ===== 参数校验 =====
        self._validate_params()

        # ===== 加载文件列表 =====
        self.hr_files: List[str] = self._load_valid_files(hr_dir)
        self.lr_files: Optional[List[str]] = (
            self._load_valid_files(lr_dir) if lr_dir else None
        )
        if self.lr_files is not None and len(self.hr_files) != len(self.lr_files):
            raise ValueError(
                f"HR({len(self.hr_files)}) 与 LR({len(self.lr_files)}) 文件数不匹配")

        logger.info(
            f"[{self.phase}] 数据集加载: {len(self.hr_files)} 张, "
            f"scale={scale_factor}, crop={crop_size}")

        # ===== 构建变换 =====
        self._build_transforms()

    # ---------- 参数校验 ----------
    def _validate_params(self):
        if self.phase not in ('train', 'val', 'test'):
            raise ValueError(
                f"无效 phase: '{self.phase}'，仅支持 train/val/test")

        if self.crop_size % self.scale_factor != 0:
            self.crop_size -= self.crop_size % self.scale_factor
            logger.warning(f"crop_size 修正为 {self.crop_size}")

        if not os.path.exists(self.hr_dir):
            raise FileNotFoundError(f"HR 目录不存在: {self.hr_dir}")
        if self.lr_dir and not os.path.exists(self.lr_dir):
            raise FileNotFoundError(f"LR 目录不存在: {self.lr_dir}")

        if self.max_rotation < 0:
            self.max_rotation = abs(self.max_rotation)
        if self.max_scale <= self.min_scale:
            self.max_scale, self.min_scale = self.min_scale, self.max_scale
        if self.min_scale <= 0:
            self.min_scale = 0.8

    # ---------- 文件加载 ----------
    def _load_valid_files(self, dir_path: Optional[str]) -> Optional[List[str]]:
        if not dir_path:
            return None
        files = []
        for fname in sorted(os.listdir(dir_path)):
            if fname.startswith('.'):
                continue
            if not fname.lower().endswith(SUPPORTED_EXTENSIONS):
                continue
            fpath = os.path.join(dir_path, fname)
            try:
                with Image.open(fpath) as img:
                    img.verify()
                files.append(fpath)
            except (UnidentifiedImageError, IOError) as e:
                logger.warning(f"跳过无效图像 {fpath}: {e}")
        if not files:
            raise RuntimeError(f"目录 {dir_path} 无有效图像")
        return files

    # ---------- 变换管道 ----------
    def _build_transforms(self):
        # 公共变换：灰度化
        common = [transforms.Lambda(lambda x: x.convert('L'))]

        # 训练增强
        train_aug = []
        if self.augment:
            train_aug = [
                transforms.RandomResizedCrop(
                    size=self.crop_size,
                    scale=(self.min_scale, self.max_scale),
                    interpolation=InterpolationMode.BICUBIC),
                transforms.RandomCrop(
                    self.crop_size, padding=8, pad_if_needed=True, fill=0),
                transforms.RandomHorizontalFlip(p=0.5),
                transforms.RandomVerticalFlip(p=0.5),
                transforms.RandomRotation(
                    degrees=(-self.max_rotation, self.max_rotation),
                    expand=False, fill=0),
                transforms.Lambda(
                    lambda x: ImageEnhance.Contrast(x).enhance(
                        np.random.uniform(0.9, 1.1))),
            ]

        # val/test: 中心裁剪
        val_test = []
        if self.phase in ('val', 'test') and self.crop_size > 0:
            val_test = [transforms.CenterCrop(self.crop_size)]

        if self.phase == 'train':
            self.public_transform = transforms.Compose(common + train_aug)
        else:
            self.public_transform = transforms.Compose(common + val_test)

        # ===== LR 变换 =====
        lr_t = []
        if self.phase == 'train' and self.noise_std > 0:
            lr_t.append(AddGaussianNoise(sigma=self.noise_std, prob=0.5))

        if self.phase == 'train':
            lr_t.append(transforms.Resize(
                self.crop_size // self.scale_factor,
                interpolation=InterpolationMode.BICUBIC))
        else:
            # val/test：按原尺寸等比缩小
            lr_t.append(transforms.Lambda(
                lambda x: transforms.Resize(
                    (x.size[0] // self.scale_factor,
                     x.size[1] // self.scale_factor),
                    interpolation=InterpolationMode.BICUBIC)(x)))

        lr_t.append(transforms.ToTensor())
        if self.normalize:
            lr_t.append(transforms.Normalize(mean=[0.5], std=[0.5]))
        self.lr_transform = transforms.Compose(lr_t)

        # ===== HR 变换 =====
        hr_t = [transforms.ToTensor()]
        if self.normalize:
            hr_t.append(transforms.Normalize(mean=[0.5], std=[0.5]))
        self.hr_transform = transforms.Compose(hr_t)

    # ---------- 数据清洗 ----------
    def _clean_image_data(self, img_np: np.ndarray) -> np.ndarray:
        img_np = np.nan_to_num(img_np, nan=0.0, posinf=255.0, neginf=0.0)
        return np.clip(img_np, 0, 255)

    # ---------- 单样本读取 ----------
    def __getitem__(self, index: int) -> Tuple[torch.Tensor, torch.Tensor]:
        try:
            hr_path = self.hr_files[index]
            if not os.path.exists(hr_path):
                raise FileNotFoundError(f"HR 不存在: {hr_path}")

            with Image.open(hr_path) as f:
                image_pil = f.convert('L')
                image_np = np.array(image_pil, dtype=np.uint8)

            # 过滤极小图（非递归重试）
            min_side = min(image_np.shape[0], image_np.shape[1])
            if min_side < 32:
                for _ in range(3):
                    new_idx = random.randint(0, len(self.hr_files) - 1)
                    try:
                        with Image.open(self.hr_files[new_idx]) as f:
                            tmp = np.array(f.convert('L'), dtype=np.uint8)
                        if min(tmp.shape) >= 32:
                            image_np = tmp
                            break
                    except Exception:
                        pass
                else:
                    image_np = np.ones((64, 64), dtype=np.uint8) * 128

            image_np = self._clean_image_data(image_np)
            img_hr = Image.fromarray(image_np.astype(np.uint8))
            x = self.public_transform(img_hr)

            # LR 分支
            if self.lr_files and index < len(self.lr_files):
                lr_path = self.lr_files[index]
                with Image.open(lr_path) as f:
                    img_lr = f.convert('L')
                img_lr = self.public_transform(img_lr)
                y_lr = self.lr_transform(img_lr)
            else:
                y_lr = self.lr_transform(x)

            y_hr = self.hr_transform(x)

            # 数值校验
            if torch.isnan(y_lr).any() or torch.isinf(y_lr).any():
                y_lr = torch.nan_to_num(y_lr, nan=0.0, posinf=1.0, neginf=-1.0)
            if torch.isnan(y_hr).any() or torch.isinf(y_hr).any():
                y_hr = torch.nan_to_num(y_hr, nan=0.0, posinf=1.0, neginf=-1.0)

            return y_lr, y_hr

        except Exception as e:
            logger.error(f"样本[{index}] 处理失败: {e}")
            # 兜底张量
            sf = max(1, self.scale_factor)
            lr_size = max(1, self.crop_size // sf)
            y_lr = torch.zeros((1, lr_size, lr_size), dtype=torch.float32)
            y_hr = torch.zeros((1, self.crop_size, self.crop_size),
                               dtype=torch.float32)
            return y_lr, y_hr

    def __len__(self):
        return len(self.hr_files)

    # ---------- 辅助方法 ----------
    def get_filename_list(self) -> List[str]:
        return [os.path.splitext(os.path.basename(f))[0]
                for f in self.hr_files]

    def get_image_shape(self, index: int = 0):
        with Image.open(self.hr_files[index]) as img:
            return img.size[1], img.size[0]  # H, W
