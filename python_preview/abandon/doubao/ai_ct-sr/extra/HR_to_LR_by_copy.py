import os
import cv2 as cv
import numpy as np
from PIL import Image
import argparse
from pathlib import Path
import random
from tqdm import tqdm


class LRImageGenerator:
    def __init__(self, scale_factor=4, method='bicubic',
                 add_noise=False, add_blur=False):
        self.scale_factor = scale_factor
        self.method = method
        self.add_noise = add_noise
        self.add_blur = add_blur

    def downsample_bicubic(self, img):
        """双三次插值下采样"""
        h, w = img.shape[:2]
        new_h, new_w = h // self.scale_factor, w // self.scale_factor
        return cv.resize(img, (new_w, new_h), interpolation=cv.INTER_CUBIC)

    def downsample_lanczos(self, img):
        """Lanczos 插值下采样"""
        h, w = img.shape[:2]
        new_h, new_w = h // self.scale_factor, w // self.scale_factor
        return cv.resize(img, (new_w, new_h), interpolation=cv.INTER_LANCZOS4)

    def downsample_area(self, img):
        """区域插值下采样"""
        h, w = img.shape[:2]
        new_h, new_w = h // self.scale_factor, w // self.scale_factor
        return cv.resize(img, (new_w, new_h), interpolation=cv.INTER_AREA)

    def add_gaussian_noise(self, img, mean=0, sigma=25):
        """添加高斯噪声"""
        noise = np.random.normal(mean, sigma, img.shape).astype(np.float32)
        noisy_img = img.astype(np.float32) + noise
        return np.clip(noisy_img, 0, 255).astype(np.uint8)

    def add_gaussian_blur(self, img, kernel_size=5, sigma=1.0):
        """添加高斯模糊"""
        return cv.GaussianBlur(img, (kernel_size, kernel_size), sigma)

    def generate_lr_from_hr(self, hr_img):
        """从 HR 图像生成 LR 图像"""
        if isinstance(hr_img, Image.Image):
            hr_array = np.array(hr_img)
        else:
            hr_array = hr_img

        if self.method == 'bicubic':
            lr_array = self.downsample_bicubic(hr_array)
        elif self.method == 'lanczos':
            lr_array = self.downsample_lanczos(hr_array)
        elif self.method == 'area':
            lr_array = self.downsample_area(hr_array)
        else:
            lr_array = self.downsample_bicubic(hr_array)

        if self.add_noise:
            lr_array = self.add_gaussian_noise(lr_array)

        if self.add_blur:
            lr_array = self.add_gaussian_blur(lr_array)

        return Image.fromarray(lr_array)

    def generate_patch_pairs(self, hr_img, patch_size=48):
        """生成图像块对（用于训练）"""
        hr_array = np.array(hr_img)
        h, w = hr_array.shape[:2]

        big = patch_size * self.scale_factor
        if h < big or w < big:
            return None, None

        x = random.randint(0, w - big)
        y = random.randint(0, h - big)

        hr_patch = hr_array[y:y + big, x:x + big]

        lr_patch_array = self.downsample_bicubic(hr_patch)
        lr_patch = Image.fromarray(lr_patch_array)
        hr_patch_img = Image.fromarray(hr_patch)

        return hr_patch_img, lr_patch


def process_dataset(input_dir, output_dir, scale_factor=4, method='bicubic',
                    add_noise=False, add_blur=False, create_patches=False,
                    patch_size=48, num_patches=16):
    """
    处理整个数据集，从 HR 图像生成 LR 图像

    参数:
        input_dir:      输入目录（包含 train/HR, val/HR, test/HR）
        output_dir:     输出目录
        scale_factor:   下采样比例
        method:         下采样方法 ('bicubic', 'lanczos', 'area')
        add_noise:      是否添加噪声
        add_blur:       是否添加模糊
        create_patches: 是否创建图像块
        patch_size:     HR 块大小
        num_patches:    每张图像生成的块数
    """
    generator = LRImageGenerator(
        scale_factor=scale_factor,
        method=method,
        add_noise=add_noise,
        add_blur=add_blur,
    )

    valid_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff'}

    for split in ['train', 'val', 'test']:
        hr_dir = os.path.join(input_dir, split, 'HR')
        lr_dir = os.path.join(output_dir, split, 'LR')
        patches_hr_dir = os.path.join(output_dir, split, 'HR_patches')
        patches_lr_dir = os.path.join(output_dir, split, 'LR_patches')

        if not os.path.exists(hr_dir):
            print(f"跳过 {split} - HR 目录不存在: {hr_dir}")
            continue

        os.makedirs(lr_dir, exist_ok=True)
        if create_patches:
            os.makedirs(patches_hr_dir, exist_ok=True)
            os.makedirs(patches_lr_dir, exist_ok=True)

        print(f"\n处理 {split} 集...")

        hr_files = []
        for ext in valid_extensions:
            hr_files.extend(list(Path(hr_dir).glob(f'*{ext}')))
            hr_files.extend(list(Path(hr_dir).glob(f'*{ext.upper()}')))

        if not hr_files:
            print(f"在 {hr_dir} 中未找到图像文件")
            continue

        for hr_path in tqdm(hr_files, desc=f"生成 {split} LR图像"):
            try:
                hr_img = Image.open(hr_path)

                lr_img = generator.generate_lr_from_hr(hr_img)
                lr_save_path = os.path.join(lr_dir, hr_path.name)
                lr_img.save(lr_save_path)

                if create_patches and split == 'train':
                    base_name = hr_path.stem
                    for i in range(num_patches):
                        hr_patch, lr_patch = generator.generate_patch_pairs(
                            hr_img, patch_size)
                        if hr_patch is not None and lr_patch is not None:
                            hr_patch.save(os.path.join(
                                patches_hr_dir, f"{base_name}_patch{i:d}.png"))
                            lr_patch.save(os.path.join(
                                patches_lr_dir, f"{base_name}_patch{i:d}.png"))

            except Exception as e:
                print(f"处理图像 {hr_path} 时出错: {e}")
                continue


def main():
    parser = argparse.ArgumentParser(
        description='从 HR 图像生成 LR 图像用于超分辨率训练')
    parser.add_argument('--input_dir', type=str, required=True,
                        help='输入目录，包含 train/HR, val/HR, test/HR 子目录')
    parser.add_argument('--output_dir', type=str, required=True,
                        help='输出目录')
    parser.add_argument('--scale_factor', type=int, default=4,
                        help='下采样比例 (默认: 4)')
    parser.add_argument('--method', type=str, default='bicubic',
                        choices=['bicubic', 'lanczos', 'area'],
                        help='下采样方法 (默认: bicubic)')
    parser.add_argument('--add_noise', action='store_true',
                        help='添加高斯噪声到 LR 图像')
    parser.add_argument('--add_blur', action='store_true',
                        help='添加高斯模糊到 LR 图像')
    parser.add_argument('--create_patches', action='store_true',
                        help='为训练集创建图像块')
    parser.add_argument('--patch_size', type=int, default=48,
                        help='HR 块大小 (默认: 48)')
    parser.add_argument('--num_patches', type=int, default=16,
                        help='每张图像生成的块数 (默认: 16)')

    args = parser.parse_args()

    print("开始生成 LR 图像...")
    print(f"输入目录: {args.input_dir}")
    print(f"输出目录: {args.output_dir}")
    print(f"下采样比例: {args.scale_factor}")
    print(f"下采样方法: {args.method}")
    print(f"添加噪声: {args.add_noise}")
    print(f"添加模糊: {args.add_blur}")
    print(f"创建图像块: {args.create_patches}")

    if args.create_patches:
        print(f"块大小: {args.patch_size}")
        print(f"每图像块数: {args.num_patches}")

    process_dataset(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        scale_factor=args.scale_factor,
        method=args.method,
        add_noise=args.add_noise,
        add_blur=args.add_blur,
        create_patches=args.create_patches,
        patch_size=args.patch_size,
        num_patches=args.num_patches,
    )

    print(f"\nLR 图像生成完成!")
    print(f"输出目录结构:")
    print(f"{args.output_dir}/")
    print("├── train/")
    print("│   ├── LR/           低分辨率训练图像")
    if args.create_patches:
        print("│   ├── HR_patches/   HR 训练块")
        print("│   └── LR_patches/   LR 训练块")
    print("├── val/")
    print("│   └── LR/           低分辨率验证图像")
    print("└── test/")
    print("    └── LR/           低分辨率测试图像")


if __name__ == "__main__":
    main()
