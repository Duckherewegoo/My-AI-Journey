import os
import cv2 as cv
import numpy as np
from PIL import Image
from pathlib import Path
from tqdm import tqdm


def generate_lr_images_move(base_dir, scale_factor=4):
    """
    从 HR 图像创建 LR 图像（移动版本，直接替换 HR 图像为下采样版本）

    参数:
        base_dir:     数据集基础目录
        scale_factor: 下采样比例
    """
    print("开始生成 LR 图像（移动版本）...")

    for split in ['train', 'val', 'test']:
        hr_dir = os.path.join(base_dir, split, 'HR')
        lr_dir = os.path.join(base_dir, split, 'LR')

        if not os.path.exists(hr_dir):
            print(f"跳过 {split} - HR 目录不存在")
            continue

        os.makedirs(lr_dir, exist_ok=True)

        valid_extensions = {'.png', '.jpg', '.jpeg', '.bmp'}
        hr_files = []
        for ext in valid_extensions:
            hr_files.extend(list(Path(hr_dir).glob(f'*{ext}')))
            hr_files.extend(list(Path(hr_dir).glob(f'*{ext.upper()}')))

        if not hr_files:
            print(f"在 {hr_dir} 中未找到图像文件")
            continue

        print(f"\n处理 {split} 集...")

        for hr_path in tqdm(hr_files, desc=f"生成 {split} LR图像"):
            try:
                hr_img = cv.imread(str(hr_path))
                if hr_img is None:
                    continue

                h, w = hr_img.shape[:2]
                lr_h = h // scale_factor
                lr_w = w // scale_factor

                lr_img = cv.resize(hr_img, (lr_w, lr_h),
                                   interpolation=cv.INTER_CUBIC)

                lr_save_path = os.path.join(lr_dir, hr_path.name)
                cv.imwrite(lr_save_path, lr_img)

            except Exception as e:
                print(f"处理 {hr_path} 时出错: {e}")

    print("\nLR 图像生成完成!")


if __name__ == "__main__":
    DATASET_DIR = "deeplesion_sr_dataset"
    SCALE_FACTOR = 4

    generate_lr_images_move(DATASET_DIR, SCALE_FACTOR)
