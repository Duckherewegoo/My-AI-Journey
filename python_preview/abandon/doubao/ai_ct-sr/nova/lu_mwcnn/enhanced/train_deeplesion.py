"""
LU-MWCNN 训练代码 @ DeepLesion (修复版)
修复点：解决 AverageMeter.update() 参数不匹配问题，增强类型兼容性
新增：超强Early-Stopping机制
新增：测试集评估环节
-新增：修复与检查相关函数及实现
修改：适配HR/LR图像对的超分辨率数据加载
"""

import os
import time
import glob
import importlib
from tqdm import tqdm
from datetime import datetime
import torch
import torch.nn as nn
import numpy as np
from PIL import Image
from base.utils.metrics import calc_psnr_torch, calc_ssim_torch
from base.utils.collate_fn import deeplesion_collate_fn
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.utils.data import DataLoader
from torch.utils.tensorboard.writer import SummaryWriter


 从 utils 导入所需工具（若不存在请确保实现）
 这里补充完整 AverageMeter 类的正确实现，避免参数错误
global config
 配置参数 - 集中管理可配置项
config = {
     配置参数 - 集中管理可配置项
     训练参数（针对RTX  Mobile优化）
    "lr": e-,  
     ============ 降低学习率 ============
    "epochs": ,
    "batch_size": ,
      Mobile显存有限，降低批次大小避免溢出
    "val_every": ,
    "num_workers": min(os.cpu_count() or , ),   根据CPU核心数自动调整，避免内存占用过高
    "device": "cuda:" if torch.cuda.is_available() else "cpu",   明确指定设备
    "keep_checkpoints": ,   保留最新的个检查点
     Early Stopping 配置
    "early_stopping": {
        "enabled": True,
        "patience": ,
        "min_delta": e-,
        "min_improvement": .,
        "warmup_epochs": ,
        "strategy": "composite",   'composite', 'psnr', 'loss', 'dynamic'
    },
     路径配置
    "output_path": r"/home/dake/Documents/Projects/Graduction_Projects/codes/nova/lu_mwcnn/output_deeplesion",
     数据集配置 - 更新为HR/LR结构
    "dataset": {
        "train_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/train/HR/",
        "val_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/val/HR",
        "test_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/test/HR", 
        "interface": "deeplesions.DeepLesionDataset",
        "crop_size": ,
        "scale_factor": ,   超分辨率缩放因子
        "noise_std": .,   生成LR的噪声参数，传给Dataset
    },
}
config["noise_std"] = config["dataset"]["noise_std"] 高斯噪声标准差
config["grad_clip_norm"] = .   梯度裁剪阈值
config["psnr_max"] = .   PSNR归一化最大值
config["gradient_check_interval"] =    梯度检查批次间隔
 ============ 在这里添加模型修复函数 ============
def repair_model_initialization(model):
    """修复模型初始化问题"""
    print("正在修复模型初始化...")
    
    def weights_init(m):
        if isinstance(m, (nn.Convd, nn.ConvTransposed)):
             使用Kaiming初始化
            torch.nn.init.kaiming_normal_(m.weight, mode='fan_in', nonlinearity='leaky_relu')
            if m.bias is not None:
                torch.nn.init.constant_(m.bias, )
        elif isinstance(m, nn.BatchNormd):
            torch.nn.init.constant_(m.weight, )
            torch.nn.init.constant_(m.bias, )
    
    model.apply(weights_init)
    return model


def check_gradient_health(model, logger):
    """检查梯度健康状况（修复版）"""
    total_params = 
    zero_gradients = 
    nan_gradients = 
    
    for name, param in model.named_parameters():
        total_params +=    统计所有参数（含无梯度的）
        if param.grad is None:
            logger.write(f"参数 {name} 无梯度（可能被冻结）")
            continue   无梯度则跳过后续判断
        
         计算当前参数的梯度均值（绝对值）
        grad_mean = param.grad.abs().mean().item()
        
         检查梯度是否接近零
        if grad_mean < e-:
            zero_gradients += 
            logger.write(f"警告: 参数 {name} 梯度接近零 (均值: {grad_mean:.e})")
        
         检查梯度是否包含NaN
        if torch.isnan(param.grad).any():
            nan_gradients += 
            logger.write(f"严重: 参数 {name} 梯度包含NaN")
    
     汇总日志（整体统计）
    if zero_gradients > :
        logger.write(f"\n梯度健康汇总: {zero_gradients}/{total_params} 个参数梯度接近零")
    if nan_gradients > :
        logger.write(f"\n梯度健康汇总: {nan_gradients}/{total_params} 个参数梯度为NaN")
    if zero_gradients ==  and nan_gradients == :
        logger.write("\n梯度健康汇总: 所有参数梯度状态正常")
    
    return zero_gradients, nan_gradients

def emergency_model_repair(model, logger):
    """紧急模型修复"""
    logger.write("执行紧急模型修复...")
    
    repair_count = 
    for name, param in model.named_parameters():
         修复NaN参数
        if torch.isnan(param).any():
            torch.nn.init.normal_(param, mean=, std=.)
            logger.write(f"修复NaN参数: {name}")
            repair_count += 
        
         修复梯度NaN
        if param.grad is not None and torch.isnan(param.grad).any():
            param.grad = torch.where(
                torch.isnan(param.grad),
                torch.zeros_like(param.grad),
                param.grad
            )
            repair_count += 
    
    if repair_count > :
        logger.write(f"完成 {repair_count} 处修复")
    else:
        logger.write("模型状态正常")
    
    return model

 通用数据健康检查函数（适配train/val/test）

def check_data_health(loader, config, logger=None, phase="train", check_batches=):
    """
    检查数据加载器的健康状态（修复config未定义+提升鲁棒性）
    Args:
        loader: DataLoader 数据加载器
        config: 全局配置字典（必须传入，解决未定义问题）
        logger: 日志对象（可选）
        phase: train/val/test（用于日志区分）
        check_batches: 检查的批次数量（测试集建议设为)
    """

    try:
         从传入的config读取缩放因子（修复未定义问题）
        scale = config.get("dataset", {}).get("scale_factor", )   加默认值，更鲁棒
        batch_count = 
        for batch_idx, data in enumerate(loader):
            if batch_count >= check_batches:   只检查指定数量的批次
                break
            batch_count += 
            
            
             . 鲁棒化解包数据
            if len(data) >= :
                lr, hr = data[:]
            else:
                safe_log(f"批次{batch_idx}数据格式错误，长度不足，数据：{data}")
                continue
            
             . 确保是tensor（避免非tensor类型）
            if not isinstance(lr, torch.Tensor):
                safe_log(f"批次{batch_idx} LR不是Tensor，类型：{type(lr)}")
                continue
            if hr is not None and not isinstance(hr, torch.Tensor):
                safe_log(f"批次{batch_idx} HR不是Tensor，类型：{type(hr)}")
                hr = None   置为None，跳过后续检查
            
             . 设备迁移（兼容hr为None）
            lr = lr.to(config["device"])
            hr = hr.to(config["device"]) if hr is not None else None
            
             . 检查NaN/Inf
            if torch.isnan(lr).any() or torch.isinf(lr).any():
                safe_log(f"批次 {batch_idx} LR包含NaN/Inf！")
            if hr is not None:
                if torch.isnan(hr).any() or torch.isinf(hr).any():
                    safe_log(f"批次 {batch_idx} HR包含NaN/Inf！")
            
             . 维度校验（确保是维 [B, C, H, W]）
            if len(lr.shape) != :
                safe_log(f"批次 {batch_idx} LR维度异常，应为维，实际：{lr.shape}")
                continue
            if hr is not None and len(hr.shape) != :
                safe_log(f"批次 {batch_idx} HR维度异常，应为维，实际：{hr.shape}")
                continue
            
             . 尺寸匹配检查（用配置的缩放因子）
            if hr is not None:
                lr_b, lr_c, lr_h, lr_w = lr.shape
                hr_b, hr_c, hr_h, hr_w = hr.shape
                
                 额外检查：批次大小、通道数一致
                if lr_b != hr_b:
                    safe_log(f"批次 {batch_idx} 批次大小不匹配：LR({lr_b}) vs HR({hr_b})")
                if lr_c != hr_c:
                    safe_log(f"批次 {batch_idx} 通道数不匹配：LR({lr_c}) vs HR({hr_c})")
                
                 缩放尺寸检查
                if hr_h != lr_h  scale or hr_w != lr_w  scale:
                    safe_log(f"批次 {batch_idx} 尺寸不匹配：LR({lr_h}x{lr_w}) → HR({hr_h}x{hr_w}) (缩放因子{scale})")
        
        safe_log(f"{phase}数据健康检查完成（检查前个批次）")
    
    except Exception as e:
        safe_log(f"{phase}数据集加载失败: {e}")
        raise   抛出异常，让上层感知错误

def safe_torch_load(file_path, map_location=None):
    """安全的 torch.load 包装函数"""
    try:
         方法: 使用文件对象
        with open(file_path, "rb") as f:
            return torch.load(f, map_location=map_location, weights_only=False)
    except Exception as e:
        print(f"文件对象加载失败: {e}")
         方法: 直接加载
        try:
            return torch.load(file_path, map_location=map_location, weights_only=False)
        except Exception as e:
            print(f"直接加载也失败: {e}")
            raise

 内置修复后的AverageMeter，不再依赖外部模块
class AverageMeter:
    """修复参数不匹配问题的AverageMeter"""
    def __init__(self):
        self.reset()

    def reset(self):
        self.val =      当前批次值
        self.avg =      平均值
        self.sum =      总和
        self.count =    样本数

    def update(self, val, n=):
        """
        更新指标
        :param val: 当前批次的指标值（如loss/psnr）
        :param n: 当前批次的样本数（默认）
        """
        self.val = val
        self.sum += val  n
        self.count += n
        self.avg = self.sum / self.count if self.count !=  else 

class SuperEarlyStopping:
    """
    超强Early-Stopping机制
    特点：
    . 多指标监控（PSNR、SSIM、Loss）
    . 自适应耐心值调整
    . 学习率衰减恢复
    . 最佳模型自动保存和恢复
    . 训练动态分析
    . 多种停止策略
    """

    def __init__(
        self,
        patience=,
        min_delta=e-,
        min_improvement=.,
        warmup_epochs=,
        strategy="composite",
        verbose=True,
        checkpoint_dir="",
    ):

        self.patience = patience
        self.min_delta = min_delta
        self.min_improvement = min_improvement
        self.warmup_epochs = warmup_epochs
        self.strategy = strategy   'composite', 'psnr', 'loss', 'dynamic'
        self.verbose = verbose
        self.checkpoint_dir = checkpoint_dir

         多指标跟踪
        self.best_psnr = -float("inf")
        self.best_ssim = -float("inf")
        self.best_loss = float("inf")
        self.best_composite_score = -float("inf")

         动态参数
        self.counter = 
        self.epochs_since_improvement = 
        self.lr_reduced = False
        self.early_stop = False
        self.best_epoch = 

         训练动态分析
        self.psnr_history = []
        self.loss_history = []
        self.improvement_trend = []

         自适应耐心值
        self.adaptive_patience = patience
        self.convergence_speed = .

         创建最佳模型保存路径
        self.best_model_path = os.path.join(checkpoint_dir, "best_model.pth")

        if verbose:
            print(f"Early-Stopping初始化: 策略={strategy}")
            print(f"耐心值={patience}, 热启动={warmup_epochs}")

    def calculate_composite_score(self, psnr, ssim, loss):
        """计算综合评分（PSNR和SSIM越高越好，Loss越低越好）"""
         归一化处理，确保各指标权重平衡
        psnr_norm = psnr / .   假设PSNR最大
        ssim_norm = ssim / .   SSIM最大
        loss_norm = . / (loss + e-)   Loss越小越好

         加权综合评分
        composite = .  psnr_norm + .  ssim_norm + .  loss_norm
        return composite

    def analyze_trend(self, current_psnr, current_loss):
        """分析训练趋势"""
        if len(self.psnr_history) >= :
             计算最近几个epoch的改进趋势
            recent_psnr = self.psnr_history[-:]
            recent_loss = self.loss_history[-:]

            psnr_trend = (current_psnr - recent_psnr[]) / .
            loss_trend = (recent_loss[] - current_loss) / .

             综合趋势分析
            trend_score = .  psnr_trend + .  loss_trend
            self.improvement_trend.append(trend_score)

             自适应调整耐心值
            if len(self.improvement_trend) >= :
                avg_trend = np.mean(self.improvement_trend[-:])
                if avg_trend > .:   快速改进阶段
                    self.adaptive_patience = max(self.patience // , )
                    self.convergence_speed = .
                elif avg_trend < -.:   性能下降阶段
                    self.adaptive_patience = self.patience
                    self.convergence_speed = .
                else:   稳定阶段
                    self.adaptive_patience = int(self.patience  .)
                    self.convergence_speed = .

    def should_stop(self, epoch, psnr, ssim, loss, model, optimizer, scheduler, logger):
        """
        判断是否应该停止训练
        返回: (should_stop, reason)
        """
         热启动阶段不进行early stopping
        if epoch < self.warmup_epochs:
            return False, "warmup"

         更新历史记录
        self.psnr_history.append(psnr)
        self.loss_history.append(loss)

         分析训练趋势
        self.analyze_trend(psnr, loss)

         计算综合评分
        current_composite = self.calculate_composite_score(psnr, ssim, loss)

        improvement_found = False
        stop_reason = ""

         根据策略判断改进
        if self.strategy == "composite":
            if current_composite > self.best_composite_score + self.min_delta:
                improvement_found = True
                self.best_composite_score = current_composite
        elif self.strategy == "psnr":
            if psnr > self.best_psnr + self.min_delta:
                improvement_found = True
                self.best_psnr = psnr
        elif self.strategy == "loss":
            if loss < self.best_loss - self.min_delta:
                improvement_found = True
                self.best_loss = loss
        elif self.strategy == "dynamic":
             动态策略：根据训练阶段调整判断标准
            if epoch < self.patience:   早期阶段主要看PSNR
                if psnr > self.best_psnr + self.min_delta:
                    improvement_found = True
                    self.best_psnr = psnr
            else:   后期阶段看综合评分
                if current_composite > self.best_composite_score + self.min_delta / :
                    improvement_found = True
                    self.best_composite_score = current_composite

         处理改进情况
        if improvement_found:
            self.counter = 
            self.epochs_since_improvement = 
            self.best_epoch = epoch

            self.best_ssim = ssim   补充更新SSIM
             保存最佳模型
            self.save_best_model(model, optimizer, scheduler, epoch, psnr, ssim, loss)

            if self.verbose:
                logger.write(f"发现改进!: PSNR: {psnr:.f}")
                logger.write(f"SSIM: {ssim:.f}, Loss: {loss:.f}")

        else:
            self.counter += 
            self.epochs_since_improvement += 

             学习率衰减恢复机制
            if (
                self.epochs_since_improvement > self.adaptive_patience // 
                and not self.lr_reduced
            ):
                self.reduce_learning_rate(optimizer, logger)
                self.lr_reduced = True
                stop_reason = "lr_reduced"

         检查停止条件
        if self.counter >= self.adaptive_patience:
            self.early_stop = True
            stop_reason = f"patience_exceeded_{self.adaptive_patience}"

         性能下降检查
        if len(self.psnr_history) > :
            recent_avg = np.mean(self.psnr_history[-:])
            previous_avg = np.mean(self.psnr_history[-:-])
            if recent_avg < previous_avg - self.min_improvement  :
                stop_reason = "performance_degradation"
                self.early_stop = True

         收敛检查
        if len(self.psnr_history) > :
            last__std = np.std(self.psnr_history[-:])
            if last__std < self.min_delta  :   波动很小，可能已收敛
                stop_reason = "converged"
                self.early_stop = True

        if self.early_stop and self.verbose:
            logger.write(f"Early Stopping触发! 原因: {stop_reason}")
            logger.write(
                f"最佳结果 - Epoch: {self.best_epoch}, "
                f"PSNR: {self.best_psnr:.f}, SSIM: {self.best_ssim:.f}"
            )

        return self.early_stop, stop_reason

    def reduce_learning_rate(self, optimizer, logger):
        """降低学习率（增强版）"""
         检查优化器是否包含参数组
        if not optimizer.param_groups:
            logger.write("错误：尝试降低空优化器的学习率")
            return

         记录原始学习率并执行衰减
        original_lrs = [pg["lr"] for pg in optimizer.param_groups]
    
        for param_group in optimizer.param_groups:
            param_group["lr"] = .   半衰期衰减

        if self.verbose:
             安全获取衰减后的学习率（避免未绑定问题）
            new_lrs = [pg["lr"] for pg in optimizer.param_groups]
            logger.write(
                f"学习率衰减: {original_lrs[]:.e} → {new_lrs[]:.e} "
                f"(已衰减 {len(optimizer.param_groups)} 个参数组)"
            )
    def save_best_model(self, model, optimizer, scheduler, epoch, psnr, ssim, loss):
        """保存最佳模型"""
        checkpoint = {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "psnr": psnr,
            "ssim": ssim,
            "loss": loss,
            "best_psnr": self.best_psnr,
            "best_ssim": self.best_ssim,
            "best_loss": self.best_loss,
        }
        torch.save(checkpoint, self.best_model_path)

     在 SuperEarlyStopping 类中
    def load_best_model(self, model, optimizer=None, scheduler=None):
        if os.path.exists(self.best_model_path):
            try:
                checkpoint = safe_torch_load(self.best_model_path)
                model.load_state_dict(checkpoint["model_state_dict"])
                if optimizer and "optimizer_state_dict" in checkpoint:
                    optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
                if scheduler and "scheduler_state_dict" in checkpoint:
                    scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
                return checkpoint
            except Exception as e:
                print(f"加载最佳模型失败: {e}")
                return None
        return None

    def get_status_report(self):
        """获取状态报告"""
        return {
            "best_epoch": self.best_epoch,
            "best_psnr": self.best_psnr,
            "best_ssim": self.best_ssim,
            "best_loss": self.best_loss,
            "epochs_since_improvement": self.epochs_since_improvement,
            "adaptive_patience": self.adaptive_patience,
            "convergence_speed": self.convergence_speed,
        }




 初始化目录结构


def init_directories():
    """确保所有必要的输出目录存在"""
    dirs = [
        config["output_path"],
        os.path.join(config["output_path"], "ckp"),
        os.path.join(config["output_path"], "val_inference"),
        os.path.join(config["output_path"], "test_inference"),   新增测试推理目录
        os.path.join(config["output_path"], "logs"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


 检查点管理


def find_latest_checkpoint(ckp_dir):
    """查找最新的检查点文件"""
    checkpoint_files = glob.glob(os.path.join(ckp_dir, "epoch_.pth"))
    if not checkpoint_files:
        return None

     提取epoch号并排序
    def get_epoch(file_path):
        return int(os.path.basename(file_path).split("_")[].split(".")[])

    checkpoint_files.sort(key=get_epoch, reverse=True)
    return checkpoint_files[]


def clean_old_checkpoints(ckp_dir, keep_num):
    """清理旧的检查点，只保留最新的N个"""
    checkpoint_files = glob.glob(os.path.join(ckp_dir, "epoch_.pth"))
    if len(checkpoint_files) <= keep_num:
        return

    def get_epoch(file_path):
        return int(os.path.basename(file_path).split("_")[].split(".")[])

     按epoch升序排序（oldest first）
    checkpoint_files.sort(key=get_epoch)
     删除多余的旧检查点
    for file in checkpoint_files[:-keep_num]:
        try:
            os.remove(file)
            print(f"已清理旧检查点: {file}")
        except Exception as e:
            print(f"清理检查点失败 {file}: {e}")


 日志系统

 单例Logger实例（避免重复创建）
_logger_instance = None

def get_logger():
    """创建单例日志记录器（只创建一次，避免多文件）"""
    global _logger_instance
     如果已创建，直接返回现有实例
    if _logger_instance is not None:
        return _logger_instance
    
     确保日志目录存在
    log_dir = os.path.join(config["output_path"], "logs")
    os.makedirs(log_dir, exist_ok=True)
    
     生成日志文件名（只在第一次创建时生成时间戳）
    log_file = os.path.join(
        log_dir,
        f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
    )

    class Logger:
        def __init__(self, log_file):
            self.log_file = log_file
             初始化时创建空文件（避免追加到旧文件）
            with open(self.log_file, "w", encoding="utf-") as f:
                f.write(f"日志开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        def write(self, message):
            """同时写入控制台和日志文件"""
            print(message)
            with open(self.log_file, "a", encoding="utf-") as f:
                f.write(message + "\n")

     赋值给单例变量
    _logger_instance = Logger(log_file)
    return _logger_instance

 修正后的safe_log（复用单例Logger）
def safe_log(msg):
    """安全日志函数（复用已创建的Logger）"""
    try:
        logger = get_logger()   此时返回的是单例，不会重复创建
        logger.write(msg)
    except Exception as e:
         日志创建失败时，仅打印到控制台
        print(f"日志写入失败: {e} | 消息: {msg}")

 模型初始化与恢复


def init_model():
    """初始化模型并尝试从检查点恢复"""
    from model import LUMWCNN   显式导入模型，避免类型错误

    model = LUMWCNN().to(config["device"])
    
     ============ 修复模型初始化 ============
    model = repair_model_initialization(model)
    
     检查并修复NaN参数
    for name, param in model.named_parameters():
        if torch.isnan(param).any():
            print(f"修复NaN参数: {name}")
            torch.nn.init.normal_(param, mean=, std=.)

     支持多卡训练（如果有多个GPU）
    if torch.cuda.device_count() > :
        model = nn.DataParallel(model)
        print(f"使用 {torch.cuda.device_count()} 张GPU进行训练")

    return model



def load_checkpoint(model, optimizer, scheduler, ckp_path):
    try:
        checkpoint = safe_torch_load(ckp_path, config["device"])
         处理多卡前缀
        state_dict = checkpoint["model_state_dict"]
        state_dict = {k.replace('module.', ''): v for k, v in state_dict.items()}
         仅加载处理后的state_dict（删除重复的load语句）
        model.load_state_dict(state_dict)
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        start_epoch = checkpoint["epoch"] + 
        print(f"成功从 {ckp_path} 恢复，将从epoch {start_epoch} 开始训练")
        return start_epoch
    except Exception as e:
        print(f"检查点加载失败: {e}")
        raise


 测试集评估函数

def evaluate_test_set(model, logger, save_images=False):
    """
    在测试集上评估模型性能
    参数:
        model: 训练好的模型
        logger: 日志记录器（需实现write方法）
        save_images: 是否保存推理图像
    """
    logger.write("\n" + "="  )
    logger.write("开始测试集评估")
    logger.write("="  )

     加载测试数据集
    try:
        dataset_module = importlib.import_module(
            "." + config["dataset"]["interface"].split(".")[], "base.datasets"
        )
        DatasetClass = eval(
            f"dataset_module.{config['dataset']['interface'].split('.')[]}"
        )
        pin_memory = config["device"].startswith("cuda")
         统一num_workers配置（CPU时设为，避免死锁）
        num_workers = config["num_workers"] //  if pin_memory else 
        test_set = DatasetClass(
            hr_dir=config["dataset"]["test_hr_dir"], 
            crop_size=config["dataset"]["crop_size"],
            scale_factor=config["dataset"]["scale_factor"],
            noise_std=config["dataset"]["noise_std"],
            phase="test",   测试模式
        )
        test_loader = DataLoader(
            test_set,
            batch_size=,   测试时批次大小为
            shuffle=False,
            pin_memory=pin_memory,   统一pin_memory配置
            collate_fn=deeplesion_collate_fn,
            num_workers=num_workers,
        )
        logger.write(f"测试集大小: {len(test_set)}")

         ============ 新增：测试集数据健康检查（简化版） ============
        logger.write("开始测试集数据健康检查...")
         调用check_data_health，指定phase="test"，仅检查前个批次（足够覆盖问题）
         注意：传入正确的参数顺序（loader, config, logger, phase）
        check_data_health(test_loader, config, logger, "test", check_batches=)
        logger.write("测试集数据健康检查完成！")
    except Exception as e:
        logger.write(f"测试集加载失败: {str(e)}")
        return None

     初始化指标
    test_psnr = AverageMeter()
    test_ssim = AverageMeter()
    test_loss = AverageMeter()
    criterion = nn.MSELoss()

    model.eval()
    test_start_time = time.time()

     创建测试结果目录
    test_inference_dir = os.path.join(config["output_path"], "test_inference")
    os.makedirs(test_inference_dir, exist_ok=True)

     测试推理 - 核心修复：循环迭代逻辑
    with torch.no_grad():
          修复：用enumerate获取batch_idx，迭代变量仅data（移除错误的epoch）
        for batch_idx, data in enumerate(tqdm(test_loader, ncols=, desc="Testing")):
            try:
                  修复：鲁棒化解包数据，移除epoch引用
                if len(data) == :
                    lr, hr, filename = data
                     处理批量filename（batch_size=时取第一个）
                    filename = filename[] if isinstance(filename, (list, tuple)) else filename
                elif len(data) == :
                    lr, hr = data
                     生成filename时仅用batch_idx（无epoch）
                    filename = f"batch_{batch_idx}"
                else:
                    logger.write(f"批次{batch_idx}：无效的data格式（长度{len(data)}），跳过")
                    continue                
                
                 设备迁移（non_blocking仅在cuda时生效）
                lr = lr.to(config["device"], non_blocking=pin_memory)
                hr = hr.to(config["device"], non_blocking=pin_memory)

                 模型推理
                predict = model(lr)
                loss = criterion(predict, hr)

                  修复：增强数据维度/类型校验，避免squeeze后维度异常
                 确保是D图像（移除batch/channel维度）
                predict = predict.detach().cpu().clamp(, )
                predict = predict.squeeze() if predict.dim() >  else predict
                hr_np = hr.squeeze().cpu() if hr.dim() >  else hr.cpu()

                 确保是float类型（避免计算指标时类型错误）
                if predict.dtype != torch.float:
                    predict = predict.float()
                if hr_np.dtype != torch.float:
                    hr_np = hr_np.float()

                 计算指标
                psnr = calc_psnr_torch(predict, hr_np)
                ssim = calc_ssim_torch(predict, hr_np)

                 更新指标
                test_psnr.update(psnr, n=)   batch_size=，n=
                test_ssim.update(ssim, n=)
                test_loss.update(loss.item(), n=)

                 保存测试结果图像（可选）
                if save_images:
                      修复：filename处理（避免字符串取[]崩溃）
                    base_name = filename if isinstance(filename, str) else f"batch_{batch_idx}"
                    
                     处理预测图
                    predict_y = np.array(predict.numpy()  , dtype=np.uint)
                    predict_gray = Image.fromarray(predict_y, mode="L")
                    pred_filename = f"{base_name}_pred.png"
                    pred_path = os.path.join(test_inference_dir, pred_filename)
                    predict_gray.save(pred_path)

                     处理输入LR图
                    lr_array = lr.detach().cpu().numpy()
                    lr_squeezed = lr_array.squeeze() if lr_array.ndim >  else lr_array
                    lr_scaled = (lr_squeezed  ).clip(, )   防止溢出
                    lr_y = np.array(lr_scaled, dtype=np.uint)
                    lr_filename = f"{base_name}_lr.png"
                    lr_path = os.path.join(test_inference_dir, lr_filename)
                    Image.fromarray(lr_y, mode="L").save(lr_path)

                     处理参考HR图
                    hr_array = hr_np.numpy()
                    hr_scaled = (hr_array  ).clip(, )   防止溢出
                    hr_y = np.array(hr_scaled, dtype=np.uint)
                    hr_filename = f"{base_name}_hr.png"
                    hr_path = os.path.join(test_inference_dir, hr_filename)
                    Image.fromarray(hr_y, mode="L").save(hr_path)
                    
            except Exception as e:
                logger.write(f"批次{batch_idx}处理失败：{str(e)}，跳过")
                continue

     记录测试结果
    test_time = time.time() - test_start_time
    logger.write(f"测试集评估完成!")
    logger.write(f"测试结果:")
    logger.write(f"  PSNR: {test_psnr.avg:.f} dB")
    logger.write(f"  SSIM: {test_ssim.avg:.f}")
    logger.write(f"  Loss: {test_loss.avg:.f}")
    logger.write(f"  样本数: {test_psnr.count}")
    logger.write(f"  耗时: {test_time:.f}s")

     保存测试结果到文件
    test_results = {
        "psnr": test_psnr.avg,
        "ssim": test_ssim.avg,
        "loss": test_loss.avg,
        "num_samples": test_psnr.count,
        "test_time": test_time,
    }

     写入测试结果文件
    results_file = os.path.join(config["output_path"], "test_results.txt")
    with open(results_file, "w", encoding="utf-") as f:
        f.write("测试集评估结果\n")
        f.write("="   + "\n")
        f.write(f"评估时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"PSNR: {test_psnr.avg:.f} dB\n")
        f.write(f"SSIM: {test_ssim.avg:.f}\n")
        f.write(f"Loss: {test_loss.avg:.f}\n")
        f.write(f"样本数量: {test_psnr.count}\n")
        f.write(f"测试耗时: {test_time:.f}s\n")

    return test_results


 主训练函数


def main():
     初始化环境
    init_directories()
    logger = get_logger()
    logger.write(f"训练开始于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.write(f"使用设备: {config['device']}")
    logger.write("===== 训练配置 =====")
    for k, v in config.items():
        if isinstance(v, dict):
            logger.write(f"{k}:")
            for k, v in v.items():
                logger.write(f"  {k}: {v}")
        else:
            logger.write(f"{k}: {v}")
    logger.write("====================")
     将长表达式拆分成多个部分
    gpu_info = (
        torch.cuda.get_device_name(config["device"])
        if config["device"].startswith("cuda")
        else "CPU"
    )
    logger.write(f"GPU信息: {gpu_info}")
    logger.write(f"超分辨率缩放因子: {config['dataset']['scale_factor']}x")

     初始化early stopping
    early_stopping = None
    if config["early_stopping"]["enabled"]:
        early_stopping = SuperEarlyStopping(
            patience=config["early_stopping"]["patience"],
            min_delta=config["early_stopping"]["min_delta"],
            min_improvement=config["early_stopping"]["min_improvement"],
            warmup_epochs=config["early_stopping"]["warmup_epochs"],
            strategy=config["early_stopping"]["strategy"],
            verbose=True,
            checkpoint_dir=os.path.join(config["output_path"], "ckp"),
        )
        logger.write("Early-Stopping机制已启用")

     初始化模型、损失函数、优化器
    model = init_model()
    criterion = nn.MSELoss()
    
     . 初始化优化器
    optimizer = torch.optim.Adam(model.parameters(), lr=e-, weight_decay=e-)

     . 配置带重启的余弦退火（参数正确）
    scheduler = lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer,
        T_=,         初始重启周期（每个epoch重启一次学习率）
        T_mult=,       重启后周期倍增（第次重启周期，第次，第次...）
        eta_min=e-,   最小学习率
        last_epoch=-
    )

     ============ 定义warmup参数（放在训练循环前） ============
    warmup_epochs = 
    warmup_lr_start = e-
    warmup_lr_end = e-
    lr_step = (warmup_lr_end - warmup_lr_start) / warmup_epochs     加载数据集 - 适配HR/LR结构

    try:
        logger.write(f"加载数据集: {config['dataset']['interface']}")
        dataset_module = importlib.import_module(
            "." + config['dataset']["interface"].split(".")[], "base.datasets"
        )
        DatasetClass = eval(
            f"dataset_module.{config['dataset']['interface'].split('.')[]}"
        )

        pin_memory = config["device"].startswith("cuda")
        num_workers = config["num_workers"] if pin_memory else    CPU时num_workers=避免死锁

   
         训练集
         修改后（使用正确的参数名和关键字参数）
        train_set = DatasetClass(
            hr_dir=config["dataset"]["train_hr_dir"],
            crop_size=config["dataset"]["crop_size"],
            noise_std=config["dataset"]["noise_std"],
            phase="train",   使用 phase 而不是 mode
            scale_factor=config["dataset"]["scale_factor"],
        )
        train_loader = DataLoader(
            train_set,
            batch_size=config["batch_size"],
            shuffle=True,
            num_workers=num_workers,
            pin_memory=pin_memory,
            collate_fn=deeplesion_collate_fn,
            drop_last=True,   避免最后一个批次尺寸不一致
        )

         验证集
        val_set = DatasetClass(
            hr_dir=config["dataset"]["val_hr_dir"],
            crop_size=config["dataset"]["crop_size"],
            noise_std=config["dataset"]["noise_std"],
            scale_factor=config["dataset"]["scale_factor"],
            phase="val",
        )
        val_loader = DataLoader(
            val_set,
            batch_size=,
            shuffle=False,
            pin_memory=pin_memory,
            collate_fn=deeplesion_collate_fn,
            num_workers=num_workers //  if pin_memory else ,   验证时减少worker
        )

        logger.write(f"训练集大小: {len(train_set)}")
        logger.write(f"验证集大小: {len(val_set)}")

         ============ 添加数据健康检查 ============
        check_data_health(train_loader, config, logger, "train")
        check_data_health(val_loader, config, logger, "val")   
    except Exception as e:
        logger.write(f"数据集加载失败: {e}")
        return

     初始化TensorBoard
    tb_writer = SummaryWriter(os.path.join(config["output_path"], "tensorboard"))

     检查断点续传
    ckp_dir = os.path.join(config["output_path"], "ckp")
    os.makedirs(ckp_dir, exist_ok=True)
    latest_ckp = find_latest_checkpoint(ckp_dir)
    start_epoch = 
    if latest_ckp:
        start_epoch = load_checkpoint(model, optimizer, scheduler, latest_ckp)
    
    
               
     训练主循环
    epoch = -
    current_lr = warmup_lr_start
    try:
        total_epochs = config["epochs"]
        for epoch in range(start_epoch, config["epochs"]):
             ============ 定期模型修复 ============
            if epoch %  == :   每个epoch检查一次
                model = emergency_model_repair(model, logger)
              ============ 手动添加warmup逻辑 ============
            if epoch < warmup_epochs:
                current_lr = warmup_lr_start + epoch  lr_step
                for param_group in optimizer.param_groups:
                    param_group['lr'] = current_lr
            else:
                 注意：CosineAnnealingWarmRestarts需要每个epoch都step
                scheduler.step()
                current_lr = optimizer.param_groups[]['lr']
        
            logger.write(f"Epoch {epoch+}/{total_epochs}: LR = {current_lr:.f}")

            epoch_start_time = time.time()
            model.train()
            epoch_loss = AverageMeter()
             ... 剩下的训练代码 ...
             使用修复后的AverageMeter
             训练阶段
            with tqdm(
                total=len(train_loader)  config["batch_size"],
                ncols=,
                desc=f'Training Epoch {epoch + }/{config["epochs"]}',
            ) as t:
                for batch_idx, data in enumerate(train_loader):
                    try:
                        lr, hr= data
                        lr = lr.to(config["device"], non_blocking=True)
                        hr = hr.to(config["device"], non_blocking=True)

                         前向传播
                        predict = model(lr)
                        loss = criterion(predict, hr)

                         反向传播
                        optimizer.zero_grad(set_to_none=True)
                        loss.backward()
                         ============ 添加梯度监控 ============
                        if batch_idx %  == :
                             记录学习率
                            tb_writer.add_scalar("Train/Learning Rate", optimizer.param_groups[]["lr"], epoch)
                             记录梯度范数
                            total_grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), float('inf'))
                            global_step = epoch  len(train_loader) + batch_idx
                            tb_writer.add_scalar("Train/Gradient Norm", total_grad_norm, global_step)
                             检查梯度健康
                            zero_grads, nan_grads = check_gradient_health(model, logger)
                            if nan_grads > :
                                logger.write(f"批次 {batch_idx} 检测到NaN梯度，跳过")
                                optimizer.zero_grad()
                                t.update(config["batch_size"])
                                continue

                         ============ 添加梯度裁剪 ============
                        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=config["grad_clip_norm"])               
                        optimizer.step()

                         更新metrics
                        batch_size = lr.size()
                        epoch_loss.update(val=loss.item(), n=batch_size)

                         更新进度条
                        t.set_postfix({
                            "loss": f"{epoch_loss.avg:.f}",
                            "lr": f'{optimizer.param_groups[]["lr"]:.f}',
                        })
                        t.update(batch_size)

                    except Exception as e:
                        logger.write(f"批次 {batch_idx} 处理失败: {e}")
                        optimizer.zero_grad()   清除失败批次的梯度
                        continue
                 记录 epoch 损失
                tb_writer.add_scalar("Train/Epoch Loss", epoch_loss.avg, epoch)
                logger.write(
                    f"Epoch {epoch + }/{config['epochs']} | "
                    f"Loss: {epoch_loss.avg:.f} | "
                    f"LR: {optimizer.param_groups[]['lr']:.f} | "
                    f"耗时: {time.time() - epoch_start_time:.f}s"
                )

             学习率调度
            scheduler.step()

             补充：epoch耗时统计
            epoch_time = time.time() - epoch_start_time
            logger.write(f"Epoch {epoch+} 完成 | 耗时: {epoch_time:.f}s | 平均损失: {epoch_loss.avg:.f}")


             保存检查点
            ckp_path = os.path.join(ckp_dir, f"epoch_{epoch}.pth")
            try:
                checkpoint = {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "scheduler_state_dict": scheduler.state_dict(),
                    "loss": epoch_loss.avg,
                }
                torch.save(checkpoint, ckp_path)
                logger.write(f"已保存检查点: {ckp_path}")
                clean_old_checkpoints(ckp_dir, config["keep_checkpoints"])
            except Exception as e:
                logger.write(f"检查点保存失败: {e}")

             验证阶段
            if epoch ==  or (epoch + ) % config["val_every"] == :
                model.eval()
                epoch_psnr = AverageMeter()
                epoch_ssim = AverageMeter()
                val_start_time = time.time()

                with torch.no_grad():
                      enumerate(loader) 会返回「批次索引 + 批次数据」，和循环变量一一匹配
                    for batch_idx, data in enumerate(tqdm(val_loader, ncols=, desc="Validation")):
                        try:
                              加固解包逻辑：先初始化，再按长度解包
                            lr, hr = None, None
                            filename = f"batch_{batch_idx}_epoch_{epoch}"   初始化filename
            
                            if len(data) == :
                                 有filename的情况：解包个值，保留前个核心值
                                lr, hr, filename = data
                                 处理批量filename（batch_size=时取第一个）
                                filename = filename[] if isinstance(filename, (list, tuple)) else filename
                            elif len(data) == :
                                 无filename的情况：仅解包个值，无报错
                                lr, hr = data
                            else:
                                logger.write(f"批次{batch_idx}：无效的data格式（长度{len(data)}），跳过")
                                continue                            
                            lr = lr.to(config["device"], non_blocking=True)
                            hr = hr.to(config["device"], non_blocking=True)

                             模型推理
                            predict = model(lr).detach().cpu().clamp(, )

                             数据处理
                            predict = predict.squeeze()
                            hr_np = hr.squeeze().cpu()

                             计算指标（假设已有实现）
                            
                            psnr = calc_psnr_torch(predict, hr_np)
                            ssim = calc_ssim_torch(predict, hr_np)
                            epoch_psnr.update(psnr)
                            epoch_ssim.update(ssim)

                             保存结果
                            predict_y = np.array(predict.numpy()  , dtype=np.uint)
                            predict_gray = Image.fromarray(predict_y, mode="L")
                             最保守的版本，完全避免任何可能的格式问题：
                            val_inference_dir = os.path.join(
                                config["output_path"], "val_inference"
                            )

                             保存预测结果
                            base_name = filename[]
                            pred_filename = base_name + "_pred.png"
                            pred_path = os.path.join(val_inference_dir, pred_filename)
                            predict_gray.save(pred_path)

                             保存输入图
                            lr_array = lr.detach().cpu().numpy()
                            lr_squeezed = lr_array.squeeze()
                            lr_scaled = lr_squeezed  
                            lr_y = np.array(lr_scaled, dtype=np.uint)
                            lr_filename = base_name + "_lr.png"
                            lr_path = os.path.join(val_inference_dir, lr_filename)
                            Image.fromarray(lr_y, mode="L").save(lr_path)

                             保存参考图
                            hr_array = hr_np.numpy()
                            hr_scaled = hr_array  
                            hr_y = np.array(hr_scaled, dtype=np.uint)
                            hr_filename = base_name + "_hr.png"
                            hr_path = os.path.join(val_inference_dir, hr_filename)
                            Image.fromarray(hr_y, mode="L").save(hr_path)
                        except Exception as e:
                            logger.write(f"数据解包失败：{e}，跳过该批次")                            
                            continue

                 记录验证指标
                tb_writer.add_scalar("Val/PSNR", epoch_psnr.avg, epoch)
                tb_writer.add_scalar("Val/SSIM", epoch_ssim.avg, epoch)
                logger.write(
                    f"验证结果 | PSNR: {epoch_psnr.avg:.f} | "
                    f"SSIM: {epoch_ssim.avg:.f} | "
                    f"耗时: {time.time() - val_start_time:.f}s"
                )

                 Early Stopping 检查
                val_psnr = epoch_psnr.avg
                val_ssim = epoch_ssim.avg
                val_loss = epoch_loss.avg   若需要可计算验证损失
                 记录到TensorBoard
                tb_writer.add_scalar("Val/PSNR", val_psnr, epoch)
                tb_writer.add_scalar("Val/SSIM", val_ssim, epoch)
                 调用EarlyStopping判断是否停止
                if early_stopping:
                    stop, reason = early_stopping.should_stop(epoch, val_psnr, val_ssim, val_loss, model, optimizer, scheduler, logger)
                    if stop:
                        logger.write(f"EarlyStopping触发，终止训练！原因：{reason}")
                         加载最佳模型
                        early_stopping.load_best_model(model)
                        break

             检查是否达到最大epoch
            if epoch == config["epochs"] - :
                logger.write("达到最大训练周期，训练完成")

        logger.write(f"训练完成于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

         最终报告
        if early_stopping:
            final_status = early_stopping.get_status_report()
            logger.write("="  )
            logger.write("最终训练报告:")
            logger.write(f"   最佳Epoch: {final_status['best_epoch']}")
            logger.write(f"   最佳PSNR: {final_status['best_psnr']:.f}")
            logger.write(f"   最佳SSIM: {final_status['best_ssim']:.f}")
            logger.write(f"   最佳Loss: {final_status['best_loss']:.f}")
            logger.write("="  )

         训练完成后进行测试集评估
        logger.write("\n" + "="  )
        logger.write("开始最终测试集评估")
        logger.write("="  )

         确保使用最佳模型进行测试
        if early_stopping and os.path.exists(early_stopping.best_model_path):
            logger.write("加载最佳模型进行测试...")
            early_stopping.load_best_model(model)
        else:
            logger.write("使用最终模型进行测试...")

         执行测试集评估
        test_results = evaluate_test_set(model, logger, save_images=True)

        if test_results:
            logger.write("测试集评估完成!")
            logger.write(
                f"最终测试结果 - PSNR: {test_results['psnr']:.f} dB, "
                f"SSIM: {test_results['ssim']:.f}"
            )

    except KeyboardInterrupt:
            logger.write("检测到用户中断，保存当前状态...")
             边界检查：epoch有效时才保存
            if epoch >= :
                emergency_ckp = os.path.join(ckp_dir, f"emergency_epoch_{epoch}.pth")
                torch.save(
                    {
                        "epoch": epoch,
                        "model_state_dict": model.state_dict(),
                        "optimizer_state_dict": optimizer.state_dict(),
                        "scheduler_state_dict": scheduler.state_dict(),
                    },
                    emergency_ckp,
                )
                logger.write(f"紧急检查点已保存: {emergency_ckp}")

                 中断时测试（仅epoch有效时执行）
                if epoch > :
                    response = input("\n是否在中断前进行测试集评估？(y/n): ").lower().strip()
                    if response == "y":
                        test_results = evaluate_test_set(model, logger, save_images=False)
            else:
                logger.write("未进入训练循环，无需保存紧急检查点")

     ========== 修复：通用异常处理（epoch已初始化） ==========
    except Exception as e:
            logger.write(f"训练过程发生错误: {str(e)}")
             边界检查：epoch有效时才保存
            if epoch >= :
                error_ckp = os.path.join(ckp_dir, f"error_epoch_{epoch}.pth")
                torch.save(
                    {"epoch": epoch, "model_state_dict": model.state_dict()}, 
                    error_ckp
                )
                logger.write(f"错误检查点已保存: {error_ckp}")
            else:
                logger.write("未进入训练循环，无需保存错误检查点")
                 抛出异常，让上层感知
                raise e
    finally:
        tb_writer.close()


if __name__ == "__main__":
    main()
