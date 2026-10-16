 ===================== 权重结果自动解析脚本 =====================
import os

 配置（直接用你生成的文件）
INPUT_FILE = "all_ct_weights_metrics.txt"
OUTPUT_FILE = "最优权重汇总.txt"

 固定分类：CT灰度图文件夹 / RGB图像文件夹
CT_FOLDERS = {
    "best_covid", "best_deeplesionkey_ct", "best_luna",
    "deeplesionkey_ct", "covid_ct", "luna"
}
RGB_FOLDERS = {
    "best_divk_rgb", "best_voc_rgb", "divk_rgb", "voc_rgb", "emergency"
}


def parse_metrics_file():
    """解析文本文件，提取所有权重数据"""
    ct_weights = []
    rgb_weights = []

    with open(INPUT_FILE, "r", encoding="utf-") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
         只解析有效数据行
        if line.startswith("[") and "|" in line:
            try:
                 拆分解析：[文件夹] 文件名 | Epoch:x | PSNR:x | SSIM:x | LPIPS:x
                folder_part = line.split("]")[].replace("[", "")
                rest = line.split("|")
                filename = line.split("]")[].split("|")[].strip()
                epoch = rest[].replace("Epoch:", "").strip()
                psnr = float(rest[].replace("PSNR:", "").strip())
                ssim = float(rest[].replace("SSIM:", "").strip())
                lpips = float(rest[].replace("LPIPS:", "").strip())

                 分类
                if folder_part in CT_FOLDERS:
                    ct_weights.append({
                        "folder": folder_part, "file": filename,
                        "epoch": epoch, "psnr": psnr, "ssim": ssim, "lpips": lpips
                    })
                elif folder_part in RGB_FOLDERS:
                    rgb_weights.append({
                        "folder": folder_part, "file": filename,
                        "epoch": epoch, "psnr": psnr, "ssim": ssim, "lpips": lpips
                    })
            except:
                continue
    return ct_weights, rgb_weights


def find_best_weights(weight_list):
    """找出 PSNR最高 / LPIPS最优 / 综合最优"""
    if not weight_list:
        return None, None, None

     PSNR 最大
    best_psnr = max(weight_list, key=lambda x: x["psnr"])
     LPIPS 最小（越低越真实，最优）
    best_lpips = min(weight_list, key=lambda x: x["lpips"])
     综合最优：PSNR最高 且 LPIPS最低（优先PSNR）
    best_overall = best_psnr

    return best_psnr, best_lpips, best_overall


def print_and_save_result(ct_data, rgb_data):
    """打印并保存最优结果"""
    ct_psnr, ct_lpips, ct_overall = find_best_weights(ct_data)
    rgb_psnr, rgb_lpips, rgb_overall = find_best_weights(rgb_data)

     拼接结果文本
    result = "="   + "\n"
    result += " 全量权重最优模型汇总（CT灰度图 / RGB图像）\n"
    result += "="   + "\n\n"

     CT 灰度图
    result += " 【CT 灰度图 最优权重】\n"
    result += "-"   + "\n"
    if ct_psnr:
        result += f" PSNR 最高：{ct_psnr['psnr']:.f} | {ct_psnr['folder']}/{ct_psnr['file']} | Epoch:{ct_psnr['epoch']}\n"
        result += f" LPIPS 最优：{ct_lpips['lpips']:.f} | {ct_lpips['folder']}/{ct_lpips['file']} | Epoch:{ct_lpips['epoch']}\n"
        result += f" 综合最强：{ct_overall['folder']}/{ct_overall['file']}\n"
    else:
        result += " 无CT灰度图数据\n"

     RGB 图像
    result += "\n 【RGB 自然图像 最优权重】\n"
    result += "-"   + "\n"
    if rgb_psnr:
        result += f" PSNR 最高：{rgb_psnr['psnr']:.f} | {rgb_psnr['folder']}/{rgb_psnr['file']} | Epoch:{rgb_psnr['epoch']}\n"
        result += f" LPIPS 最优：{rgb_lpips['lpips']:.f} | {rgb_lpips['folder']}/{rgb_lpips['file']} | Epoch:{rgb_lpips['epoch']}\n"
        result += f" 综合最强：{rgb_overall['folder']}/{rgb_overall['file']}\n"
    else:
        result += " 无RGB图像数据\n"

    result += "="   + "\n"

     打印控制台
    print(result)
     保存文件
    with open(OUTPUT_FILE, "w", encoding="utf-") as f:
        f.write(result)


 ===================== 运行 =====================
if __name__ == "__main__":
    print(" 正在解析权重结果文件...")
    ct_data, rgb_data = parse_metrics_file()
    print(f" 解析完成：CT灰度图 {len(ct_data)} 个 | RGB图像 {len(rgb_data)} 个")
    print_and_save_result(ct_data, rgb_data)
    print(f"\n 最优结果已保存至：{os.path.abspath(OUTPUT_FILE)}")
