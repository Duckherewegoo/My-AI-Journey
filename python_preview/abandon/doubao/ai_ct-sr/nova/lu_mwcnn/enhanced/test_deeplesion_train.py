"""
LU-MWCNN 小型测试版本 + 详细诊断功能
目的：找出PSNR/SSIM极低的原因
"""

import os
import time
import glob
from tqdm import tqdm
from datetime import datetime
import torch
import torch.nn as nn
import numpy as np
from PIL import Image
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.utils.data import DataLoader
import matplotlib.pyplot as plt

 简化版 AverageMeter
class AverageMeter:
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.val = 
        self.avg = 
        self.sum = 
        self.count = 
    
    def update(self, val, n=):
        self.val = val
        self.sum += val  n
        self.count += n
        self.avg = self.sum / self.count

 诊断工具类
class ModelDiagnoser:
    def __init__(self, output_path):
        self.output_path = output_path
        os.makedirs(output_path, exist_ok=True)
        self.diagnosis_log = []
        
    def log(self, message):
        """记录诊断信息"""
        print(f"[诊断] {message}")
        self.diagnosis_log.append(f"{datetime.now().strftime('%H:%M:%S')} - {message}")
    
    def analyze_data_distribution(self, dataset, name="dataset"):
        """分析数据分布"""
        self.log(f"开始分析 {name} 数据分布...")
        
        hr_values = []
        lr_values = []
        
        for i in range(min(, len(dataset))):   分析前个样本
            try:
                lr, hr, filename = dataset[i]
                hr_values.extend(hr.flatten().numpy())
                lr_values.extend(lr.flatten().numpy())
            except Exception as e:
                self.log(f"样本 {i} 分析失败: {e}")
        
        if hr_values and lr_values:
            hr_values = np.array(hr_values)
            lr_values = np.array(lr_values)
            
            self.log(f"HR数据 - 最小值: {hr_values.min():.f}, 最大值: {hr_values.max():.f}, 均值: {hr_values.mean():.f}")
            self.log(f"LR数据 - 最小值: {lr_values.min():.f}, 最大值: {lr_values.max():.f}, 均值: {lr_values.mean():.f}")
            
             绘制分布图
            plt.figure(figsize=(, ))
            
            plt.subplot(, , )
            plt.hist(hr_values, bins=, alpha=., color='blue')
            plt.title(f'{name} HR值分布')
            plt.xlabel('像素值')
            plt.ylabel('频次')
            
            plt.subplot(, , )
            plt.hist(lr_values, bins=, alpha=., color='red')
            plt.title(f'{name} LR值分布')
            plt.xlabel('像素值')
            plt.ylabel('频次')
            
            plt.tight_layout()
            plt.savefig(os.path.join(self.output_path, f'{name}_distribution.png'))
            plt.close()
            
            return True
        else:
            self.log(f"无法分析 {name} 数据分布")
            return False
    
    def analyze_model_output(self, model, dataloader, device, num_batches=):
        """分析模型输出"""
        self.log("分析模型输出分布...")
        
        model.eval()
        outputs = []
        targets = []
        
        with torch.no_grad():
            for batch_idx, (lr, hr, filenames) in enumerate(dataloader):
                if batch_idx >= num_batches:
                    break
                    
                lr = lr.to(device)
                hr = hr.to(device)
                
                output = model(lr)
                outputs.extend(output.cpu().flatten().numpy())
                targets.extend(hr.cpu().flatten().numpy())
        
        if outputs:
            outputs = np.array(outputs)
            targets = np.array(targets)
            
            self.log(f"模型输出 - 最小值: {outputs.min():.f}, 最大值: {outputs.max():.f}, 均值: {outputs.mean():.f}")
            self.log(f"目标输出 - 最小值: {targets.min():.f}, 最大值: {targets.max():.f}, 均值: {targets.mean():.f}")
            
             检查输出范围
            if outputs.min() < -. or outputs.max() > .:
                self.log("️ 警告: 模型输出超出预期范围 [,]")
            if targets.min() < -. or targets.max() > .:
                self.log("️ 警告: 目标数据超出预期范围 [,]")
            
             绘制对比图
            plt.figure(figsize=(, ))
            plt.hist(outputs, bins=, alpha=., label='模型输出', color='green')
            plt.hist(targets, bins=, alpha=., label='目标数据', color='blue')
            plt.title('模型输出 vs 目标数据分布')
            plt.xlabel('像素值')
            plt.ylabel('频次')
            plt.legend()
            plt.savefig(os.path.join(self.output_path, 'model_output_distribution.png'))
            plt.close()
            
            return True
        else:
            self.log("无法分析模型输出")
            return False
    
    def visualize_sample_pairs(self, dataset, num_samples=, name="sample"):
        """可视化样本对"""
        self.log(f"可视化 {num_samples} 个样本对...")
        
        fig, axes = plt.subplots(num_samples, , figsize=(, num_samples))
        if num_samples == :
            axes = axes.reshape(, -)
        
        for i in range(num_samples):
            try:
                lr, hr, filename = dataset[i]
                
                 转换为numpy
                lr_np = lr.squeeze().numpy()
                hr_np = hr.squeeze().numpy()
                
                 显示LR
                axes[i, ].imshow(lr_np, cmap='gray')
                axes[i, ].set_title(f'LR: {filename}\nRange: [{lr_np.min():.f}, {lr_np.max():.f}]')
                axes[i, ].axis('off')
                
                 显示HR
                axes[i, ].imshow(hr_np, cmap='gray')
                axes[i, ].set_title(f'HR: {filename}\nRange: [{hr_np.min():.f}, {hr_np.max():.f}]')
                axes[i, ].axis('off')
                
                 显示差值
                diff = hr_np - lr_np
                im = axes[i, ].imshow(diff, cmap='coolwarm')
                axes[i, ].set_title(f'HR-LR差值\nRange: [{diff.min():.f}, {diff.max():.f}]')
                axes[i, ].axis('off')
                plt.colorbar(im, ax=axes[i, ])
                
            except Exception as e:
                self.log(f"样本 {i} 可视化失败: {e}")
                for j in range():
                    axes[i, j].text(., ., f"Error: {e}", 
                                   horizontalalignment='center', 
                                   verticalalignment='center',
                                   transform=axes[i, j].transAxes)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_path, f'{name}_visualization.png'), dpi=, bbox_inches='tight')
        plt.close()
    
    def check_data_consistency(self, train_set, val_set):
        """检查数据一致性"""
        self.log("检查训练集和验证集数据一致性...")
        
         检查文件重叠
        train_files = set([os.path.basename(f) for f in train_set.hr_files])
        val_files = set([os.path.basename(f) for f in val_set.hr_files])
        
        overlap = train_files.intersection(val_files)
        if overlap:
            self.log(f"️ 警告: 训练集和验证集有 {len(overlap)} 个重叠文件")
            self.log(f"重叠文件示例: {list(overlap)[:]}")
        else:
            self.log("✓ 训练集和验证集无文件重叠")
        
         检查数据范围一致性
        train_sample = train_set[]
        val_sample = val_set[]
        
        self.log(f"训练样本范围 - LR: [{train_sample[].min():.f}, {train_sample[].max():.f}], "
                f"HR: [{train_sample[].min():.f}, {train_sample[].max():.f}]")
        self.log(f"验证样本范围 - LR: [{val_sample[].min():.f}, {val_sample[].max():.f}], "
                f"HR: [{val_sample[].min():.f}, {val_sample[].max():.f}]")
    
    def save_diagnosis_report(self):
        """保存诊断报告"""
        report_path = os.path.join(self.output_path, 'diagnosis_report.txt')
        with open(report_path, 'w', encoding='utf-') as f:
            f.write("模型诊断报告\n")
            f.write("="   + "\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for log_entry in self.diagnosis_log:
                f.write(log_entry + "\n")
        
        self.log(f"诊断报告已保存: {report_path}")

 简化配置 - 针对测试优化
test_config = {
    "lr": e-,
    "epochs": ,
    "batch_size": ,
    "val_every": ,
    "num_workers": ,
    "device": "cuda" if torch.cuda.is_available() else "cpu",
    
    "dataset": {
        "train_hr_dir": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/train/HR",
        "train_lr_dir": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/train/LR", 
        "val_hr_dir": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/val/HR",
        "val_lr_dir": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/val/LR",
        "crop_size": ,
        "scale_factor": ,
    },
    
    "output_path": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/nova/lu_mwcnn/detailed_diagnosis",
}

 创建简单的测试数据集类
class TestDataset(torch.utils.data.Dataset):
    def __init__(self, hr_dir, lr_dir, crop_size=, scale_factor=, phase="train"):
        self.hr_dir = hr_dir
        self.lr_dir = lr_dir
        self.crop_size = crop_size
        self.scale_factor = scale_factor
        self.phase = phase
        
         获取文件列表
        self.hr_files = sorted([f for f in os.listdir(hr_dir) if f.endswith('.png')])[:]
        self.lr_files = sorted([f for f in os.listdir(lr_dir) if f.endswith('.png')])[:]
        
        print(f"测试数据集: {phase}模式, HR文件: {len(self.hr_files)}, LR文件: {len(self.lr_files)}")
        
         检查文件对应关系
        if len(self.hr_files) != len(self.lr_files):
            print(f"️ 警告: HR和LR文件数量不匹配! HR: {len(self.hr_files)}, LR: {len(self.lr_files)}")
    
    def __len__(self):
        return min(len(self.hr_files), len(self.lr_files))
    
    def __getitem__(self, idx):
        try:
             加载HR图像
            hr_path = os.path.join(self.hr_dir, self.hr_files[idx])
            hr_img = Image.open(hr_path).convert('L')
            hr_array = np.array(hr_img, dtype=np.float) / .
            
             加载对应的LR图像
            lr_path = os.path.join(self.lr_dir, self.lr_files[idx])
            lr_img = Image.open(lr_path).convert('L') 
            lr_array = np.array(lr_img, dtype=np.float) / .
            
             转换为Tensor
            hr_tensor = torch.from_numpy(hr_array).unsqueeze()
            lr_tensor = torch.from_numpy(lr_array).unsqueeze()
            
            return lr_tensor, hr_tensor, self.hr_files[idx]
            
        except Exception as e:
            print(f"数据加载错误 {idx}: {e}")
             返回随机数据作为fallback
            dummy_data = torch.rand(, self.crop_size, self.crop_size)
            return dummy_data, dummy_data, f"dummy_{idx}"

 简化模型
class SimpleTestModel(nn.Module):
    def __init__(self):
        super(SimpleTestModel, self).__init__()
        self.net = nn.Sequential(
            nn.Convd(, , , padding=),
            nn.ReLU(),
            nn.Convd(, , , padding=),
            nn.ReLU(),
            nn.Convd(, , , padding=)
        )
    
    def forward(self, x):
        return self.net(x)

 简化的PSNR计算
def simple_psnr(pred, target):
    mse = torch.mean((pred - target)  )
    if mse == :
        return float('inf')
    return   torch.log(. / torch.sqrt(mse))

def detailed_test_main():
    print("="  )
    print("开始详细诊断测试")
    print("="  )
    
     初始化诊断器
    diagnoser = ModelDiagnoser(test_config["output_path"])
    
     检查设备
    device = test_config["device"]
    diagnoser.log(f"使用设备: {device}")
    if device.startswith("cuda"):
        diagnoser.log(f"GPU: {torch.cuda.get_device_name(device)}")
    
     加载测试数据集
    diagnoser.log("加载测试数据集...")
    try:
        train_set = TestDataset(
            hr_dir=test_config["dataset"]["train_hr_dir"],
            lr_dir=test_config["dataset"]["train_lr_dir"],
            crop_size=test_config["dataset"]["crop_size"],
            scale_factor=test_config["dataset"]["scale_factor"],
            phase="train"
        )
        
        val_set = TestDataset(
            hr_dir=test_config["dataset"]["val_hr_dir"], 
            lr_dir=test_config["dataset"]["val_lr_dir"],
            crop_size=test_config["dataset"]["crop_size"],
            scale_factor=test_config["dataset"]["scale_factor"],
            phase="val"
        )
        
         执行数据诊断
        diagnoser.analyze_data_distribution(train_set, "train_set")
        diagnoser.analyze_data_distribution(val_set, "val_set")
        diagnoser.visualize_sample_pairs(train_set, , "train_samples")
        diagnoser.visualize_sample_pairs(val_set, , "val_samples")
        diagnoser.check_data_consistency(train_set, val_set)
        
        train_loader = DataLoader(
            train_set,
            batch_size=test_config["batch_size"],
            shuffle=True,
            num_workers=test_config["num_workers"]
        )
        
        val_loader = DataLoader(
            val_set,
            batch_size=,
            shuffle=False,
            num_workers=test_config["num_workers"]
        )
        
        diagnoser.log(f"训练集: {len(train_set)} 样本")
        diagnoser.log(f"验证集: {len(val_set)} 样本")
        
    except Exception as e:
        diagnoser.log(f"数据集加载失败: {e}")
        diagnoser.save_diagnosis_report()
        return
    
     初始化模型
    try:
        from model import LUMWCNN
        model = LUMWCNN().to(device)
        diagnoser.log("使用原版 LUMWCNN 模型")
        
         分析模型结构
        total_params = sum(p.numel() for p in model.parameters())
        diagnoser.log(f"模型参数总数: {total_params:,}")
        
    except Exception as e:
        model = SimpleTestModel().to(device)
        diagnoser.log(f"使用简化测试模型 (原因: {e})")
    
     分析初始模型输出
    diagnoser.analyze_model_output(model, val_loader, device)
    
     损失函数和优化器
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=test_config["lr"])
    
     开始微型训练
    diagnoser.log("开始微型训练...")
    train_losses = []
    val_psnrs = []
    
    for epoch in range(test_config["epochs"]):
        epoch_start = time.time()
        
         训练阶段
        model.train()
        train_loss = AverageMeter()
        
        diagnoser.log(f"Epoch {epoch+}/{test_config['epochs']}")
        for batch_idx, (lr, hr, filenames) in enumerate(train_loader):
            lr = lr.to(device)
            hr = hr.to(device)
            
             前向传播
            pred = model(lr)
            loss = criterion(pred, hr)
            
             反向传播
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            train_loss.update(loss.item(), lr.size())
            
            if batch_idx %  == :
                diagnoser.log(f"  批次 {batch_idx}: 损失 {loss.item():.f}")
        
        train_losses.append(train_loss.avg)
        
         验证阶段
        model.eval()
        val_psnr = AverageMeter()
        val_loss = AverageMeter()
        
        diagnoser.log("验证...")
        with torch.no_grad():
            for lr, hr, filename in val_loader:
                lr = lr.to(device)
                hr = hr.to(device)
                
                pred = model(lr)
                psnr = simple_psnr(pred, hr)
                loss = criterion(pred, hr)
                
                val_psnr.update(psnr.item())
                val_loss.update(loss.item())
        
        val_psnrs.append(val_psnr.avg)
        
        epoch_time = time.time() - epoch_start
        diagnoser.log(f"Epoch {epoch+} 完成 | "
              f"训练损失: {train_loss.avg:.f} | "
              f"验证PSNR: {val_psnr.avg:.f} dB | "
              f"验证损失: {val_loss.avg:.f} | "
              f"耗时: {epoch_time:.f}s")
        
         分析训练后的模型输出
        if epoch == test_config["epochs"] - :
            diagnoser.analyze_model_output(model, val_loader, device)
    
     绘制训练曲线
    plt.figure(figsize=(, ))
    
    plt.subplot(, , )
    plt.plot(train_losses, 'b-', label='训练损失')
    plt.title('训练损失曲线')
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.legend()
    
    plt.subplot(, , )
    plt.plot(val_psnrs, 'r-', label='验证PSNR')
    plt.title('验证PSNR曲线')
    plt.xlabel('Epoch')
    plt.ylabel('PSNR (dB)')
    plt.legend()
    
    plt.tight_layout()
    plt.savefig(os.path.join(test_config["output_path"], 'training_curves.png'))
    plt.close()
    
     保存示例推理结果
    diagnoser.log("保存示例推理结果...")
    model.eval()
    with torch.no_grad():
         取前个验证样本
        for i, (lr, hr, filename) in enumerate(val_loader):
            if i >= :
                break
                
            lr = lr.to(device)
            hr = hr.to(device)
            pred = model(lr).cpu().squeeze()
            
             转换为numpy
            lr_np = lr.cpu().squeeze().numpy()
            hr_np = hr.cpu().squeeze().numpy()
            pred_np = pred.numpy()
            
             计算指标
            mse = np.mean((pred_np - hr_np)  )
            psnr =   np.log(. / np.sqrt(mse)) if mse >  else float('inf')
            
             可视化对比
            fig, axes = plt.subplots(, , figsize=(, ))
            
            axes[].imshow(lr_np, cmap='gray')
            axes[].set_title(f'LR输入\n范围: [{lr_np.min():.f}, {lr_np.max():.f}]')
            axes[].axis('off')
            
            axes[].imshow(hr_np, cmap='gray')
            axes[].set_title(f'HR目标\n范围: [{hr_np.min():.f}, {hr_np.max():.f}]')
            axes[].axis('off')
            
            axes[].imshow(pred_np, cmap='gray')
            axes[].set_title(f'模型输出\n范围: [{pred_np.min():.f}, {pred_np.max():.f}]')
            axes[].axis('off')
            
            diff = np.abs(pred_np - hr_np)
            im = axes[].imshow(diff, cmap='hot')
            axes[].set_title(f'绝对误差\nPSNR: {psnr:.f} dB\nMSE: {mse:.f}')
            axes[].axis('off')
            plt.colorbar(im, ax=axes[])
            
            plt.tight_layout()
            plt.savefig(os.path.join(test_config["output_path"], f'result_comparison_{i}.png'), dpi=, bbox_inches='tight')
            plt.close()
            
            diagnoser.log(f"样本 {filename[]} - PSNR: {psnr:.f} dB, MSE: {mse:.f}")
    
     最终诊断总结
    diagnoser.log("\n" + "="  )
    diagnoser.log("诊断总结:")
    
    if val_psnrs and val_psnrs[-] < :
        diagnoser.log(" 问题确认: PSNR确实极低 (<  dB)")
        diagnoser.log("可能原因:")
        diagnoser.log(". 数据不匹配: LR和HR图像不对应")
        diagnoser.log(". 数据范围异常: 图像值不在[,]范围内")
        diagnoser.log(". 模型结构问题: 网络无法学习有效映射")
        diagnoser.log(". 训练配置问题: 学习率、损失函数等")
    else:
        diagnoser.log(" PSNR在合理范围内")
    
    diagnoser.log("="  )
    
    print("\n" + "="  )
    print("详细诊断完成!")
    print("="  )
    
     保存模型和诊断报告
    model_path = os.path.join(test_config["output_path"], "test_model.pth")
    torch.save(model.state_dict(), model_path)
    diagnoser.log(f"测试模型保存至: {model_path}")
    
    diagnoser.save_diagnosis_report()
    
     显存清理
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        diagnoser.log(f"GPU显存使用: {torch.cuda.memory_allocated()/:.f} MB")

if __name__ == "__main__":
    detailed_test_main()