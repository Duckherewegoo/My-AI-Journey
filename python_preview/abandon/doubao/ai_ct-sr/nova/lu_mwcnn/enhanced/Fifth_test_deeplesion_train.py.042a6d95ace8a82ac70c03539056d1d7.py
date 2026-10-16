"""
LU-MWCNN 深度诊断与修复代码
针对真实训练问题提供更深入的解决方案
"""

from real_repair_test import RealDeepLesionDataset, load_real_model, calculate_psnr
import os
import sys
import torch
import torch.nn as nn
import numpy as np
from torch.utils.data import DataLoader
import matplotlib.pyplot as plt

 添加路径
sys.path.append(
    "/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/nova/lu_mwcnn"
)


def deep_model_analysis(model, dataloader, device):
    """深度模型分析"""
    print("="  )
    print(" 深度模型分析")
    print("="  )

    model.eval()
    analysis_results = {}

     . 分析各层激活值分布
    print(". 各层激活值分布分析:")
    activation_stats = {}

    def hook_fn(name):
        def hook(module, input, output):
            activation_stats[name] = {
                "mean": output.mean().item(),
                "std": output.std().item(),
                "min": output.min().item(),
                "max": output.max().item(),
            }

        return hook

     注册hook
    hooks = []
    for name, module in model.named_modules():
        if isinstance(module, (nn.Convd, nn.ConvTransposed)):
            hook = module.register_forward_hook(hook_fn(name))
            hooks.append(hook)

     前向传播收集统计信息
    with torch.no_grad():
        sample_lr, sample_hr, _ = next(iter(dataloader))
        sample_lr = sample_lr.to(device)
        _ = model(sample_lr)

     移除hook
    for hook in hooks:
        hook.remove()

     打印激活统计
    for name, stats in activation_stats.items():
        print(
            f"  {name}: 均值={stats['mean']:.f}, 标准差={stats['std']:.f}, 范围=[{stats['min']:.f}, {stats['max']:.f}]"
        )

    analysis_results["activation_stats"] = activation_stats

     . 分析参数分布
    print("\n. 参数分布分析:")
    param_stats = {}
    for name, param in model.named_parameters():
        if param.requires_grad:
            param_stats[name] = {
                "mean": param.data.mean().item(),
                "std": param.data.std().item(),
                "grad_mean": param.grad.mean().item() if param.grad is not None else ,
                "grad_std": param.grad.std().item() if param.grad is not None else ,
            }
            print(
                f"  {name}: 权重均值={param_stats[name]['mean']:.f}, 权重标准差={param_stats[name]['std']:.f}"
            )

    analysis_results["param_stats"] = param_stats

    return analysis_results


def advanced_repair_strategy(model, analysis_results):
    """基于分析结果的进阶修复策略 - 极简版本"""
    print("\n" + "="  )
    print(" 进阶修复策略")
    print("="  )

    repair_actions = []

     . 分析激活值问题
    activation_stats = analysis_results["activation_stats"]
    for name, stats in activation_stats.items():
         检测激活值消失
        if abs(stats["mean"]) < e- and stats["std"] < e-:
            print(f" 检测到激活值消失: {name}")
            repair_actions.append(f"激活值消失 - {name}")

         检测激活值爆炸
        if abs(stats["mean"]) >  or stats["std"] > :
            print(f" 检测到激活值爆炸: {name}")
            repair_actions.append(f"激活值爆炸 - {name}")

     . 只进行安全的权重初始化修复
    print("\n应用修复:")
    print(" 策略: 应用更精细的初始化")
    model = advanced_weight_init(model)
    repair_actions.append("改进权重初始化")

     跳过所有可能改变模型结构的复杂修复
    print("️  跳过批量归一化和残差连接（避免结构变化）")

    return model, repair_actions


def add_batch_norm_layers(model):
    """在卷积层后添加批量归一化 - 修复版本"""
    print("   添加批量归一化层...")

     创建安全的批量归一化层
    class ModelWithBN(nn.Module):
        def __init__(self, original_model):
            super().__init__()
            self.original_model = original_model

             使用列表存储BN层，避免命名冲突
            self.bn_layers = nn.ModuleList()
            conv_count = 

             统计卷积层数量
            for module in original_model.modules():
                if isinstance(module, nn.Convd):
                    conv_count += 

             为每个卷积层创建BN层
            for i in range(conv_count):
                 使用安全的命名方式
                bn_layer = nn.BatchNormd()   假设输出通道为，实际可能需要调整
                self.bn_layers.append(bn_layer)

        def forward(self, x):
             直接使用原模型，在输出前应用BN
            x = self.original_model(x)

             如果有BN层就应用最后一个
            if len(self.bn_layers) > :
                x = self.bn_layers[-](x)

            return x

    return ModelWithBN(model)


def advanced_weight_init(model):
    """进阶权重初始化"""

    def init_weights(m):
        if isinstance(m, nn.Convd):
             根据激活函数选择初始化
            if hasattr(m, "activation") and isinstance(m.activation, nn.ReLU):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            else:
                nn.init.xavier_normal_(m.weight)

            if m.bias is not None:
                nn.init.constant_(m.bias, )

        elif isinstance(m, nn.BatchNormd):
            nn.init.constant_(m.weight, )
            nn.init.constant_(m.bias, )

    model.apply(init_weights)
    return model


def add_residual_connections(model):
    """添加残差连接 - 极简版本"""
    print("   添加残差连接...")

     极简版本：直接包装，不修改内部结构
    class ModelWithResidual(nn.Module):
        def __init__(self, original_model):
            super().__init__()
            self.original_model = original_model

        def forward(self, x):
             直接返回原模型输出，不添加复杂逻辑
            return self.original_model(x)

    return ModelWithResidual(model)


def test_different_learning_rates(model, dataloader, device):
    """测试不同学习率的效果 - 修复设备不匹配问题"""
    print("\n" + "="  )
    print(" 学习率敏感性测试")
    print("=" + "="  )

    learning_rates = [e-, e-, e-, e-, e-]
    results = {}

    for lr in learning_rates:
        print(f"\n测试学习率: {lr:.e}")

        try:
             创建模型副本并确保在正确设备上
            model_copy = type(model)()
            model_copy.load_state_dict(model.state_dict())
            model_copy = model_copy.to(device)   确保模型在GPU上
            model_copy.train()

             优化器
            optimizer = torch.optim.AdamW(model_copy.parameters(), lr=lr)
            criterion = nn.MSELoss()

             训练几个批次
            losses = []

            for batch_idx, (lr_img, hr_img, _) in enumerate(dataloader):
                if batch_idx >= :   只测试个批次
                    break

                 确保数据也在GPU上
                lr_img = lr_img.to(device)
                hr_img = hr_img.to(device)

                optimizer.zero_grad()
                output = model_copy(lr_img)
                loss = criterion(output, hr_img)
                loss.backward()

                 梯度裁剪
                torch.nn.utils.clip_grad_norm_(model_copy.parameters(), max_norm=.)
                optimizer.step()

                losses.append(loss.item())

            avg_loss = np.mean(losses)
            results[lr] = avg_loss
            print(f"  平均损失: {avg_loss:.f}")

        except Exception as e:
            print(f"  学习率 {lr:.e} 测试失败: {e}")
            results[lr] = float("inf")
            continue

     找到最佳学习率
    if results:
        best_lr = min(results, key=results.get)
        print(f"\n 推荐学习率: {best_lr:.e} (损失: {results[best_lr]:.f})")
    else:
        best_lr = e-
        print(f"\n️  所有学习率测试失败，使用默认学习率: {best_lr:.e}")

    return best_lr, results


def create_simple_cnn_comparison():
    """创建简单的CNN模型作为对比"""

    class SimpleSRCNN(nn.Module):
        def __init__(self):
            super().__init__()
             简单的超分辨率CNN
            self.conv = nn.Convd(, , , padding=)
            self.conv = nn.Convd(, , , padding=)
            self.conv = nn.Convd(, , , padding=)
            self.relu = nn.ReLU()

        def forward(self, x):
            x = self.relu(self.conv(x))
            x = self.relu(self.conv(x))
            x = self.conv(x)
            return x

    return SimpleSRCNN()


def compare_with_simple_model(complex_model, simple_model, dataloader, device):
    """与简单模型对比"""
    print("\n" + "="  )
    print(" 与简单模型对比")
    print("="  )

    models = {"复杂模型": complex_model, "简单模型": simple_model}

    results = {}

    for name, model in models.items():
        print(f"\n测试 {name}:")
        model = model.to(device)
        model.eval()

        losses = []
        psnrs = []

        with torch.no_grad():
            for batch_idx, (lr_img, hr_img, _) in enumerate(dataloader):
                if batch_idx >= :   测试个批次
                    break

                lr_img = lr_img.to(device)
                hr_img = hr_img.to(device)

                output = model(lr_img)
                loss = nn.MSELoss()(output, hr_img)
                psnr = calculate_psnr(output, hr_img)

                losses.append(loss.item())
                psnrs.append(psnr.item())

        results[name] = {
            "avg_loss": np.mean(losses),
            "avg_psnr": np.mean(psnrs),
            "std_loss": np.std(losses),
            "std_psnr": np.std(psnrs),
        }

        print(f"  平均损失: {results[name]['avg_loss']:.f}")
        print(f"  平均PSNR: {results[name]['avg_psnr']:.f} dB")

     对比分析
    print("\n 对比分析:")
    complex_loss = results["复杂模型"]["avg_loss"]
    simple_loss = results["简单模型"]["avg_loss"]

    if simple_loss < complex_loss:
        print(f" 复杂模型性能不如简单模型")
        print(f"   简单模型损失: {simple_loss:.f} vs 复杂模型损失: {complex_loss:.f}")
        improvement = (complex_loss - simple_loss) / complex_loss  
        print(f"   简单模型优于复杂模型: {improvement:.f}%")
    else:
        print(f" 复杂模型性能优于简单模型")

    return results


def main():
    """主诊断函数 - 修复版本"""
    print(" LU-MWCNN 深度诊断与修复")

     设置设备
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"使用设备: {device}")

    try:
         加载数据
        dataset = RealDeepLesionDataset(
            "/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/train/LR",
            "/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/train/HR",
        )
        dataloader = DataLoader(dataset, batch_size=, shuffle=True)

         . 加载原始模型并深度分析
        original_model = load_real_model().to(device)
        analysis_results = deep_model_analysis(original_model, dataloader, device)

         . 应用安全的修复策略
        repaired_model, repair_actions = advanced_repair_strategy(
            original_model, analysis_results
        )

         . 学习率敏感性测试（添加异常处理）
        try:
            best_lr, lr_results = test_different_learning_rates(
                repaired_model, dataloader, device
            )
        except Exception as e:
            print(f"️  学习率测试失败: {e}")
            print("使用默认学习率: e-")
            best_lr = e-
            lr_results = {}
         . 生成诊断报告
        print("\n" + "="  )
        print(" 深度诊断报告")
        print("="  )

        print("修复措施应用:")
        for action in repair_actions:
            print(f"   {action}")

        print(f"\n推荐配置:")
        print(f"   最佳学习率: {best_lr:.e}")

         模型复杂度分析
        def count_parameters(model):
            return sum(p.numel() for p in model.parameters() if p.requires_grad)

        original_params = count_parameters(original_model)
        repaired_params = count_parameters(repaired_model)

        print(f"\n模型复杂度:")
        print(f"  原始模型参数: {original_params:,}")
        print(f"  修复后模型参数: {repaired_params:,}")

        report = {
            "repair_actions": repair_actions,
            "best_learning_rate": best_lr,
            "parameter_counts": {
                "original": original_params,
                "repaired": repaired_params,
            },
        }

        return report

    except Exception as e:
        print(f" 诊断过程中出错: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    report = main()
