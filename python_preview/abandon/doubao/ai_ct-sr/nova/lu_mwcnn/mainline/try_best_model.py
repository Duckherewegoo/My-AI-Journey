import os
import torch
import numpy as np
from tqdm import tqdm
import importlib
from PIL import Image

 ===================== 基础配置（和原训练代码保持一致） =====================
config = {
    "device": "cuda:" if torch.cuda.is_available() else "cpu",
    "dataset": {
        "test_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/test/HR",
        "interface": "deeplesions.DeepLesionDataset",
        "crop_size": ,
        "scale_factor": ,
        "noise_std": .,
    },
    "loss": {
        "use_mixed_loss": True,
        "l_weight": .,
        "mse_weight": .,
    },
    "model_path": r"/home/dake/Documents/Projects/Graduction_Projects/codes/nova/lu_mwcnn/output_deeplesion/ckp/best_model.pth",
    "save_pred_samples": True,   是否保存预测样本（可视化）
    "sample_save_dir": "./model_evaluation_samples",
}

 ===================== 必要函数（修复.item()报错） =====================
 . 混合损失函数（和原代码一致）


class MixedLoss(torch.nn.Module):
    def __init__(self, l_weight=., mse_weight=.):
        super().__init__()
        self.l = torch.nn.LLoss()
        self.mse = torch.nn.MSELoss()
        self.l_weight = l_weight
        self.mse_weight = mse_weight

    def forward(self, pred, target):
        pred = torch.clamp(pred, ., .)
        target = torch.clamp(target, ., .)
        return self.l_weight  self.l(pred, target) + self.mse_weight  self.mse(pred, target)

 . 指标计算（修复返回类型，确保统一为数值）


def calc_psnr_torch(pred, target, max_val=.):
    mse = torch.mean((pred - target)  )
    if mse == :
        return float('inf')   原生float
     先转张量为数值，再计算
    psnr_val =   torch.log(torch.tensor(max_val, device=mse.device) / torch.sqrt(mse))
    return psnr_val.item()   直接返回数值，而非张量


def calc_ssim_torch(pred, target):
    from torch.nn.functional import convd
    window = torch.ones(, ).to(pred.device) / .
    window = window.unsqueeze().unsqueeze()
    mu_x = convd(pred, window, padding=, groups=)
    mu_y = convd(target, window, padding=, groups=)
    sigma_x = convd(pred, window, padding=, groups=) - mu_x
    sigma_y = convd(target, window, padding=, groups=) - mu_y
    sigma_xy = convd(pred  target, window, padding=, groups=) - mu_x  mu_y
    C = (.  .)  
    C = (.  .)  
    ssim_map = ((  mu_x  mu_y + C)  (  sigma_xy + C)) / ((mu_x + mu_y + C)  (sigma_x + sigma_y + C))
    return ssim_map.mean().item()   直接返回数值，而非张量

 . 图像归一化（保存预测样本用）


def normalize_image_array(arr):
    arr = arr - arr.min()
    arr = arr / (arr.max() + e-)
    arr = (arr  ).astype(np.uint)
    return arr

 ===================== 核心评估逻辑（删除多余的.item()调用） =====================


def evaluate_best_model():
    print("="  )
    print(f"开始评估模型: {config['model_path']}")
    print(f"使用设备: {config['device']}")
    print("="  )

     . 加载模型
    try:
         导入模型定义（和原训练代码一致）
        from model import LUMWCNN
        model = LUMWCNN().to(config["device"])

         加载权重（处理多卡训练的module.前缀）
        checkpoint = torch.load(config["model_path"], map_location=config["device"], weights_only=False)
        state_dict = checkpoint["model_state_dict"]
         移除module.前缀（多卡训练的模型）
        state_dict = {k.replace('module.', ''): v for k, v in state_dict.items()}
        model.load_state_dict(state_dict)
        model.eval()
        print(f" 模型加载成功（最佳epoch: {checkpoint.get('epoch', '未知')}）")
        print(f" 模型最佳验证指标：PSNR={checkpoint.get('val_psnr', ):.f} dB, SSIM={checkpoint.get('val_ssim', ):.f}")
    except Exception as e:
        print(f" 模型加载失败: {e}")
        return

     . 加载测试数据集
    try:
         动态导入数据集（和原训练代码一致）
        module_name, class_name = config["dataset"]["interface"].split(".")
        dataset_module = importlib.import_module(f"base.datasets.{module_name}")
        DatasetClass = getattr(dataset_module, class_name)

        test_set = DatasetClass(
            hr_dir=config["dataset"]["test_hr_dir"],
            crop_size=config["dataset"]["crop_size"],
            scale_factor=config["dataset"]["scale_factor"],
            noise_std=config["dataset"]["noise_std"],
            phase="test",
            augment=False,
        )
        test_loader = torch.utils.data.DataLoader(
            test_set,
            batch_size=,
            shuffle=False,
            pin_memory=config["device"].startswith("cuda"),
            num_workers=,   评估时禁用多线程，避免报错
        )
        print(f" 测试集加载成功（样本数: {len(test_set)}）")
    except Exception as e:
        print(f" 测试集加载失败: {e}")
        return

     . 初始化评估指标
    criterion = MixedLoss({k: v for k, v in config["loss"].items() if k in ["l_weight", "mse_weight"]})
    test_psnr = []
    test_ssim = []
    test_loss = []

     . 创建预测样本保存目录
    if config["save_pred_samples"]:
        os.makedirs(config["sample_save_dir"], exist_ok=True)

     . 执行评估
    print("\n开始测试集评估...")
    with torch.no_grad():
        for batch_idx, data in enumerate(tqdm(test_loader, desc="Evaluating")):
            try:
                lr, hr = data[:]
                lr = lr.to(config["device"])
                hr = hr.to(config["device"])

                 模型推理
                pred = model(lr)
                pred = torch.clamp(pred, ., .)

                 计算损失
                loss = criterion(pred, hr).item()
                test_loss.append(loss)

                 处理张量（适配指标计算）
                pred_np = pred.detach().cpu().squeeze()
                hr_np = hr.cpu().squeeze()
                pred_np = torch.clamp(pred_np, ., .)
                hr_np = torch.clamp(hr_np, ., .)

                 计算PSNR/SSIM（已在函数内返回数值，无需.item()）
                psnr = calc_psnr_torch(pred_np.float(), hr_np.float())
                ssim = calc_ssim_torch(pred_np.float(), hr_np.float())
                test_psnr.append(psnr)   直接添加数值，无.item()
                test_ssim.append(ssim)   直接添加数值，无.item()

                 保存前个预测样本（可视化）
                if config["save_pred_samples"] and batch_idx < :
                    pred_arr = normalize_image_array(pred_np[].numpy())
                    lr_arr = normalize_image_array(lr[].squeeze().cpu().numpy())
                    hr_arr = normalize_image_array(hr_np[].numpy())

                    Image.fromarray(pred_arr, mode="L").save(os.path.join(config["sample_save_dir"], f"batch_{batch_idx}_pred.png"))
                    Image.fromarray(lr_arr, mode="L").save(os.path.join(config["sample_save_dir"], f"batch_{batch_idx}_lr.png"))
                    Image.fromarray(hr_arr, mode="L").save(os.path.join(config["sample_save_dir"], f"batch_{batch_idx}_hr.png"))

            except Exception as e:
                print(f"\n️  批次{batch_idx}评估失败: {e}")
                continue

     . 输出评估结果
    print("\n" + "="  )
    print("模型性能评估结果（测试集）")
    print("="  )
    print(f"平均PSNR: {np.mean(test_psnr):.f} dB (标准差: {np.std(test_psnr):.f})")
    print(f"平均SSIM: {np.mean(test_ssim):.f} (标准差: {np.std(test_ssim):.f})")
    print(f"平均Loss: {np.mean(test_loss):.f} (标准差: {np.std(test_loss):.f})")
    print(f"最高PSNR: {np.max(test_psnr):.f} dB (批次: {np.argmax(test_psnr)})")
    print(f"最低PSNR: {np.min(test_psnr):.f} dB (批次: {np.argmin(test_psnr)})")

     性能解读
    print("\n" + "="  )
    print("性能解读")
    print("="  )
    avg_psnr = np.mean(test_psnr)
    if avg_psnr >= :
        print(" 模型性能优秀（PSNR≥dB，满足超分任务要求）")
    elif avg_psnr >= :
        print("️  模型性能中等（PSNR -dB，可进一步优化）")
    elif avg_psnr >= :
        print(" 模型性能较差（PSNR -dB，存在明显问题）")
    else:
        print(" 模型性能极差（PSNR<dB，大概率数据集/模型逻辑错误）")

    if config["save_pred_samples"]:
        print(f"\n 预测样本已保存至: {config['sample_save_dir']}")


if __name__ == "__main__":
    evaluate_best_model()
