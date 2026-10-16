"""
    DeepLesion 数据集接口（医学图像超分辨率）- 增强版
    特性：
      - CT 窗宽窗位调整、HU 值归一化
      - 多类型医学噪声（高斯/泊松/椒盐/乘性）
      - 弹性形变、对比度/亮度增强
      - 自适应分位数归一化
      - 内存/磁盘缓存
"""

import os
import logging
import warnings
from typing import List, Optional, Dict, Any, Tuple, Callable, cast

import numpy as np
import torch
import torchvision.transforms as transforms
from torch.utils.data.dataset import Dataset
from torchvision.transforms import InterpolationMode
from PIL import Image, ImageEnhance

from scipy.ndimage import gaussian_filter, map_coordinates

try:
    import cv2
    CV_AVAILABLE = True
except ImportError:
    cv2 = None
    CV_AVAILABLE = False
    logging.warning("OpenCV 未安装，中值滤波修复功能将不可用")

warnings.filterwarnings('ignore')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(),
              logging.FileHandler('deeplesion_dataset.log')]
)
logger = logging.getLogger(__name__)


# ===================== 常量 =====================
SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')

DEFAULT_WINDOW_LEVEL = 40        # 腹部 CT 常用窗位
DEFAULT_WINDOW_WIDTH = 400       # 腹部 CT 常用窗宽
HU_MIN = -1024                   # 空气 HU
HU_MAX = 3071                    # 骨骼 HU


# ===================== 噪声注入 =====================
class AddMedicalNoise:
    """支持多种医学图像常见噪声"""

    def __init__(self, noise_config: Optional[Dict[str, Any]] = None):
        cfg = noise_config or {}
        self.noise_type = cfg.get('type', 'gaussian')
        self.std = float(cfg.get('std', 0.01))
        self.prob = float(cfg.get('prob', 0.05))

        assert self.noise_type in (
            'gaussian', 'poisson', 'salt_pepper', 'multiplicative'
        ), f"无效噪声类型: {self.noise_type}"

    def __call__(self, img: Image.Image) -> Image.Image:
        if self.std <= 0 and self.noise_type != 'poisson':
            return img

        img_np = np.array(img).astype(np.float32)
        h, w = img_np.shape

        if self.noise_type == 'gaussian':
            noise = np.random.normal(0, self.std * 255.0, (h, w))
            img_np = img_np + noise

        elif self.noise_type == 'poisson':
            img_np = np.clip(img_np / 255.0, 0, 1)
            img_np = np.random.poisson(img_np * 255.0) / 255.0 * 255.0

        elif self.noise_type == 'salt_pepper':
            mask = np.random.choice(
                [0, 1, 2], size=(h, w),
                p=[self.prob / 2, self.prob / 2, 1 - self.prob])
            img_np[mask == 1] = 0
            img_np[mask == 2] = 255

        elif self.noise_type == 'multiplicative':
            noise = np.random.normal(1.0, self.std, (h, w))
            img_np = img_np * noise

        img_np = np.clip(img_np, 0, 255).astype(np.uint8)
        return Image.fromarray(img_np)

    def __repr__(self):
        return (f"{self.__class__.__name__}(type={self.noise_type}, "
                f"std={self.std}, prob={self.prob})")


# ===================== CT 窗宽窗位 =====================
class MedicalWindowAdjust:
    """CT 图像窗宽窗位调整"""

    def __init__(self,
                 window_level: int = DEFAULT_WINDOW_LEVEL,
                 window_width: int = DEFAULT_WINDOW_WIDTH):
        self.window_level = window_level
        self.window_width = window_width

    def __call__(self, img: Image.Image) -> Image.Image:
        img_np = np.array(img).astype(np.float32)

        # 反向映射 HU（假设已归一化到 0-255）
        hu_img = (img_np / 255.0) * (HU_MAX - HU_MIN) + HU_MIN

        # 窗宽窗位裁剪
        window_min = self.window_level - self.window_width // 2
        window_max = self.window_level + self.window_width // 2
        hu_img = np.clip(hu_img, window_min, window_max)

        # 重新归一化到 0-255
        img_np = (hu_img - window_min) / (window_max - window_min) * 255.0
        img_np = np.clip(img_np, 0, 255).astype(np.uint8)
        return Image.fromarray(img_np)


# ===================== 弹性形变 =====================
class ElasticTransform:
    """弹性形变，模拟组织形变"""

    def __init__(self, alpha: float = 1.0, sigma: float = 8.0,
                 prob: float = 0.3):
        self.alpha = alpha
        self.sigma = sigma
        self.prob = prob

    def __call__(self, img: Image.Image) -> Image.Image:
        if np.random.rand() > self.prob:
            return img

        img_np = np.array(img).astype(np.float32)
        h, w = img_np.shape

        dx = gaussian_filter((np.random.rand(h, w) * 2 - 1),
                             self.sigma) * self.alpha
        dy = gaussian_filter((np.random.rand(h, w) * 2 - 1),
                             self.sigma) * self.alpha

        x, y = np.meshgrid(np.arange(w), np.arange(h))
        indices = (np.reshape(y + dy, (-1, 1)),
                   np.reshape(x + dx, (-1, 1)))

        img_np = map_coordinates(img_np, indices, order=1,
                                 mode='nearest').reshape(h, w)
        img_np = np.clip(img_np, 0, 255).astype(np.uint8)
        return Image.fromarray(img_np)


# ===================== 自适应归一化 =====================
class AdaptiveNormalize:
    """基于分位数的自适应归一化到 [-1, 1]"""

    def __init__(self, lower_q: float = 0.01, upper_q: float = 0.99):
        self.lower_q = lower_q
        self.upper_q = upper_q

    def __call__(self, img: torch.Tensor) -> torch.Tensor:
        lower = torch.quantile(img, self.lower_q)
        upper = torch.quantile(img, self.upper_q)
        img = (img - lower) / (upper - lower + 1e-8)
        img = img * 2 - 1
        return torch.clamp(img, -1, 1)


# ===================== 主数据集 =====================
class DeepLesionDataset(Dataset):

    def __init__(self,
                 hr_dir: str,
                 crop_size: int = 128,
                 phase: str = 'train',
                 lr_dir: Optional[str] = None,
                 scale_factor: int = 4,
                 noise_config: Optional[Dict[str, Any]] = None,
                 normalize: bool = True,
                 augment: bool = True,
                 cache_mode: str = 'none',
                 window_adjust: bool = True,
                 multi_scale: Optional[List[int]] = None,
                 return_filename: bool = False):
        super().__init__()

        # ===== 参数绑定 =====
        self.hr_dir = hr_dir
        self.lr_dir = lr_dir
        self.crop_size = crop_size
        self.scale_factor = scale_factor
        self.noise_config = noise_config if noise_config is not None else {
            'type': 'gaussian', 'std': 0.01, 'prob': 0.5
        }
        self.phase = str(phase).strip().lower()
        self.normalize = normalize
        self.augment = augment and (self.phase == 'train')
        self.cache_mode = cache_mode.lower()
        self.window_adjust = window_adjust
        self.multi_scale = multi_scale if multi_scale is not None else [
            scale_factor]
        self.return_filename = return_filename

        # ===== 校验 =====
        self._validate_params()

        # ===== 加载文件列表 =====
        self.hr_files: List[str] = self._load_valid_files(hr_dir)
        self.lr_files: Optional[List[str]] = (
            self._load_valid_files(lr_dir) if lr_dir else None)

        if self.lr_files is not None:
            if len(self.hr_files) != len(self.lr_files):
                raise ValueError(
                    f"HR({len(self.hr_files)}) 与 LR({len(self.lr_files)}) "
                    f"文件数不匹配")

        # ===== 缓存（实例属性，避免跨数据集污染） =====
        self.cache: Dict[int, Tuple[torch.Tensor, torch.Tensor,
                                     Optional[str]]] = {}
        self.cache_dir: Optional[str] = None
        if self.cache_mode == 'memory':
            pass   # cache 已初始化
        elif self.cache_mode == 'disk':
            self.cache_dir = os.path.join('./cache', self.phase)
            os.makedirs(self.cache_dir, exist_ok=True)

        # ===== 数据统计 =====
        self.data_stats: Dict[str, Any] = {}
        self._compute_data_stats()

        logger.info(
            f"[{self.phase}] 加载完成 - HR: {len(self.hr_files)}, "
            f"scale={scale_factor}, cache={cache_mode}, "
            f"multi_scale={self.multi_scale}")

        # ===== 构建变换 =====
        self._build_transforms()

    # ---------- 校验 ----------
    def _validate_params(self):
        if self.phase not in ('train', 'val', 'test'):
            raise ValueError(f"无效 phase: {self.phase}")

        if self.crop_size % self.scale_factor != 0:
            new_size = self.crop_size - (self.crop_size % self.scale_factor)
            logger.warning(f"crop_size {self.crop_size} 修正为 {new_size}")
            self.crop_size = new_size

        if not os.path.exists(self.hr_dir):
            raise FileNotFoundError(f"HR 目录不存在: {self.hr_dir}")
        if self.lr_dir and not os.path.exists(self.lr_dir):
            raise FileNotFoundError(f"LR 目录不存在: {self.lr_dir}")

        assert self.cache_mode in ('none', 'memory', 'disk'), \
            f"无效缓存模式: {self.cache_mode}"

        for sf in self.multi_scale:
            assert isinstance(sf, int) and sf > 0, f"无效缩放因子: {sf}"

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

            if os.path.getsize(fpath) < 1024:
                logger.warning(f"跳过过小文件 {fpath} (< 1KB)")
                continue

            try:
                with Image.open(fpath) as img:
                    img.verify()
                    if (img.size[0] < self.crop_size
                            or img.size[1] < self.crop_size):
                        logger.warning(
                            f"跳过过小图像 {fpath} (size={img.size})")
                        continue
                files.append(fpath)
            except Exception as e:
                logger.warning(f"跳过无效图像 {fpath}: {e}")

        if not files:
            raise RuntimeError(f"目录 {dir_path} 无有效图像")
        return files

    # ---------- 数据统计 ----------
    def _compute_data_stats(self):
        if self.phase != 'train':
            return

        logger.info(f"[{self.phase}] 计算数据统计...")
        sample_num = min(100, len(self.hr_files))
        pixel_values = []

        indices = np.random.choice(len(self.hr_files), sample_num,
                                   replace=False)
        for idx in indices:
            try:
                with Image.open(self.hr_files[idx]) as img:
                    arr = np.array(img.convert('L')).astype(np.float32)
                    pixel_values.extend(arr.flatten())
            except Exception as e:
                logger.warning(f"统计样本 {idx} 失败: {e}")

        if not pixel_values:
            self.data_stats = {}
            return

        arr = np.array(pixel_values)
        self.data_stats = {
            'mean': float(np.mean(arr)),
            'std': float(np.std(arr)),
            'min': float(np.min(arr)),
            'max': float(np.max(arr)),
            'q01': float(np.quantile(arr, 0.01)),
            'q99': float(np.quantile(arr, 0.99)),
        }
        logger.info(f"[{self.phase}] 数据统计: {self.data_stats}")

    # ---------- 构建变换 ----------
    def _build_transforms(self):
        # 基础变换
        base: List[Callable] = [transforms.Lambda(lambda x: x.convert('L'))]
        if self.window_adjust:
            base.append(MedicalWindowAdjust())

        # 训练增强
        train_aug: List[Callable] = []
        if self.augment:
            train_aug = [
                transforms.RandomCrop(
                    self.crop_size, padding=8, pad_if_needed=True, fill=0),
                transforms.RandomHorizontalFlip(p=0.5),
                transforms.RandomVerticalFlip(p=0.5),
                transforms.RandomRotation(
                    degrees=(-15, 15), expand=False, fill=0),
                ElasticTransform(alpha=1.0, sigma=8.0, prob=0.3),
                transforms.Lambda(
                    lambda x: ImageEnhance.Contrast(x).enhance(
                        np.random.uniform(0.8, 1.2))),
                transforms.Lambda(
                    lambda x: ImageEnhance.Brightness(x).enhance(
                        np.random.uniform(0.9, 1.1))),
            ]

        # 验证/测试：中心裁剪
        val_test: List[Callable] = []
        if self.phase in ('val', 'test') and self.crop_size > 0:
            val_test = [transforms.CenterCrop(self.crop_size)]

        if self.phase == 'train':
            self.public_transform = transforms.Compose(base + train_aug)
        else:
            self.public_transform = transforms.Compose(base + val_test)

        # ===== LR 变换 =====
        lr_t: List[Callable] = []

        if self.phase == 'train':
            lr_t.append(AddMedicalNoise(self.noise_config))

        if self.phase == 'train' and len(self.multi_scale) > 1:
            lr_t.append(transforms.Lambda(
                lambda x: transforms.Resize(
                    self.crop_size // int(np.random.choice(self.multi_scale)),
                    interpolation=InterpolationMode.BICUBIC)(x)))
        else:
            lr_t.append(transforms.Lambda(
                lambda x: transforms.Resize(
                    (x.size[0] // self.scale_factor,
                     x.size[1] // self.scale_factor),
                    interpolation=InterpolationMode.BICUBIC)(x)))

        lr_t.append(transforms.ToTensor())
        if self.normalize:
            lr_t.append(AdaptiveNormalize(lower_q=0.01, upper_q=0.99))

        self.lr_transform = transforms.Compose(lr_t)

        # ===== HR 变换 =====
        hr_t: List[Callable] = [transforms.ToTensor()]
        if self.normalize:
            hr_t.append(AdaptiveNormalize(lower_q=0.01, upper_q=0.99))

        self.hr_transform = transforms.Compose(hr_t)

    # ---------- 图像清洗 ----------
    def _clean_image_data(self, img_np: np.ndarray) -> np.ndarray:
        img_np = np.nan_to_num(img_np, nan=0.0, posinf=255.0, neginf=0.0)
        img_np = np.clip(img_np, 0, 255)
        if CV_AVAILABLE and cv2 is not None:
            img_np = cv2.medianBlur(img_np.astype(np.uint8), 3)
        return img_np

    # ---------- 缓存 ----------
    def _load_from_cache(self, index: int):
        if self.cache_mode == 'memory':
            return self.cache.get(index, None)
        elif self.cache_mode == 'disk' and self.cache_dir:
            path = os.path.join(self.cache_dir, f"{index}.pth")
            if os.path.exists(path):
                return torch.load(path, weights_only=False)
        return None

    def _save_to_cache(self, index: int, data):
        if self.cache_mode == 'memory':
            self.cache[index] = data
        elif self.cache_mode == 'disk' and self.cache_dir:
            path = os.path.join(self.cache_dir, f"{index}.pth")
            torch.save(data, path)

    # ---------- 单样本 ----------
    def __getitem__(self, index: int):
        cached = self._load_from_cache(index)
        if cached is not None:
            return cached

        try:
            hr_path = self.hr_files[index]
            with Image.open(hr_path) as f:
                image_pil = f.convert('L')
            image_np = np.array(image_pil)

            image_np = self._clean_image_data(image_np)
            img_hr = Image.fromarray(image_np.astype(np.uint8))

            x = self.public_transform(img_hr)

            if self.lr_files:
                lr_path = self.lr_files[index]
                with Image.open(lr_path) as f:
                    img_lr = f.convert('L')
                img_lr = self.public_transform(img_lr)
                y_lr = cast(torch.Tensor, self.lr_transform(img_lr))
            else:
                y_lr = cast(torch.Tensor, self.lr_transform(x))

            y_hr = cast(torch.Tensor, self.hr_transform(x))

            # NaN/Inf 兜底
            if torch.isnan(y_lr).any() or torch.isinf(y_lr).any():
                y_lr = torch.nan_to_num(y_lr, nan=0.0, posinf=1.0, neginf=-1.0)
                y_lr = torch.clamp(y_lr, -1.0, 1.0)
            if torch.isnan(y_hr).any() or torch.isinf(y_hr).any():
                y_hr = torch.nan_to_num(y_hr, nan=0.0, posinf=1.0, neginf=-1.0)
                y_hr = torch.clamp(y_hr, -1.0, 1.0)

            filename = (None if self.phase == 'train'
                        else os.path.splitext(os.path.basename(hr_path))[0])
            data = (y_lr, y_hr, filename)
            self._save_to_cache(index, data)

            if self.return_filename:
                return data
            return y_lr, y_hr

        except Exception as e:
            logger.error(f"处理样本 {index} 失败: {e}")
            sf = (int(np.random.choice(self.multi_scale))
                  if (self.phase == 'train' and len(self.multi_scale) > 1)
                  else self.scale_factor)
            lr_h = max(1, self.crop_size // sf)
            lr_w = max(1, self.crop_size // sf)
            y_lr = torch.zeros((1, lr_h, lr_w), dtype=torch.float32)
            y_hr = torch.zeros((1, self.crop_size, self.crop_size),
                               dtype=torch.float32)
            filename = f"error_{index}" if self.phase != 'train' else None

            if self.return_filename:
                return y_lr, y_hr, filename
            return y_lr, y_hr

    def __len__(self):
        return len(self.hr_files)

    # ---------- 辅助 ----------
    def get_filename_list(self) -> List[str]:
        return [os.path.splitext(os.path.basename(f))[0]
                for f in self.hr_files]

    def get_image_shape(self, index: int = 0) -> Tuple[int, int]:
        with Image.open(self.hr_files[index]) as img:
            return img.size[1], img.size[0]   # H, W

    def clear_cache(self):
        if self.cache_mode == 'memory':
            self.cache.clear()
        elif self.cache_mode == 'disk' and self.cache_dir:
            import shutil
            if os.path.exists(self.cache_dir):
                shutil.rmtree(self.cache_dir)
                os.makedirs(self.cache_dir)
        logger.info(f"[{self.phase}] 缓存已清理")
