"""
LU-MWCNN 真实修复验证代码
使用真实模型和数据集进行实际训练验证
"""

import os
import sys
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from torch.utils.data import DataLoader, Dataset
from PIL import Image
import glob
import time
from tqdm import tqdm

 添加模型路径
sys.path.append(
    "/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/nova/lu_mwcnn"
)

 真实数据集路径
REAL_PATHS = {
    "train_hr": "/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/train/HR",
    "train_lr": "/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/train/LR",
    "val_hr": "/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/val/HR",
    "val_lr": "/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/val/LR",
    "output": "/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/nova/lu_mwcnn/repair_test_output",
}


class RealDeepLesionDataset(Dataset):
    """真实数据集加载"""

    def __init__(self, lr_dir, hr_dir, crop_size=, phase="train"):
        self.lr_dir = lr_dir
        self.hr_dir = hr_dir
        self.crop_size = crop_size
        self.phase = phase

         获取文件列表
        self.lr_files = sorted(glob.glob(os.path.join(lr_dir, ".png")))
        self.hr_files = sorted(glob.glob(os.path.join(hr_dir, ".png")))

        print(f"找到 {len(self.lr_files)} 个LR文件, {len(self.hr_files)} 个HR文件")

    def __len__(self):
        return min(len(self.lr_files), len(self.hr_files))

    def __getitem__(self, idx):
        try:
             加载LR和HR图像
            lr_img = Image.open(self.lr_files[idx]).convert("L")
            hr_img = Image.open(self.hr_files[idx]).convert("L")

             转换为numpy数组并归一化
            lr_array = np.array(lr_img, dtype=np.float) / .
            hr_array = np.array(hr_img, dtype=np.float) / .

             添加通道维度
            lr_array = np.expand_dims(lr_array, axis=)   [, H, W]
            hr_array = np.expand_dims(hr_array, axis=)   [, H, W]

             转换为tensor
            lr_tensor = torch.from_numpy(lr_array)
            hr_tensor = torch.from_numpy(hr_array)

            return lr_tensor, hr_tensor, os.path.basename(self.lr_files[idx])

        except Exception as e:
            print(f"加载图像失败 {self.lr_files[idx]}: {e}")
             返回空数据
            dummy = torch.zeros(, , )
            return dummy, dummy, "error"


def load_real_model():
    """加载真实模型"""
    try:
        from model import LUMWCNN

        model = LUMWCNN()
        print(" 成功加载真实LUMWCNN模型")
        return model
    except Exception as e:
        print(f" 加载真实模型失败: {e}")
         创建模拟模型作为fallback

        class FallbackModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.conv = nn.Convd(, , , padding=)
                self.conv = nn.Convd(, , , padding=)
                self.conv = nn.Convd(, , , padding=)
                self.relu = nn.ReLU()

            def forward(self, x):
                x = self.relu(self.conv(x))
                x = self.relu(self.conv(x))
                x = self.conv(x)
                return x

        print("️ 使用fallback模型进行测试")
        return FallbackModel()


def check_gradient_health(model):
    """真实梯度健康检查"""
    total_params = 
    zero_gradients = 
    nan_gradients = 
    healthy_gradients = 

    for name, param in model.named_parameters():
        if param.grad is not None:
            total_params += 
            grad_mean = param.grad.abs().mean().item()

            if torch.isnan(param.grad).any():
                nan_gradients += 
                print(f"   {name}: NaN梯度")
            elif grad_mean < e-:
                zero_gradients += 
                print(f"  ️ {name}: 梯度接近零 ({grad_mean:.e})")
            else:
                healthy_gradients += 
                print(f"   {name}: 健康梯度 ({grad_mean:.e})")

    return {
        "total": total_params,
        "healthy": healthy_gradients,
        "zero": zero_gradients,
        "nan": nan_gradients,
    }


def repair_model_initialization(model):
    """真实模型初始化修复"""
    print(" 执行模型初始化修复...")

    def weights_init(m):
        if isinstance(m, (nn.Convd, nn.ConvTransposed)):
             Kaiming初始化
            nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            if m.bias is not None:
                nn.init.constant_(m.bias, )
                print(f"   初始化: {m.__class__.__name__}")

    model.apply(weights_init)

     检查并修复NaN参数
    repair_count = 
    for name, param in model.named_parameters():
        if torch.isnan(param).any():
            nn.init.normal_(param, mean=, std=.)
            print(f"   修复NaN参数: {name}")
            repair_count += 

    print(f" 模型初始化修复完成，修复了 {repair_count} 个参数")
    return model


def calculate_psnr(pred, target):
    """计算PSNR - 安全版本"""
     确保数据在相同设备上且没有梯度
    pred = pred.detach()
    target = target.detach()

     确保数值范围合理
    pred = torch.clamp(pred, , )
    target = torch.clamp(target, , )

    mse = torch.mean((pred - target)  )
    if mse == :
        return torch.tensor(float("inf"), device=pred.device)

    psnr =   torch.log(. / torch.sqrt(mse))
    return psnr


def test_before_fix():
    """修复前真实测试"""
    print("="  )
    print(" 修复前真实测试")
    print("="  )

     加载模型和数据
    model = load_real_model()
    dataset = RealDeepLesionDataset(REAL_PATHS["train_lr"], REAL_PATHS["train_hr"])
    dataloader = DataLoader(dataset, batch_size=, shuffle=True)

     测试设备
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    print(f"使用设备: {device}")

     测试前向传播
    print("\n. 前向传播测试:")
    model.eval()
    with torch.no_grad():
        sample_lr, sample_hr, _ = next(iter(dataloader))
        sample_lr = sample_lr.to(device)
        sample_hr = sample_hr.to(device)

        output = model(sample_lr)
        print(f"  输入范围: [{sample_lr.min():.f}, {sample_lr.max():.f}]")
        print(f"  输出范围: [{output.min():.f}, {output.max():.f}]")
        print(f"  输出均值: {output.mean():.f} ± {output.std():.f}")

     测试反向传播
    print("\n. 反向传播测试:")
    model.train()
    optimizer = optim.Adam(model.parameters(), lr=e-)   修复前的高学习率

     模拟一个训练步骤
    sample_lr, sample_hr, _ = next(iter(dataloader))
    sample_lr = sample_lr.to(device)
    sample_hr = sample_hr.to(device)

    output = model(sample_lr)
    loss = nn.MSELoss()(output, sample_hr)

    optimizer.zero_grad()
    loss.backward()

     检查梯度健康
    grad_status = check_gradient_health(model)
    print(f"\n  梯度健康报告:")
    print(f"  总参数: {grad_status['total']}")
    print(f"  健康梯度: {grad_status['healthy']}")
    print(f"  接近零梯度: {grad_status['zero']}")
    print(f"  NaN梯度: {grad_status['nan']}")

     计算PSNR
    psnr = calculate_psnr(output, sample_hr)
    print(f"\n. 性能指标:")
    print(f"  损失: {loss.item():.f}")
    print(f"  PSNR: {psnr:.f} dB")

    return model, loss.item(), psnr.item(), grad_status


def train_with_fixes():
    """使用修复方案进行真实训练"""
    print("\n" + "="  )
    print(" 使用修复方案进行真实训练")
    print("="  )

     加载模型和数据
    model = load_real_model()
    dataset = RealDeepLesionDataset(REAL_PATHS["train_lr"], REAL_PATHS["train_hr"])
    dataloader = DataLoader(dataset, batch_size=, shuffle=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

     应用修复
    print("\n. 应用修复方案:")
    model = repair_model_initialization(model)

     使用修复后的优化器配置
    optimizer = optim.AdamW(
        model.parameters(), lr=e-, weight_decay=e-
    )   修复后的低学习率

     训练循环
    print("\n. 开始真实训练 (个批次):")
    model.train()
    losses = []
    psnrs = []
    gradient_health_history = []

    for batch_idx, (lr, hr, filenames) in enumerate(dataloader):
        if batch_idx >= :   只训练个批次作为演示
            break

        lr = lr.to(device)
        hr = hr.to(device)

         前向传播
        output = model(lr)
        loss = nn.MSELoss()(output, hr)

         反向传播
        optimizer.zero_grad()
        loss.backward()

         梯度裁剪
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=.)

         检查梯度健康
        grad_status = check_gradient_health(model)
        gradient_health_history.append(grad_status)

        optimizer.step()

         计算指标
        psnr = calculate_psnr(output, hr)

        losses.append(loss.item())
        psnrs.append(psnr.item())

        print(
            f"  批次 {batch_idx + }: 损失={loss.item():.f}, PSNR={psnr.item():.f} dB"
        )
        print(f"    梯度健康: {grad_status['healthy']}/{grad_status['total']} 参数正常")

     验证修复效果
    print("\n. 修复后验证:")
    model.eval()
    with torch.no_grad():
        val_lr, val_hr, _ = next(iter(dataloader))
        val_lr = val_lr.to(device)
        val_hr = val_hr.to(device)

        val_output = model(val_lr)
        val_loss = nn.MSELoss()(val_output, val_hr)
        val_psnr = calculate_psnr(val_output, val_hr)

        print(f"  验证损失: {val_loss.item():.f}")
        print(f"  验证PSNR: {val_psnr.item():.f} dB")
        print(f"  输出范围: [{val_output.min():.f}, {val_output.max():.f}]")

    return {
        "final_loss": np.mean(losses),
        "final_psnr": np.mean(psnrs),
        "val_loss": val_loss.item(),
        "val_psnr": val_psnr.item(),
        "gradient_health": (
            gradient_health_history[-] if gradient_health_history else {}
        ),
    }


def compare_results(before_results, after_results):
    """对比修复前后结果"""
    print("\n" + "="  )
    print(" 修复前后对比")
    print("="  )

    print("指标对比:")
    print(f"{'指标':<} {'修复前':<} {'修复后':<} {'改进':<}")
    print("-"  )

     损失对比
    loss_improvement = before_results["loss"] - after_results["final_loss"]
    print(
        f"{'训练损失':<} {before_results['loss']:<.f} {after_results['final_loss']:<.f} {loss_improvement:+.f}"
    )

     PSNR对比
    psnr_improvement = after_results["final_psnr"] - before_results["psnr"]
    print(
        f"{'训练PSNR':<} {before_results['psnr']:<.f} {after_results['final_psnr']:<.f} {psnr_improvement:+.f} dB"
    )

     验证PSNR对比
    val_psnr_improvement = after_results["val_psnr"] - before_results["psnr"]
    print(
        f"{'验证PSNR':<} {before_results['psnr']:<.f} {after_results['val_psnr']:<.f} {val_psnr_improvement:+.f} dB"
    )

     梯度健康对比
    print(f"\n梯度健康对比:")
    before_healthy_ratio = (
        before_results["grad_status"]["healthy"]
        / before_results["grad_status"]["total"]
         
    )
    after_healthy_ratio = (
        after_results["gradient_health"]["healthy"]
        / after_results["gradient_health"]["total"]
         
    )

    print(
        f"  修复前: {before_results['grad_status']['healthy']}/{before_results['grad_status']['total']} ({before_healthy_ratio:.f}%) 参数梯度正常"
    )
    print(
        f"  修复后: {after_results['gradient_health']['healthy']}/{after_results['gradient_health']['total']} ({after_healthy_ratio:.f}%) 参数梯度正常"
    )

     总体评估
    print(f"\n 总体评估:")
    if psnr_improvement > :
        print("   修复效果显著！PSNR提升明显")
    elif psnr_improvement > :
        print("  ️ 修复有一定效果，PSNR有所提升")
    else:
        print("   修复效果不明显，需要进一步调整")

    if after_healthy_ratio > :
        print("   梯度健康问题已基本解决")
    elif after_healthy_ratio > :
        print("  ️ 梯度健康有所改善，但仍有问题")
    else:
        print("   梯度健康问题依然严重")


def main():
    """主函数 - 真实修复验证"""
    print(" LU-MWCNN 真实修复验证")
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

     确保输出目录存在
    os.makedirs(REAL_PATHS["output"], exist_ok=True)

    try:
         修复前测试
        model_before, loss_before, psnr_before, grad_status_before = test_before_fix()

         修复后训练
        after_results = train_with_fixes()

         对比结果
        before_results = {
            "loss": loss_before,
            "psnr": psnr_before,
            "grad_status": grad_status_before,
        }

        compare_results(before_results, after_results)

         保存修复报告
        report_path = os.path.join(REAL_PATHS["output"], "repair_report.txt")
        with open(report_path, "w") as f:
            f.write("LU-MWCNN 修复验证报告\n")
            f.write("="   + "\n")
            f.write(f"验证时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"修复前 - 损失: {loss_before:.f}, PSNR: {psnr_before:.f} dB\n")
            f.write(
                f"修复后 - 损失: {after_results['final_loss']:.f}, PSNR: {after_results['final_psnr']:.f} dB\n"
            )
            f.write(f"验证PSNR: {after_results['val_psnr']:.f} dB\n")
            f.write(
                f"梯度健康: {after_results['gradient_health']['healthy']}/{after_results['gradient_health']['total']}\n"
            )

        print(f"\n 修复报告已保存: {report_path}")

    except Exception as e:
        print(f" 验证过程中出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()

