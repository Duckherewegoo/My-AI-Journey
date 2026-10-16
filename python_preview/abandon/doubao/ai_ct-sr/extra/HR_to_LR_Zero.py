import os
import shutil
from pathlib import Path
from PIL import Image
import argparse
import pandas as pd


def is_hard_link_or_copy(file_path):
    """
    检查文件是否是硬链接或复制。
    返回: True 如果是硬链接或复制，False 如果是独立文件。
    """
    try:
        # 硬链接计数 > 1 说明有多处引用
        if os.stat(file_path).st_nlink > 1:
            return True

        # 空文件通常是占位符
        if os.path.getsize(file_path) == 0:
            return True

        # 尝试当图像打开，打不开说明是坏文件/占位符
        try:
            with Image.open(file_path) as img:
                img.verify()
        except Exception:
            return True

    except Exception as e:
        print(f"检查文件 {file_path} 时出错: {e}")

    return False


def clear_lr_directory(lr_dir):
    """清空 LR 目录，特别是硬链接或复制文件。"""
    if not os.path.exists(lr_dir):
        print(f"LR目录不存在: {lr_dir}")
        return

    print(f"正在清理LR目录: {lr_dir}")
    deleted_count = 0

    for filename in os.listdir(lr_dir):
        file_path = os.path.join(lr_dir, filename)

        if not os.path.isfile(file_path):
            continue

        if is_hard_link_or_copy(file_path):
            print(f"删除硬链接/复制文件: {filename}")
            os.remove(file_path)
            deleted_count += 1
        else:
            response = input(f"文件 {filename} 不是硬链接，是否删除？(y/n): ").lower().strip()
            if response == 'y':
                os.remove(file_path)
                deleted_count += 1

    print(f"清理完成，删除了 {deleted_count} 个文件")


def create_lr_images_from_hr(hr_dir, lr_dir, scale_factor=4, quality=95):
    """
    从 HR 图像创建真正的 LR 图像（下采样）。

    参数:
        hr_dir:       HR 图像目录
        lr_dir:       LR 图像输出目录
        scale_factor: 下采样比例
        quality:      JPEG 保存质量
    """
    os.makedirs(lr_dir, exist_ok=True)

    supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif')

    hr_files = [
        f for f in os.listdir(hr_dir)
        if f.lower().endswith(supported_formats)
        and os.path.isfile(os.path.join(hr_dir, f))
    ]

    if not hr_files:
        print(f"在 {hr_dir} 中没有找到支持的图像文件")
        return

    print(f"找到 {len(hr_files)} 个HR图像文件")
    print("开始生成LR图像...")

    processed_count = 0
    error_count = 0

    for filename in hr_files:
        hr_path = os.path.join(hr_dir, filename)
        lr_path = os.path.join(lr_dir, filename)

        try:
            with Image.open(hr_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                width, height = img.size
                lr_width = max(width // scale_factor, 1)
                lr_height = max(height // scale_factor, 1)

                lr_img = img.resize((lr_width, lr_height), Image.BICUBIC)

                if filename.lower().endswith(('.jpg', '.jpeg')):
                    lr_img.save(lr_path, 'JPEG', quality=quality)
                else:
                    lr_img.save(lr_path)

                processed_count += 1

                if processed_count % 100 == 0:
                    print(f"已处理 {processed_count} 个图像...")

        except Exception as e:
            print(f"处理图像 {filename} 时出错: {e}")
            error_count += 1

    print(f"\nLR图像生成完成!")
    print(f"成功处理: {processed_count} 个图像")
    print(f"处理失败: {error_count} 个图像")

    info_file = os.path.join(lr_dir, 'lr_generation_info.txt')
    with open(info_file, 'w') as f:
        f.write("LR图像生成信息\n")
        f.write("=" * 60 + "\n")
        f.write(f"HR目录: {hr_dir}\n")
        f.write(f"LR目录: {lr_dir}\n")
        f.write(f"下采样比例: {scale_factor}\n")
        f.write(f"成功处理: {processed_count} 个图像\n")
        f.write(f"处理失败: {error_count} 个图像\n")
        f.write(f"生成时间: {pd.Timestamp.now()}\n")


def main():
    parser = argparse.ArgumentParser(description='从HR图像生成真正的LR图像')
    parser.add_argument('--hr_dir', type=str, required=True,
                        help='HR图像目录路径')
    parser.add_argument('--lr_dir', type=str, required=True,
                        help='LR图像输出目录路径')
    parser.add_argument('--scale', type=int, default=4,
                        help='下采样比例 (默认: 4)')
    parser.add_argument('--quality', type=int, default=95,
                        help='JPEG保存质量 (默认: 95)')
    parser.add_argument('--auto_clear', action='store_true',
                        help='自动清理LR目录而不询问')

    args = parser.parse_args()

    if not os.path.exists(args.hr_dir):
        print(f"错误: HR目录不存在 - {args.hr_dir}")
        return

    if os.path.exists(args.lr_dir) and os.listdir(args.lr_dir):
        if args.auto_clear:
            clear_lr_directory(args.lr_dir)
        else:
            response = input(
                f"LR目录 {args.lr_dir} 不为空，是否清理硬链接/复制文件？(y/n): "
            ).lower().strip()
            if response == 'y':
                clear_lr_directory(args.lr_dir)
            else:
                print("跳过清理步骤")

    create_lr_images_from_hr(args.hr_dir, args.lr_dir,
                             args.scale, args.quality)


if __name__ == "__main__":
    # 直接运行时的默认路径（不走命令行参数）
    HR_DIR = "./Key_slices_opt/train/HR"
    LR_DIR = "./Key_slices_opt/train/LR"
    SCALE_FACTOR = 4

    if os.path.exists(HR_DIR):
        if os.path.exists(LR_DIR) and os.listdir(LR_DIR):
            response = input(
                f"LR目录 {LR_DIR} 不为空，是否清理硬链接/复制文件？(y/n): "
            ).lower().strip()
            if response == 'y':
                clear_lr_directory(LR_DIR)

        create_lr_images_from_hr(HR_DIR, LR_DIR, SCALE_FACTOR)
    else:
        print(f"HR目录不存在: {HR_DIR}")
        print("请修改脚本中的 HR_DIR 和 LR_DIR 变量，或使用命令行参数运行")
        print("\n使用方法:")
        print("python script.py --hr_dir /path/to/hr --lr_dir /path/to/lr --scale 4")
