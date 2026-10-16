"""
LU-MWCNN 深度诊断与修复 - 解决模型不学习问题
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
from torch.utils.tensorboard import SummaryWriter

class DeepDiagnosis:
    def __init__(self, output_path):
        self.output_path = output_path
        os.makedirs(output_path, exist_ok=True)
        self.diagnosis_log = []
        
    def log(self, message):
        print(f"[诊断] {message}")
        self.diagnosis_log.append(message)
    
    def check_model_initialization(self, model):
        """检查模型初始化状态"""
        self.log(" 检查模型初始化...")
        
        total_params = 
        trainable_params = 
        
        for name, param in model.named_parameters():
            total_params += param.numel()
            if param.requires_grad:
                trainable_params += param.numel()
            
             检查参数范围
            param_mean = param.data.mean().item()
            param_std = param.data.std().item()
            
            self.log(f"  参数 {name}: 均值={param_mean:.f}, 标准差={param_std:.f}")
            
             检查梯度需求
            if not param.requires_grad:
                self.log(f"  ️ 参数 {name} 不需要梯度!")
        
        self.log(f"总参数: {total_params:,}, 可训练参数: {trainable_params:,}")
        
        return total_params, trainable_params
    
    def check_gradient_flow(self, model, loss, optimizer):
        """检查梯度流动"""
        self.log(" 检查梯度流动...")
        
         反向传播
        optimizer.zero_grad()
        loss.backward()
        
        gradient_info = []
        has_valid_gradients = False
        
        for name, param in model.named_parameters():
            if param.grad is not None:
                grad_mean = param.grad.mean().item()
                grad_std = param.grad.std().item()
                gradient_info.append((name, grad_mean, grad_std))
                
                if abs(grad_mean) > e-:   有有效梯度
                    has_valid_gradients = True
                    self.log(f"   {name}: 梯度均值={grad_mean:.f}, 标准差={grad_std:.f}")
                else:
                    self.log(f"  ️ {name}: 梯度接近零 ({grad_mean:.e})")
            else:
                self.log(f"   {name}: 无梯度!")
        
        return has_valid_gradients, gradient_info
    
    def analyze_data_flow(self, model, sample_data, device):
        """分析数据流通过模型"""
        self.log(" 分析数据流...")
        
        model.eval()
        with torch.no_grad():
             逐层分析（如果是Sequential或已知结构）
            if hasattr(model, 'model') and hasattr(model.model, 'features'):
                 假设是原版LUMWCNN
                x = sample_data.clone()
                layer_outputs = []
                
                for i, layer in enumerate(model.model.features):
                    x = layer(x)
                    if i %  == :   每层记录一次
                        layer_outputs.append((f"layer_{i}", x.mean().item(), x.std().item()))
                
                for name, mean_val, std_val in layer_outputs:
                    self.log(f"  {name}: 输出均值={mean_val:.f}, 标准差={std_val:.f}")
            
             整体分析
            output = model(sample_data)
            self.log(f"  模型最终输出: 均值={output.mean().item():.f}, 标准差={output.std().item():.f}")
            
            return output

def create_simple_sr_model(input_size=, output_size=):
    """创建一个简单的超分辨率模型作为对比"""
    return nn.Sequential(
         上采样部分
        nn.Convd(, , , padding=),
        nn.ReLU(inplace=True),
        nn.Convd(, , , padding=),
        nn.ReLU(inplace=True),
        nn.Convd(, , , padding=),
        nn.ReLU(inplace=True),
        
         上采样
        nn.Convd(, , , padding=),
        nn.PixelShuffle(),   倍上采样 ->
        nn.ReLU(inplace=True),
        
        nn.Convd(, , , padding=),
        nn.PixelShuffle(),   倍上采样 ->
        nn.ReLU(inplace=True),
        
         最终卷积
        nn.Convd(, , , padding=),
        nn.ReLU(inplace=True),
        nn.Convd(, , , padding=),
        nn.Sigmoid()   确保输出在[,]
    )

def deep_diagnosis_test():
    print("="  )
    print("深度诊断测试 - 解决模型不学习问题")
    print("="  )
    
     配置
    config = {
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "output_path": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/nova/lu_mwcnn/deep_diagnosis",
        "hr_size": ,
        "lr_size": ,
        "batch_size": ,
        "learning_rate": e-,   更小的学习率
    }
    
    diagnoser = DeepDiagnosis(config["output_path"])
    diagnoser.log(f"使用设备: {config['device']}")
    
     修复数据集
    class FixedDataset(torch.utils.data.Dataset):
        def __init__(self, hr_dir, lr_dir, hr_size=, lr_size=):
            self.hr_dir = hr_dir
            self.lr_dir = lr_dir
            self.hr_files = sorted([f for f in os.listdir(hr_dir) if f.endswith('.png')])[:]
            self.lr_files = sorted([f for f in os.listdir(lr_dir) if f.endswith('.png')])[:]
            
        def __len__(self):
            return min(len(self.hr_files), len(self.lr_files))
        
        def __getitem__(self, idx):
            hr_path = os.path.join(self.hr_dir, self.hr_files[idx])
            lr_path = os.path.join(self.lr_dir, self.lr_files[idx])
            
            hr_img = Image.open(hr_path).convert('L').resize((config["hr_size"], config["hr_size"]), Image.Resampling.LANCZOS)
            lr_img = Image.open(lr_path).convert('L').resize((config["lr_size"], config["lr_size"]), Image.Resampling.LANCZOS)
            
            hr_array = np.array(hr_img, dtype=np.float) / .
            lr_array = np.array(lr_img, dtype=np.float) / .
            
            return (torch.from_numpy(lr_array).unsqueeze(), 
                    torch.from_numpy(hr_array).unsqueeze(), 
                    self.hr_files[idx])
    
     加载数据
    diagnoser.log(" 加载数据集...")
    try:
        train_set = FixedDataset(
            r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/train/HR",
            r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/train/LR"
        )
        train_loader = DataLoader(train_set, batch_size=config["batch_size"], shuffle=True)
        diagnoser.log(f" 训练集: {len(train_set)} 样本")
    except Exception as e:
        diagnoser.log(f" 数据加载失败: {e}")
        return
    
     测试两种模型
    test_results = {}
    
    for model_name in ["原版LUMWCNN", "简单SR模型"]:
        diagnoser.log(f"\n 测试 {model_name}...")
        
         初始化模型
        if model_name == "原版LUMWCNN":
            try:
                from model import LUMWCNN
                model = LUMWCNN().to(config["device"])
                 添加输出限制
                model = nn.Sequential(model, nn.Sigmoid())
            except Exception as e:
                diagnoser.log(f" 原版模型加载失败: {e}")
                continue
        else:
            model = create_simple_sr_model().to(config["device"])
        
         模型诊断
        total_params, trainable_params = diagnoser.check_model_initialization(model)
        
         优化器和损失函数
        optimizer = optim.Adam(model.parameters(), lr=config["learning_rate"], weight_decay=e-)
        criterion = nn.MSELoss()
        
         获取一个样本进行数据流分析
        sample_lr, sample_hr, _ = train_set[]
        sample_lr = sample_lr.unsqueeze().to(config["device"])
        diagnoser.analyze_data_flow(model, sample_lr, config["device"])
        
         训练测试
        model.train()
        losses = []
        gradients_history = []
        
        diagnoser.log(" 开始训练测试...")
        for epoch in range():   个epoch测试
            epoch_loss = 
            epoch_gradients = []
            
            for batch_idx, (lr_batch, hr_batch, _) in enumerate(train_loader):
                if batch_idx >= :   只测试前个批次
                    break
                    
                lr_batch = lr_batch.to(config["device"])
                hr_batch = hr_batch.to(config["device"])
                
                 前向传播
                pred_batch = model(lr_batch)
                loss = criterion(pred_batch, hr_batch)
                
                 梯度检查
                has_gradients, grad_info = diagnoser.check_gradient_flow(model, loss, optimizer)
                epoch_gradients.append(has_gradients)
                
                 优化步骤
                optimizer.step()
                
                epoch_loss += loss.item()
                
                if batch_idx %  == :
                    diagnoser.log(f"  批次 {batch_idx}: 损失={loss.item():.f}, 梯度有效={has_gradients}")
                    
                     检查输出范围
                    with torch.no_grad():
                        output_range = f"[{pred_batch.min().item():.f}, {pred_batch.max().item():.f}]"
                        diagnoser.log(f"    输出范围: {output_range}, 均值={pred_batch.mean().item():.f}")
            
            avg_loss = epoch_loss / min(, len(train_loader))
            losses.append(avg_loss)
            gradients_history.append(epoch_gradients)
            
            diagnoser.log(f"Epoch {epoch+}: 平均损失={avg_loss:.f}")
        
         最终验证
        model.eval()
        with torch.no_grad():
            test_lr, test_hr, _ = train_set[]
            test_lr = test_lr.unsqueeze().to(config["device"])
            test_hr = test_hr.unsqueeze().to(config["device"])
            
            test_pred = model(test_lr)
            test_mse = criterion(test_pred, test_hr).item()
            test_psnr =   np.log(. / np.sqrt(test_mse)) if test_mse >  else float('inf')
            
            diagnoser.log(f" 最终测试 - PSNR: {test_psnr:.f} dB, MSE: {test_mse:.f}")
            diagnoser.log(f"    输出范围: [{test_pred.min().item():.f}, {test_pred.max().item():.f}]")
        
        test_results[model_name] = {
            'psnr': test_psnr,
            'mse': test_mse,
            'losses': losses,
            'has_valid_gradients': any(any(epoch) for epoch in gradients_history),
            'final_output_range': (test_pred.min().item(), test_pred.max().item())
        }
    
     结果分析
    diagnoser.log("\n" + "="  )
    diagnoser.log(" 诊断结果总结:")
    diagnoser.log("="  )
    
    for model_name, results in test_results.items():
        diagnoser.log(f"\n{model_name}:")
        diagnoser.log(f"  最终PSNR: {results['psnr']:.f} dB")
        diagnoser.log(f"  最终MSE: {results['mse']:.f}")
        diagnoser.log(f"  输出范围: [{results['final_output_range'][]:.f}, {results['final_output_range'][]:.f}]")
        diagnoser.log(f"  梯度有效: {results['has_valid_gradients']}")
        
        if results['psnr'] > :
            diagnoser.log("   模型学习正常!")
        elif results['psnr'] > :
            diagnoser.log("  ️ 模型学习效果一般")
        else:
            diagnoser.log("   模型学习失败!")
    
     保存诊断报告
    report_path = os.path.join(config["output_path"], "deep_diagnosis_report.txt")
    with open(report_path, 'w', encoding='utf-') as f:
        f.write("深度诊断报告\n")
        f.write("="   + "\n")
        for log_entry in diagnoser.diagnosis_log:
            f.write(log_entry + "\n")
    
    diagnoser.log(f"\n 诊断报告保存至: {report_path}")
    print("\n" + "="  )
    print("深度诊断完成!")
    print("="  )

if __name__ == "__main__":
    deep_diagnosis_test()