"""
LU-MWCNN 尺寸匹配修复测试
修复数据尺寸不匹配和输出范围问题
"""

import os
import time
import torch
import torch.nn as nn
import numpy as np
from PIL import Image
import torch.optim as optim
from torch.utils.data import DataLoader
import matplotlib.pyplot as plt

 修复版数据集 - 确保尺寸匹配
class FixedSizeDataset(torch.utils.data.Dataset):
    def __init__(self, hr_dir, lr_dir, hr_size=, lr_size=, phase="train"):
        self.hr_dir = hr_dir
        self.lr_dir = lr_dir
        self.hr_size = hr_size
        self.lr_size = lr_size
        self.phase = phase
        
         获取文件列表
        self.hr_files = sorted([f for f in os.listdir(hr_dir) if f.endswith('.png')])[:]
        self.lr_files = sorted([f for f in os.listdir(lr_dir) if f.endswith('.png')])[:]
        
        print(f"修复数据集: {phase}模式")
        print(f"HR文件: {len(self.hr_files)}, 目标尺寸: {hr_size}x{hr_size}")
        print(f"LR文件: {len(self.lr_files)}, 输入尺寸: {lr_size}x{lr_size}")
        
         验证文件对应关系
        if self.hr_files != self.lr_files:
            print("️ 警告: HR和LR文件名不匹配!")
            print(f"HR示例: {self.hr_files[:]}")
            print(f"LR示例: {self.lr_files[:]}")
    
    def __len__(self):
        return min(len(self.hr_files), len(self.lr_files))
    
    def __getitem__(self, idx):
        try:
             加载HR图像并调整尺寸
            hr_path = os.path.join(self.hr_dir, self.hr_files[idx])
            hr_img = Image.open(hr_path).convert('L')
            hr_img = hr_img.resize((self.hr_size, self.hr_size), Image.Resampling.LANCZOS)
            hr_array = np.array(hr_img, dtype=np.float) / .
            
             加载LR图像并调整尺寸
            lr_path = os.path.join(self.lr_dir, self.lr_files[idx])
            lr_img = Image.open(lr_path).convert('L')
            lr_img = lr_img.resize((self.lr_size, self.lr_size), Image.Resampling.LANCZOS)
            lr_array = np.array(lr_img, dtype=np.float) / .
            
             转换为Tensor
            hr_tensor = torch.from_numpy(hr_array).unsqueeze()   [, H, W]
            lr_tensor = torch.from_numpy(lr_array).unsqueeze()   [, H, W]
            
            print(f"样本 {idx}: LR={lr_tensor.shape}, HR={hr_tensor.shape}")
            
            return lr_tensor, hr_tensor, self.hr_files[idx]
            
        except Exception as e:
            print(f"数据加载错误 {idx}: {e}")
             返回正确尺寸的随机数据
            lr_dummy = torch.rand(, self.lr_size, self.lr_size)
            hr_dummy = torch.rand(, self.hr_size, self.hr_size)
            return lr_dummy, hr_dummy, f"dummy_{idx}"

 修复版模型 - 添加输出限制
class FixedLUMWCNN(nn.Module):
    def __init__(self, output_size=, input_size=):
        super(FixedLUMWCNN, self).__init__()
        self.output_size = output_size
        self.input_size = input_size
        
         尝试导入原模型
        try:
            from model import LUMWCNN
            self.model = LUMWCNN()
            print("使用原版LUMWCNN模型 + 输出修复")
        except:
             简化模型作为fallback
            self.model = nn.Sequential(
                nn.Convd(, , , padding=),
                nn.ReLU(),
                nn.Convd(, , , padding=),
                nn.ReLU(),
                nn.Convd(, , , padding=)
            )
            print("使用简化模型")
        
         添加输出限制
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
         确保输入尺寸正确
        if x.shape[-:] != (self.input_size, self.input_size):
            print(f"️ 输入尺寸不匹配: {x.shape} -> 调整到 {self.input_size}")
            x = torch.nn.functional.interpolate(x, size=(self.input_size, self.input_size), mode='bilinear')
        
        output = self.model(x)
        
         确保输出尺寸正确
        if output.shape[-:] != (self.output_size, self.output_size):
            print(f"️ 输出尺寸不匹配: {output.shape} -> 调整到 {self.output_size}")
            output = torch.nn.functional.interpolate(output, size=(self.output_size, self.output_size), mode='bilinear')
        
         限制输出范围在[,]
        output = self.sigmoid(output)
        
        return output

 详细的PSNR诊断
def detailed_psnr_analysis(pred, target, sample_name=""):
    """详细的PSNR分析"""
    pred_np = pred.squeeze().cpu().numpy()
    target_np = target.squeeze().cpu().numpy()
    
    mse = np.mean((pred_np - target_np)  )
    psnr =   np.log(. / np.sqrt(mse)) if mse >  else float('inf')
    
    print(f"\n PSNR详细分析 {sample_name}:")
    print(f"   预测范围: [{pred_np.min():.f}, {pred_np.max():.f}]")
    print(f"   目标范围: [{target_np.min():.f}, {target_np.max():.f}]")
    print(f"   MSE: {mse:.f}")
    print(f"   PSNR: {psnr:.f} dB")
    
     检查常见问题
    if pred_np.max() > . or pred_np.min() < .:
        print("   ️ 预测值超出[,]范围!")
    if mse > .:
        print("   ️ MSE过高!")
    if psnr < :
        print("   ️ PSNR过低!")
    
    return psnr, mse

def fix_and_test():
    print("="  )
    print("开始尺寸匹配修复测试")
    print("="  )
    
     配置
    config = {
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "output_path": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/nova/lu_mwcnn/fix_test",
        "hr_size": ,   HR图像尺寸
        "lr_size": ,   LR图像尺寸 (/=)
    }
    
    os.makedirs(config["output_path"], exist_ok=True)
    
    print(f"使用设备: {config['device']}")
    print(f"HR尺寸: {config['hr_size']}x{config['hr_size']}")
    print(f"LR尺寸: {config['lr_size']}x{config['lr_size']}")
    
     修复数据加载
    print("\n 加载修复数据集...")
    try:
        train_set = FixedSizeDataset(
            hr_dir=r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/train/HR",
            lr_dir=r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/train/LR",
            hr_size=config["hr_size"],
            lr_size=config["lr_size"],
            phase="train"
        )
        
        val_set = FixedSizeDataset(
            hr_dir=r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/val/HR",
            lr_dir=r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/val/LR", 
            hr_size=config["hr_size"],
            lr_size=config["lr_size"],
            phase="val"
        )
        
        train_loader = DataLoader(train_set, batch_size=, shuffle=True)
        val_loader = DataLoader(val_set, batch_size=, shuffle=False)
        
        print(f" 数据集加载成功")
        print(f"   训练集: {len(train_set)} 样本")
        print(f"   验证集: {len(val_set)} 样本")
        
    except Exception as e:
        print(f" 数据集加载失败: {e}")
        return
    
     修复模型
    print("\n 初始化修复模型...")
    model = FixedLUMWCNN(
        output_size=config["hr_size"], 
        input_size=config["lr_size"]
    ).to(config["device"])
    
     测试单个样本
    print("\n 测试单个样本...")
    model.eval()
    with torch.no_grad():
         取第一个样本
        lr, hr, filename = val_set[]
        lr = lr.unsqueeze().to(config["device"])   添加batch维度
        hr = hr.unsqueeze().to(config["device"])
        
        print(f"输入尺寸: {lr.shape}")
        print(f"目标尺寸: {hr.shape}")
        
         模型推理
        pred = model(lr)
        print(f"输出尺寸: {pred.shape}")
        
         详细分析
        psnr, mse = detailed_psnr_analysis(pred, hr, filename)
        
         可视化结果
        visualize_comparison(lr, hr, pred, filename, config["output_path"])
    
     快速训练测试
    print("\n 快速训练测试...")
    model.train()
    optimizer = optim.Adam(model.parameters(), lr=e-)
    criterion = nn.MSELoss()
    
    for epoch in range():   只训练个epoch测试
        epoch_loss = 
        for batch_idx, (lr_batch, hr_batch, filenames) in enumerate(train_loader):
            lr_batch = lr_batch.to(config["device"])
            hr_batch = hr_batch.to(config["device"])
            
            pred_batch = model(lr_batch)
            loss = criterion(pred_batch, hr_batch)
            
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            epoch_loss += loss.item()
            
            if batch_idx %  == :
                print(f"  批次 {batch_idx}: 损失 {loss.item():.f}")
        
        print(f"Epoch {epoch+}: 平均损失 {epoch_loss/len(train_loader):.f}")
    
     最终验证
    print("\n 最终验证...")
    model.eval()
    total_psnr = 
    total_samples = 
    
    with torch.no_grad():
        for i, (lr, hr, filename) in enumerate(val_loader):
            if i >= :   只测试个样本
                break
                
            lr = lr.to(config["device"])
            hr = hr.to(config["device"])
            
            pred = model(lr)
            psnr, mse = detailed_psnr_analysis(pred, hr, f"val_{i}")
            
            total_psnr += psnr
            total_samples += 
    
    if total_samples > :
        avg_psnr = total_psnr / total_samples
        print(f"\n 平均PSNR: {avg_psnr:.f} dB")
        
        if avg_psnr > :
            print(" PSNR显著改善!")
        elif avg_psnr > :
            print("️ PSNR有所改善，但仍需优化")
        else:
            print(" PSNR仍然很低，需要进一步诊断")
    
    print("\n" + "="  )
    print("修复测试完成!")
    print("="  )

def visualize_comparison(lr, hr, pred, filename, output_path):
    """可视化对比结果"""
    lr_np = lr.squeeze().cpu().numpy()
    hr_np = hr.squeeze().cpu().numpy() 
    pred_np = pred.squeeze().cpu().numpy()
    
    fig, axes = plt.subplots(, , figsize=(, ))
    
     第一行：图像对比
    axes[, ].imshow(lr_np, cmap='gray')
    axes[, ].set_title(f'LR输入\n{lr_np.shape}')
    axes[, ].axis('off')
    
    axes[, ].imshow(hr_np, cmap='gray')
    axes[, ].set_title(f'HR目标\n{hr_np.shape}')
    axes[, ].axis('off')
    
    axes[, ].imshow(pred_np, cmap='gray')
    axes[, ].set_title(f'模型输出\n{pred_np.shape}')
    axes[, ].axis('off')
    
     第二行：分析
     直方图对比
    axes[, ].hist(hr_np.flatten(), bins=, alpha=., label='HR', color='blue')
    axes[, ].hist(pred_np.flatten(), bins=, alpha=., label='Pred', color='red')
    axes[, ].set_title('数值分布对比')
    axes[, ].legend()
    
     误差图
    error = np.abs(pred_np - hr_np)
    im = axes[, ].imshow(error, cmap='hot')
    axes[, ].set_title('绝对误差')
    axes[, ].axis('off')
    plt.colorbar(im, ax=axes[, ])
    
     像素值散点图
    axes[, ].scatter(hr_np.flatten()[::], pred_np.flatten()[::], alpha=., s=)
    axes[, ].plot([, ], [, ], 'r--', alpha=.)
    axes[, ].set_xlabel('HR像素值')
    axes[, ].set_ylabel('预测像素值')
    axes[, ].set_title('像素值相关性')
    axes[, ].set_xlim(, )
    axes[, ].set_ylim(, )
    axes[, ].set_aspect('equal')
    
    plt.tight_layout()
    save_path = os.path.join(output_path, f'fix_comparison_{filename}.png')
    plt.savefig(save_path, dpi=, bbox_inches='tight')
    plt.close()
    
    print(f" 对比图保存至: {save_path}")

if __name__ == "__main__":
    fix_and_test()