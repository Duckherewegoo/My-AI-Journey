import os
import torch

 ===================== 【全局配置】 =====================
 权重根目录（扫描整个文件夹）
WEIGHT_ROOT = "/run/media/dake/Software/Projects/Graduction_Projects/codes/nova/lu_mwcnn/mainline/continual_ckpt"
 结果保存文件
RESULT_FILE = "all_ct_weights_metrics.txt"
 设备
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

 ===================== 【核心：扫描所有pth文件】 =====================


def scan_all_pth_files():
    """递归扫描根目录下所有子文件夹的 .pth 权重文件"""
    weight_files = []
    for root_dir, sub_dirs, files in os.walk(WEIGHT_ROOT):
        for file in files:
            if file.endswith(".pth"):
                full_path = os.path.join(root_dir, file)
                 存储：(相对文件夹路径, 文件名, 完整路径)
                relative_folder = os.path.relpath(root_dir, WEIGHT_ROOT)
                weight_files.append((relative_folder, file, full_path))
    print(f" 扫描完成：共找到 {len(weight_files)} 个 .pth 权重文件")
    return weight_files

 ===================== 【核心：兼容两种格式读取指标】 =====================


def read_metrics_from_pth(weight_path):
    """
    兼容两种保存格式：
    . 普通epoch权重：包含 best_psnr, best_ssim, best_lpips
    . best开头权重：包含 best_xxx + current_metrics 子字典
    """
    try:
         加载完整 checkpoint
        checkpoint = torch.load(weight_path, map_location=DEVICE, weights_only=False)
        epoch = checkpoint.get("epoch", "未知")

         -------- 格式：普通epoch权重 --------
        if "best_psnr" in checkpoint and "best_ssim" in checkpoint and "best_lpips" in checkpoint:
            psnr = round(checkpoint["best_psnr"], )
            ssim = round(checkpoint["best_ssim"], )
            lpips = round(checkpoint["best_lpips"], )
            return True, psnr, ssim, lpips, epoch

         -------- 格式：best_ 最佳权重（current_metrics） --------
        elif "current_metrics" in checkpoint:
            metrics = checkpoint["current_metrics"]
            psnr = round(metrics.get("psnr", ), )
            ssim = round(metrics.get("ssim", ), )
            lpips = round(metrics.get("lpips", ), )
            return True, psnr, ssim, lpips, epoch

         无指标数据
        else:
            return False, , , , "未知"

     读取失败/损坏文件
    except Exception as e:
        return False, , , , "读取失败"


 ===================== 【主程序】 =====================
if __name__ == "__main__":
    print("="  )
    print(" 全目录CT权重指标读取工具（兼容普通+best格式）")
    print("="  )

     . 扫描所有权重
    all_weights = scan_all_pth_files()
    success_list = []    读取成功列表
    failed_list = []     读取失败/未知列表

     . 遍历读取所有pth
    for folder, filename, path in all_weights:
        print(f"\n 处理: {folder}/{filename}")
        success, psnr, ssim, lpips, epoch = read_metrics_from_pth(path)

        if success:
            success_list.append((folder, filename, epoch, psnr, ssim, lpips))
            print(f" 读取成功 | Epoch:{epoch} | PSNR:{psnr} | SSIM:{ssim} | LPIPS:{lpips}")
        else:
            failed_list.append(f"{folder}/{filename}")
            print(f"️  跳过：无法读取指标")
        print("-"  )

     . 写入结果到文本文件
    with open(RESULT_FILE, "w", encoding="utf-") as f:
         标题
        f.write("="   + "\n")
        f.write(" 全部权重指标读取结果（自动兼容普通+best格式）\n")
        f.write("="   + "\n\n")

         成功列表
        f.write(" 【读取成功权重】\n")
        f.write("-"   + "\n")
        for item in success_list:
            folder, name, epoch, p, s, l = item
            f.write(f"[{folder}] {name} | Epoch:{epoch} | PSNR:{p} | SSIM:{s} | LPIPS:{l}\n")

         失败列表
        f.write("\n\n️  【无法读取指标/未知权重】\n")
        f.write("-"   + "\n")
        if failed_list:
            for failed_file in failed_list:
                f.write(f" {failed_file}\n")
        else:
            f.write(" 无读取失败的权重\n")

     . 控制台汇总
    print("\n" + "="  )
    print(f" 最终统计：")
    print(f"  成功读取：{len(success_list)} 个")
    print(f"️  失败/未知：{len(failed_list)} 个")
    print(f" 完整结果已保存至：{os.path.abspath(RESULT_FILE)}")
    print("="  )
