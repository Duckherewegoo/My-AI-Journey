import os
import shutil
import pandas as pd
from pathlib import Path


def organize_deeplesion_dataset_move(csv_path, source_dir, target_dir):
    """
    根据 DL_info.csv 将 DeepLesion 组织为 train / val / test（移动文件而非复制）。

    参数:
        csv_path:   DL_info.csv 路径
        source_dir: 原始 key_slices 目录
        target_dir: 目标目录
    """
    df = pd.read_csv(csv_path)

    # DeepLesion 的 Train_Val_Test：1=train, 2=val, 3=test
    splits = {
        1: 'train',
        2: 'val',
        3: 'test',
    }

    os.makedirs(target_dir, exist_ok=True)
    for split_name in splits.values():
        os.makedirs(os.path.join(target_dir, split_name, 'HR'), exist_ok=True)
        os.makedirs(os.path.join(target_dir, split_name, 'LR'), exist_ok=True)

    counts = {1: 0, 2: 0, 3: 0}
    moved_files = []

    print("开始组织数据集（移动文件）...")

    for index, row in df.iterrows():
        filename = row['File_name']
        split_id = row['Train_Val_Test']

        source_file = os.path.join(source_dir, filename)

        if not os.path.exists(source_file):
            print(f"警告: 文件不存在 - {source_file}")
            continue

        split_name = splits[split_id]
        target_file_hr = os.path.join(target_dir, split_name, 'HR', filename)

        try:
            shutil.move(source_file, target_file_hr)
            moved_files.append(source_file)
            counts[split_id] += 1

            # LR 目录先用硬链接占位，create_lr_images_from_hr_move 里会清掉重做
            target_file_lr = os.path.join(target_dir, split_name, 'LR', filename)
            try:
                os.link(target_file_hr, target_file_lr)
            except (AttributeError, OSError):
                # 不支持硬链接（比如跨盘），退回复制
                shutil.copy(target_file_hr, target_file_lr)

        except Exception as e:
            print(f"移动文件时出错 {source_file}: {e}")

    print("\n数据集组织完成!")
    print("各集合图像数量:")
    for split_id, count in counts.items():
        print(f"  {splits[split_id]}: {count} 张图像")

    total_images = sum(counts.values())
    print(f"\n总计: {total_images} 张图像")
    print(f"已移动文件数: {len(moved_files)}")

    info_file = os.path.join(target_dir, 'dataset_info.txt')
    with open(info_file, 'w') as f:
        f.write("DeepLesion 超分辨率数据集信息\n")
        f.write("=" * 60 + "\n")
        for split_id, count in counts.items():
            f.write(f"{splits[split_id]}: {count} 张图像\n")
        f.write(f"\n总计: {total_images} 张图像\n")
        f.write(f"原始 CSV 文件: {csv_path}\n")
        f.write(f"组织时间: {pd.Timestamp.now()}\n")
        f.write(f"操作: 移动文件（非复制）\n")


def create_lr_images_from_hr_move(target_dir, scale_factor=4):
    """
    从 HR 生成 LR（双三次下采样，移动版）。

    参数:
        target_dir:   目标目录
        scale_factor: 下采样倍数，默认 4
    """
    from PIL import Image

    print("\n开始创建 LR 图像...")

    for split in ['train', 'val', 'test']:
        hr_dir = os.path.join(target_dir, split, 'HR')
        lr_dir = os.path.join(target_dir, split, 'LR')

        if not os.path.exists(hr_dir):
            continue

        # 清空 LR 目录：可能是硬链接，也可能是复制的文件
        for file in os.listdir(lr_dir):
            file_path = os.path.join(lr_dir, file)
            if os.path.islink(file_path) or os.path.isfile(file_path):
                os.remove(file_path)

        for filename in os.listdir(hr_dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                hr_path = os.path.join(hr_dir, filename)
                lr_path = os.path.join(lr_dir, filename)

                try:
                    with Image.open(hr_path) as img:
                        width, height = img.size
                        lr_width = width // scale_factor
                        lr_height = height // scale_factor
                        lr_img = img.resize((lr_width, lr_height), Image.BICUBIC)
                        lr_img.save(lr_path)
                except Exception as e:
                    print(f"处理图像 {filename} 时出错: {e}")

        print(f"完成 {split} 集的 LR 图像生成")


if __name__ == "__main__":
    CSV_FILE_PATH = "DL_info.csv"
    SOURCE_IMAGE_DIR = "key_slices"
    TARGET_DIR = "deeplesion_sr_dataset"

    if not os.path.exists(CSV_FILE_PATH):
        print(f"错误: 找不到 CSV 文件 {CSV_FILE_PATH}")
        exit()

    if not os.path.exists(SOURCE_IMAGE_DIR):
        print(f"错误: 找不到源图像目录 {SOURCE_IMAGE_DIR}")
        exit()

    print("警告: 此操作将移动文件而不是复制，原始文件将被移动到新位置。")
    confirm = input("确定要继续吗？(输入 'yes' 继续): ")
    if confirm.lower() != 'yes':
        print("操作已取消")
        exit()

    organize_deeplesion_dataset_move(CSV_FILE_PATH, SOURCE_IMAGE_DIR, TARGET_DIR)

    create_lr = input("\n是否要从 HR 图像创建 LR 图像？(y/n): ").lower().strip()
    if create_lr == 'y':
        scale = input("请输入下采样比例 (默认 4): ").strip()
        scale_factor = int(scale) if scale.isdigit() else 4
        create_lr_images_from_hr_move(TARGET_DIR, scale_factor)

    print(f"\n数据集已成功组织到: {TARGET_DIR}")
    print("目录结构:")
    print(f"{TARGET_DIR}/")
    print("├── train/")
    print("│   ├── HR/     高分辨率训练图像")
    print("│   └── LR/     低分辨率训练图像")
    print("├── val/")
    print("│   ├── HR/     高分辨率验证图像")
    print("│   └── LR/     低分辨率验证图像")
    print("├── test/")
    print("│   ├── HR/     高分辨率测试图像")
    print("│   └── LR/     低分辨率测试图像")
    print("└── dataset_info.txt   数据集信息")
