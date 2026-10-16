 导入本科阶段必学的基础库
import os
import cv
import numpy as np
from PIL import Image
import argparse
from tqdm import tqdm   进度条，方便看处理进度（本科常用）

 ===================== 核心函数：生成超分训练用的低分辨率图片 =====================


def generate_lr_image(hr_image_path, lr_save_path, hr_save_path, scale=, noise_level=.):
    """
    生成超分训练用的低分辨率（LR）图片，同时保存对应的高分辨率（HR）图片作为标签
    :param hr_image_path: 原始高清图片路径
    :param lr_save_path: 生成的低清图片保存路径
    :param hr_save_path: 对应的高清标签图片保存路径
    :param scale: 下采样比例（超分常用倍，即HR是LR的倍尺寸）
    :param noise_level: 可选：添加高斯噪声（模拟真实低分图片的噪声，=无噪声）
    """
     . 读取高清图片（优先用PIL，兼容更多格式，本科阶段重点掌握）
    try:
         打开图片并转为RGB格式（避免灰度图干扰，超分训练常用RGB）
        hr_img = Image.open(hr_image_path).convert('RGB')
    except Exception as e:
        print(f"读取图片失败 {hr_image_path}：{e}")
        return False

     . 预处理高清图：确保尺寸是scale的整数倍（超分训练关键！避免尺寸不匹配）
    hr_width, hr_height = hr_img.size
     计算能被scale整除的最大尺寸（比如scale=时，宽高都要能被整除）
    new_hr_width = hr_width - (hr_width % scale)
    new_hr_height = hr_height - (hr_height % scale)
     裁剪高清图到适配尺寸（本科阶段学过的图像裁剪操作）
    hr_img = hr_img.crop((, , new_hr_width, new_hr_height))
    hr_width, hr_height = hr_img.size   更新裁剪后的尺寸

     . 生成低分辨率图片（超分训练核心步骤：模拟真实低分图）
     步骤：下采样（用双三次插值，这是超分训练中生成LR图的标准方法，本科课件必讲）
    lr_width = hr_width // scale
    lr_height = hr_height // scale
    lr_img = hr_img.resize((lr_width, lr_height), Image.Resampling.BICUBIC)   BICUBIC是本科阶段重点插值方法

     步骤：可选：添加高斯噪声（模拟真实场景的低分图噪声，本科概率论中的高斯分布应用）
    if noise_level > :
         将PIL图片转为numpy数组（本科阶段必学的图像数据格式转换）
        lr_np = np.array(lr_img, dtype=np.float) / .   归一化到-，方便加噪声
         生成高斯噪声（均值，标准差noise_level）
        noise = np.random.normal(, noise_level, lr_np.shape)
        lr_np = lr_np + noise
         裁剪到-范围（避免像素值溢出）
        lr_np = np.clip(lr_np, ., .)
         转回PIL图片
        lr_img = Image.fromarray((lr_np  ).astype(np.uint))

     . 保存图片（超分训练的数据集格式：LR和HR一一对应）
    try:
         保存低分辨率图（训练时的输入）
        lr_img.save(lr_save_path, quality=)   quality=保证LR图质量，避免压缩失真
         保存高分辨率图（训练时的标签）
        hr_img.save(hr_save_path, quality=)
        return True
    except Exception as e:
        print(f"保存图片失败：{e}")
        return False

 ===================== 批量处理函数：处理整个文件夹的图片 =====================


def batch_generate_lr_hr(input_dir, output_dir, scale=, noise_level=.):
    """
    批量处理文件夹中的所有图片，生成超分训练用的LR/HR数据集
    :param input_dir: 原始高清图片文件夹
    :param output_dir: 输出文件夹（会自动创建LR和HR两个子文件夹）
    :param scale: 下采样比例
    :param noise_level: 高斯噪声强度
    """
     . 创建输出文件夹（本科阶段的文件操作基础）
    lr_dir = os.path.join(output_dir, "LR")   低分辨率图片文件夹
    hr_dir = os.path.join(output_dir, "HR")   高分辨率标签文件夹
    os.makedirs(lr_dir, exist_ok=True)
    os.makedirs(hr_dir, exist_ok=True)

     . 获取文件夹中所有图片（过滤支持的格式）
    supported_formats = ('.jpg', '.jpeg', '.png', '.bmp')   本科阶段常用图片格式
    image_paths = []
    for file in os.listdir(input_dir):
        if file.lower().endswith(supported_formats):
            image_paths.append(os.path.join(input_dir, file))

    if len(image_paths) == :
        print(f"文件夹 {input_dir} 中没有找到支持的图片格式（{supported_formats}）")
        return

     . 批量处理（用tqdm显示进度条，本科项目中常用）
    success_count = 
    for img_path in tqdm(image_paths, desc="生成超分训练数据"):
         获取文件名（用于保持LR/HR文件名一致）
        img_name = os.path.basename(img_path)
         构建保存路径
        lr_save_path = os.path.join(lr_dir, img_name)
        hr_save_path = os.path.join(hr_dir, img_name)
         生成LR/HR图片
        if generate_lr_image(img_path, lr_save_path, hr_save_path, scale, noise_level):
            success_count += 

     . 输出处理结果（本科项目的结果可视化基础）
    print(f"\n处理完成！")
    print(f"总图片数：{len(image_paths)} | 成功生成：{success_count}")
    print(f"LR图片保存路径：{lr_dir}")
    print(f"HR图片保存路径：{hr_dir}")

 ===================== 主函数：解析命令行参数（本科阶段的工程化基础） =====================


def main():
     解析命令行参数（本科AI项目中常用，方便调整参数不用改代码）
    parser = argparse.ArgumentParser(description="生成超分训练用的低分辨率图片（本科AI易懂版）")
    parser.add_argument("--input_dir", "-i", required=True, help="原始高清图片文件夹路径（必填）")
    parser.add_argument("--output_dir", "-o", default="./sr_train_data", help="输出LR/HR数据集的文件夹（默认：./sr_train_data）")
    parser.add_argument("--scale", "-s", type=int, default=, help="超分比例（默认倍，即HR是LR的倍尺寸）")
    parser.add_argument("--noise", "-n", type=float, default=., help="高斯噪声强度（默认.，=无噪声）")

    args = parser.parse_args()

     调用批量处理函数
    batch_generate_lr_hr(args.input_dir, args.output_dir, args.scale, args.noise)


 ===================== 运行入口（本科Python编程的标准写法） =====================
if __name__ == "__main__":
    main()
