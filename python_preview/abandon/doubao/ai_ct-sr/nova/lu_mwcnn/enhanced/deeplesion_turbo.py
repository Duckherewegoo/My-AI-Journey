"""
LU-MWCNN 训练代码 @ DeepLesion (最终优化版+PSNR提升)
核心优化：
. 修复测试集HR图像全黑/数值范围异常问题（强制归一化到-）
. 修复EarlyStopping的best_psnr显示-inf问题
. 优化训练策略提升PSNR（调整损失/噪声/裁剪尺寸/学习率）
. 增强数据校验和归一化逻辑
. 优化早停策略避免过早终止
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


 全局配置参数 - 优化后（提升PSNR关键调整）
config = {
     训练参数（针对RTX  Mobile优化）
    "lr": e-,
    "epochs": ,
    "batch_size": ,
    "val_every": ,
    "num_workers": min(os.cpu_count() or , ),
    "device": "cuda:" if torch.cuda.is_available() else "cpu",
    "keep_checkpoints": ,
     Early Stopping 配置（优化早停策略）
    "early_stopping": {
        "enabled": True,
        "patience": ,           增加耐心值避免过早停止
        "min_delta": e-,        降低最小改进阈值
        "min_improvement": .,   降低性能下降阈值
        "warmup_epochs": ,      延长预热期
        "strategy": "composite",
    },
     路径配置
    "output_path": r"/home/dake/Documents/Projects/Graduction_Projects/codes/nova/lu_mwcnn/output_deeplesion",
    "tb_log_dir": r"/home/dake/Documents/Projects/Graduction_Projects/codes/nova/lu_mwcnn/tb_logs/deeplesion",
     数据集配置（核心优化）
    "dataset": {
        "train_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/train/HR/",
        "val_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/val/HR",
        "test_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/test/HR",
        "interface": "deeplesion_plus.DeepLesionDataset",
        "crop_size": ,         增大裁剪尺寸，提升上下文信息
        "scale_factor": ,
        "noise_std": .,       降低噪声，减少输入干扰
        "augment": True,
        "force_normalize": True,   强制归一化到-
    },
     训练优化配置（提升PSNR关键）
    "loss": {
        "use_mixed_loss": True,
        "l_weight": .,         调整损失权重，增强拟合
        "mse_weight": .,
    },
    "grad_clip_norm": .,        调整梯度裁剪，更合理的梯度控制
    "psnr_max": .,
    "gradient_check_interval": ,
    "warmup_epochs": ,          延长warmup，学习率更平缓
    "warmup_lr_start": e-,
    "warmup_lr_end": e-,
}
config["noise_std"] = config["dataset"]["noise_std"]

 ============ 工具函数 - 拆分高复杂度函数 ============


def _init_layer_weights(m):
    """初始化层权重（拆分自repair_model_initialization）"""
    if isinstance(m, (nn.Convd, nn.ConvTransposed)):
        torch.nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
        if m.bias is not None:
            torch.nn.init.constant_(m.bias, .)
    elif isinstance(m, nn.BatchNormd):
        torch.nn.init.constant_(m.weight, .)
        torch.nn.init.constant_(m.bias, .)
    elif isinstance(m, nn.Linear):
        torch.nn.init.xavier_uniform_(m.weight)
        if m.bias is not None:
            torch.nn.init.constant_(m.bias, .)


def _fix_nan_parameters(model):
    """修复NaN参数（拆分自repair_model_initialization）"""
    repair_count = 
    for _, param in model.named_parameters():
        if torch.isnan(param).any():
            torch.nn.init.normal_(param, mean=, std=.)
            repair_count += 
        param.data = torch.clamp(param.data, -., .)
    return repair_count


def _check_gradient_stats(param, _):
    """检查单个参数梯度（拆分自check_gradient_health）"""
    grad_norm = param.grad.norm().item()
    has_zero_grad = grad_norm < e-
    has_nan_inf = torch.isnan(param.grad).any() or torch.isinf(param.grad).any()

    if has_nan_inf:
        param.grad = torch.where(torch.isnan(param.grad) | torch.isinf(param.grad),
                                 torch.zeros_like(param.grad), param.grad)

    return grad_norm, has_zero_grad, has_nan_inf


def _normalize_image_array(arr):
    """归一化图像数组到-（拆分自图像保存逻辑）"""
     修复：先裁剪到-再归一化，避免负数影响
    arr = np.clip(arr, ., .)
    arr = arr - arr.min()
    arr = arr / (arr.max() + e-)
    arr = (arr  ).astype(np.uint)
    return arr


def _process_prediction_for_metrics(pred, hr):
    """处理预测结果用于指标计算（拆分自评估函数）"""
    pred_np = pred.detach().cpu()
    hr_np = hr.cpu()

     处理通道维度
    if pred_np.dim() ==  and pred_np.size() == :
        pred_np = pred_np.squeeze()
    if hr_np.dim() ==  and hr_np.size() == :
        hr_np = hr_np.squeeze()

     强制裁剪到-范围（修复数值异常）
    pred_np = torch.clamp(pred_np, ., .)
    hr_np = torch.clamp(hr_np, ., .)

    return pred_np, hr_np

 新增：强制图像归一化到-的工具函数


def _force_image_normalization(tensor):
    """强制将张量归一化到-范围（修复HR图像负均值/全黑）"""
     步骤：移除异常值（NaN/Inf）
    tensor = torch.where(torch.isnan(tensor) | torch.isinf(tensor), torch.zeros_like(tensor), tensor)
     步骤：归一化到-
    tensor_min = tensor.min(dim=-, keepdim=True)[].min(dim=-, keepdim=True)[]
    tensor_max = tensor.max(dim=-, keepdim=True)[].max(dim=-, keepdim=True)[]
     避免除以
    tensor_range = torch.clamp(tensor_max - tensor_min, min=e-)
    tensor = (tensor - tensor_min) / tensor_range
     步骤：最终裁剪
    tensor = torch.clamp(tensor, ., .)
    return tensor

 ============ 模型修复与梯度检查 ============


def repair_model_initialization(model):
    """修复模型初始化权重问题（降低圈复杂度）"""
    print("正在修复模型初始化...")
    model.apply(_init_layer_weights)

     检查并修复NaN参数
    repair_count = _fix_nan_parameters(model)
    if repair_count > :
        print(f"修复了 {repair_count} 个NaN参数")

    return model


def check_gradient_health(model, logger, writer, epoch, batch_idx):
    """检查梯度健康状况（重构后降低圈复杂度）"""
    total_params = 
    zero_grad_count = 
    nan_grad_count = 
    grad_norms = []

    for param_name, param in model.named_parameters():
        total_params += 
        if param.grad is None:
            logger.write(f"参数 {param_name} 无梯度（可能被冻结）")
            continue

        grad_norm, has_zero_grad, has_nan_inf = _check_gradient_stats(param, param_name)
        grad_norms.append(grad_norm)

        if has_zero_grad:
            zero_grad_count += 
            logger.write(f"警告: 参数 {param_name} 梯度接近零 (范数: {grad_norm:.e})")
        if has_nan_inf:
            nan_grad_count += 
            logger.write(f"严重: 参数 {param_name} 梯度包含NaN/Inf")

     记录梯度分布到TensorBoard
    if len(grad_norms) >  and writer is not None:
        global_step = epoch   + batch_idx
        writer.add_scalar("Gradient/mean_norm", np.mean(grad_norms), global_step)
        writer.add_scalar("Gradient/max_norm", np.max(grad_norms), global_step)
        writer.add_scalar("Gradient/zero_grad_ratio", zero_grad_count / total_params, global_step)
        writer.add_scalar("Gradient/nan_grad_count", nan_grad_count, global_step)

     汇总日志
    logger.write(f"\n梯度健康汇总: {zero_grad_count}/{total_params} 零梯度, {nan_grad_count} NaN/Inf梯度")
    return zero_grad_count, nan_grad_count


def emergency_model_repair(model, logger):
    """紧急修复NaN参数/梯度（简化逻辑）"""
    logger.write("执行紧急模型修复...")
    repair_count = 

    for param_name, param in model.named_parameters():
         修复NaN/Inf参数
        if torch.isnan(param).any() or torch.isinf(param).any():
            torch.nn.init.normal_(param, mean=, std=.)
            logger.write(f"修复参数: {param_name}")
            repair_count += 

         修复梯度
        if param.grad is not None:
            param.grad = torch.where(torch.isnan(param.grad) | torch.isinf(param.grad),
                                     torch.zeros_like(param.grad), param.grad)

    logger.write(f"完成 {repair_count} 处修复" if repair_count >  else "模型状态正常")
    return model


 ============ 数据健康检查 ============
def check_data_health(loader, config, logger=None, phase="train", check_batches=):
    """增强版数据健康检查（重构后降低圈复杂度）"""
    def safe_log(msg):
        if logger:
            logger.write(msg)
        else:
            print(msg)

    try:
        scale = config.get("dataset", {}).get("scale_factor", )
        batch_count = 

        for batch_idx, data in enumerate(loader):
            if batch_count >= check_batches:
                break
            batch_count += 

             鲁棒化解包
            if len(data) < :
                safe_log(f"[{phase}] 批次{batch_idx}数据格式错误，长度不足")
                continue
            lr, hr = data[:]

             核心修复：强制归一化（解决HR全黑/负均值）
            if config["dataset"]["force_normalize"]:
                lr = _force_image_normalization(lr)
                hr = _force_image_normalization(hr)

             基础校验
            lr, hr = _validate_data_tensor(lr, hr, phase, batch_idx, safe_log)
            if lr is None or hr is None:
                continue

             尺寸匹配检查
            _check_data_dimensions(lr, hr, scale, phase, batch_idx, safe_log)

        safe_log(f"[{phase}] 数据健康检查完成（检查前{check_batches}个批次）")

    except Exception as e:
        safe_log(f"[{phase}] 数据集加载失败: {e}")
        raise


def validate_dataset_samples(loader, config, logger, check_num=):
    """校验数据集样本是否正常（非全黑、尺寸匹配）"""
    logger.write("\n=== 数据集样本校验 ===")
    scale = config["dataset"]["scale_factor"]
    for batch_idx, data in enumerate(loader):
        if batch_idx >= check_num:
            break
        lr, hr = data[:]

         核心修复：强制归一化后再检查
        if config["dataset"]["force_normalize"]:
            lr = _force_image_normalization(lr)
            hr = _force_image_normalization(hr)

         检查：LR/HR尺寸是否匹配（HR = LR × scale）
        lr_h, lr_w = lr.shape[], lr.shape[]
        hr_h, hr_w = hr.shape[], hr.shape[]
        if hr_h != lr_h  scale or hr_w != lr_w  scale:
            logger.write(f" 批次{batch_idx}尺寸不匹配：LR({lr_h}x{lr_w}) → HR({hr_h}x{hr_w})")
        else:
            logger.write(f" 批次{batch_idx}尺寸匹配")

         检查：图像是否全黑（均值接近）- 修复阈值，避免误判
        lr_mean = lr.mean().item()
        hr_mean = hr.mean().item()
        if lr_mean < .:   降低阈值，更严格的全黑判断
            logger.write(f" 批次{batch_idx} LR全黑（均值：{lr_mean:.f}）")
        if hr_mean < .:
            logger.write(f" 批次{batch_idx} HR全黑（均值：{hr_mean:.f}）")
        else:
            logger.write(f" 批次{batch_idx} 图像均值正常：LR={lr_mean:.f}, HR={hr_mean:.f}")


def _validate_data_tensor(lr, hr, phase, batch_idx, safe_log):
    """验证数据张量（拆分自check_data_health）"""
     类型校验
    if not isinstance(lr, torch.Tensor):
        safe_log(f"[{phase}] 批次{batch_idx} LR不是Tensor，类型：{type(lr)}")
        return None, None
    if hr is not None and not isinstance(hr, torch.Tensor):
        safe_log(f"[{phase}] 批次{batch_idx} HR不是Tensor，类型：{type(hr)}")
        return None, None

     NaN/Inf检查和修复
    if torch.isnan(lr).any() or torch.isinf(lr).any():
        safe_log(f"[{phase}] 批次 {batch_idx} LR包含NaN/Inf！已修复")
        lr = torch.where(torch.isnan(lr) | torch.isinf(lr), torch.zeros_like(lr), lr)

    if hr is not None and (torch.isnan(hr).any() or torch.isinf(hr).any()):
        safe_log(f"[{phase}] 批次 {batch_idx} HR包含NaN/Inf！已修复")
        hr = torch.where(torch.isnan(hr) | torch.isinf(hr), torch.zeros_like(hr), hr)

     数值范围检查
    lr = _clip_tensor_range(lr, phase, batch_idx, "LR", safe_log)
    if hr is not None:
        hr = _clip_tensor_range(hr, phase, batch_idx, "HR", safe_log)

     维度校验
    if len(lr.shape) != :
        safe_log(f"[{phase}] 批次 {batch_idx} LR维度异常，应为维，实际：{lr.shape}")
        return None, None
    if hr is not None and len(hr.shape) != :
        safe_log(f"[{phase}] 批次 {batch_idx} HR维度异常，应为维，实际：{hr.shape}")
        return None, None

    return lr, hr


def _clip_tensor_range(tensor, phase, batch_idx, tensor_type, safe_log):
    """裁剪张量数值范围（拆分自check_data_health）"""
    t_min, t_max = tensor.min().item(), tensor.max().item()
    if t_min <  or t_max > :
        safe_log(f"[{phase}] 批次 {batch_idx} {tensor_type}数值范围异常: [{t_min:.f}, {t_max:.f}]，已裁剪")
        tensor = torch.clamp(tensor, ., .)
    return tensor


def _check_data_dimensions(lr, hr, scale, phase, batch_idx, safe_log):
    """检查数据维度匹配（拆分自check_data_health）"""
    lr_b, lr_c, lr_h, lr_w = lr.shape
    hr_b, hr_c, hr_h, hr_w = hr.shape

    if lr_b != hr_b:
        safe_log(f"[{phase}] 批次 {batch_idx} 批次大小不匹配：LR({lr_b}) vs HR({hr_b})")
    if lr_c != hr_c:
        safe_log(f"[{phase}] 批次 {batch_idx} 通道数不匹配：LR({lr_c}) vs HR({hr_c})")
    if hr_h != lr_h  scale or hr_w != lr_w  scale:
        safe_log(f"[{phase}] 批次 {batch_idx} 尺寸不匹配：LR({lr_h}x{lr_w}) → HR({hr_h}x{hr_w}) (缩放因子{scale})")


 ============ 工具类 ============
class AverageMeter:
    """修复参数不匹配问题的指标统计类"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 
        self.avg = 
        self.sum = 
        self.count = 
        self.history = []

    def update(self, val, n=):
        if np.isnan(val) or np.isinf(val):
            return
        self.val = val
        self.sum += val  n
        self.count += n
        self.avg = self.sum / self.count if self.count !=  else 
        self.history.append(val)

    def get_std(self):
        return np.std(self.history) if len(self.history) >  else 


class SuperEarlyStopping:
    """超强Early-Stopping机制（修复best_psnr=-inf问题）"""

    def __init__(self, patience=, min_delta=e-, min_improvement=.,
                 warmup_epochs=, strategy="composite", verbose=True, checkpoint_dir=""):
        self.patience = patience
        self.min_delta = min_delta
        self.min_improvement = min_improvement
        self.warmup_epochs = warmup_epochs
        self.strategy = strategy
        self.verbose = verbose
        self.checkpoint_dir = checkpoint_dir

         修复：初始化best_psnr为而不是-inf
        self.best_psnr = .
        self.best_ssim = -float("inf")
        self.best_loss = float("inf")
        self.best_composite_score = -float("inf")

         动态参数
        self.counter = 
        self.epochs_since_improvement = 
        self.lr_reduced = False
        self.early_stop = False
        self.best_epoch = 

         训练趋势分析
        self.psnr_history = []
        self.loss_history = []
        self.improvement_trend = []
        self.adaptive_patience = patience
        self.convergence_speed = .

         最佳模型路径
        self.best_model_path = os.path.join(checkpoint_dir, "best_model.pth")

        if verbose:
            print(f"Early-Stopping初始化: 策略={strategy}, 耐心值={patience}, 热启动={warmup_epochs}")

    def calculate_composite_score(self, psnr, ssim, loss):
        """计算综合评分"""
        psnr_norm = np.clip(psnr / ., , )
        ssim_norm = np.clip(ssim / ., , )
        loss_norm = np.clip(. / (loss + e-), , )
        return .  psnr_norm + .  ssim_norm + .  loss_norm

    def analyze_trend(self, current_psnr, current_loss):
        """分析训练趋势"""
        if len(self.psnr_history) < :
            return

        recent_psnr = self.psnr_history[-:]
        recent_loss = self.loss_history[-:]

        psnr_trend = (current_psnr - recent_psnr[]) / .
        loss_trend = (recent_loss[] - current_loss) / .
        trend_score = .  psnr_trend + .  loss_trend
        self.improvement_trend.append(trend_score)

         自适应耐心值
        if len(self.improvement_trend) >= :
            avg_trend = np.mean(self.improvement_trend[-:])
            if avg_trend > .:
                self.adaptive_patience = max(self.patience // , )
                self.convergence_speed = .
            elif avg_trend < -.:
                self.adaptive_patience = self.patience  
                self.convergence_speed = .
            else:
                self.adaptive_patience = int(self.patience  .)
                self.convergence_speed = .

    def _check_improvement(self, current_composite, psnr, loss):
        """检查是否有改进（拆分自should_stop）"""
        improvement_found = False

        if self.strategy == "composite":
            if current_composite > self.best_composite_score + self.min_delta:
                improvement_found = True
                self.best_composite_score = current_composite
                 修复：同步更新best_psnr
                self.best_psnr = psnr
        elif self.strategy == "psnr":
            if psnr > self.best_psnr + self.min_delta:
                improvement_found = True
                self.best_psnr = psnr
        elif self.strategy == "loss":
            if loss < self.best_loss - self.min_delta:
                improvement_found = True
                self.best_loss = loss
                 修复：loss改进时也更新best_psnr
                self.best_psnr = psnr
        elif self.strategy == "dynamic":
            if self.best_epoch < self.patience:
                if psnr > self.best_psnr + self.min_delta:
                    improvement_found = True
                    self.best_psnr = psnr
            else:
                if current_composite > self.best_composite_score + self.min_delta / :
                    improvement_found = True
                    self.best_composite_score = current_composite
                    self.best_psnr = psnr

        return improvement_found

    def _check_stop_conditions(self):
        """检查停止条件（拆分自should_stop）"""
        stop_reason = ""

         耐心值耗尽
        if self.counter >= self.adaptive_patience:
            self.early_stop = True
            stop_reason = f"patience_exceeded_{self.adaptive_patience}"
         性能下降
        elif len(self.psnr_history) > :
            recent_avg = np.mean(self.psnr_history[-:])
            previous_avg = np.mean(self.psnr_history[-:-])
            if recent_avg < previous_avg - self.min_improvement  .:
                self.early_stop = True
                stop_reason = "performance_degradation"
         收敛
        elif len(self.psnr_history) > :
            last__std = np.std(self.psnr_history[-:])
            if last__std < self.min_delta  :
                self.early_stop = True
                stop_reason = "converged"

        return stop_reason

    def should_stop(self, epoch, psnr, ssim, loss, model, optimizer, scheduler, logger):
        """判断是否停止训练（重构主逻辑）"""
         热启动阶段不触发
        if epoch < self.warmup_epochs:
            return False, ""

         更新历史记录
        self.psnr_history.append(psnr)
        self.loss_history.append(loss)
        self.analyze_trend(psnr, loss)

         计算综合评分
        current_composite = self.calculate_composite_score(psnr, ssim, loss)

         检查改进
        improvement_found = self._check_improvement(current_composite, psnr, loss)

         处理改进/无改进
        if improvement_found:
            self._handle_improvement(epoch, psnr, ssim, loss, model, optimizer, scheduler, logger)
        else:
            self._handle_no_improvement(optimizer, logger)

         检查停止条件
        stop_reason = self._check_stop_conditions()

        if self.early_stop and self.verbose:
            logger.write(f"Early Stopping触发! 原因: {stop_reason}")
            logger.write(f"最佳结果 - Epoch: {self.best_epoch}, PSNR: {self.best_psnr:.f}, SSIM: {self.best_ssim:.f}")

        return self.early_stop, stop_reason

    def _handle_improvement(self, epoch, psnr, ssim, loss, model, optimizer, scheduler, logger):
        """处理改进情况"""
        self.counter = 
        self.epochs_since_improvement = 
        self.best_epoch = epoch
        self.best_ssim = ssim
         修复：确保best_psnr正确更新
        if psnr > self.best_psnr:
            self.best_psnr = psnr
        self.save_best_model(model, optimizer, scheduler, epoch, psnr, ssim, loss)
        if self.verbose:
            logger.write(f"发现改进! Epoch {epoch}: PSNR={psnr:.f}, SSIM={ssim:.f}, Loss={loss:.f}")

    def _handle_no_improvement(self, optimizer, logger):
        """处理无改进情况"""
        self.counter += 
        self.epochs_since_improvement += 

         学习率衰减
        if self.epochs_since_improvement > self.adaptive_patience //  and not self.lr_reduced:
            self.reduce_learning_rate(optimizer, logger)
            self.lr_reduced = True

    def reduce_learning_rate(self, optimizer, logger, decay_rate=.):
        """衰减学习率"""
        if not optimizer.param_groups:
            logger.write("错误：优化器无参数组")
            return
        original_lr = optimizer.param_groups[]["lr"]
        new_lr = original_lr  decay_rate
        new_lr = max(new_lr, e-)

        for param_group in optimizer.param_groups:
            param_group["lr"] = new_lr

        logger.write(f"学习率衰减: {original_lr:.e} → {new_lr:.e} (衰减率{decay_rate})")

    def save_best_model(self, model, optimizer, scheduler, epoch, psnr, ssim, loss):
        """保存最佳模型检查点"""
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

    def load_best_model(self, model, optimizer=None, scheduler=None):
        """加载最佳模型"""
        if os.path.exists(self.best_model_path):
            try:
                checkpoint = torch.load(self.best_model_path, map_location=config["device"], weights_only=False)
                state_dict = {k.replace('module.', ''): v for k, v in checkpoint["model_state_dict"].items()}
                model.load_state_dict(state_dict)
                if optimizer and "optimizer_state_dict" in checkpoint:
                    optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
                if scheduler and "scheduler_state_dict" in checkpoint:
                    scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
                 修复：加载后同步best_psnr
                self.best_psnr = checkpoint.get("best_psnr", .)
                self.best_epoch = checkpoint.get("epoch", )
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


 ============ 目录/检查点/日志管理 ============
def init_directories():
    """初始化输出目录"""
    dirs = [
        config["output_path"],
        os.path.join(config["output_path"], "ckp"),
        os.path.join(config["output_path"], "val_inference"),
        os.path.join(config["output_path"], "test_inference"),
        os.path.join(config["output_path"], "logs"),
        config["tb_log_dir"],
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def find_latest_checkpoint(ckp_dir):
    """查找最新检查点"""
    checkpoint_files = glob.glob(os.path.join(ckp_dir, "epoch_.pth"))
    if not checkpoint_files:
        return None

    def get_epoch(file_path):
        return int(os.path.basename(file_path).split("_")[].split(".")[])
    checkpoint_files.sort(key=get_epoch, reverse=True)
    return checkpoint_files[]


def clean_old_checkpoints(ckp_dir, keep_num):
    """清理旧检查点"""
    checkpoint_files = glob.glob(os.path.join(ckp_dir, "epoch_.pth"))
    if len(checkpoint_files) <= keep_num:
        return

    def get_epoch(file_path):
        return int(os.path.basename(file_path).split("_")[].split(".")[])
    checkpoint_files.sort(key=get_epoch)
    for file in checkpoint_files[:-keep_num]:
        try:
            os.remove(file)
            print(f"清理旧检查点: {file}")
        except Exception as e:
            print(f"清理检查点失败 {file}: {e}")


 单例日志器
_logger_instance = None


def get_logger():
    """获取单例日志器"""
    global _logger_instance
    if _logger_instance is not None:
        return _logger_instance

    log_dir = os.path.join(config["output_path"], "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

    class Logger:
        def __init__(self, log_file):
            self.log_file = log_file
            with open(self.log_file, "w", encoding="utf-") as f:
                f.write(f"日志开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        def write(self, message):
            """写入控制台+文件"""
            print(message)
            with open(self.log_file, "a", encoding="utf-") as f:
                f.write(message + "\n")

    _logger_instance = Logger(log_file)
    return _logger_instance


def safe_log(msg):
    """安全日志函数"""
    try:
        logger = get_logger()
        logger.write(msg)
    except Exception as e:
        print(f"日志写入失败: {e} | 消息: {msg}")


 ============ 模型初始化与检查点加载 ============
def init_model():
    """初始化模型"""
    from model import LUMWCNN
    model = LUMWCNN().to(config["device"])
    model = repair_model_initialization(model)

     多卡训练支持
    if torch.cuda.device_count() > :
        model = nn.DataParallel(model)
        print(f"使用 {torch.cuda.device_count()} 张GPU训练")
    return model


def load_checkpoint(model, optimizer, scheduler, ckp_path):
    """加载检查点"""
    try:
        checkpoint = torch.load(ckp_path, map_location=config["device"], weights_only=False)
        state_dict = {k.replace('module.', ''): v for k, v in checkpoint["model_state_dict"].items()}
        model.load_state_dict(state_dict)
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        start_epoch = checkpoint["epoch"] + 
        print(f"从检查点 {ckp_path} 恢复，起始Epoch: {start_epoch}")
        return start_epoch
    except Exception as e:
        print(f"检查点加载失败: {e}")
        raise


 ============ 混合损失函数 ============
class MixedLoss(nn.Module):
    """L+MSE混合损失函数"""

    def __init__(self, l_weight=., mse_weight=.):
        super(MixedLoss, self).__init__()
        self.l = nn.LLoss()
        self.mse = nn.MSELoss()
        self.l_weight = l_weight
        self.mse_weight = mse_weight

    def forward(self, pred, target):
         强制裁剪，确保损失计算在正确范围
        pred = torch.clamp(pred, ., .)
        target = torch.clamp(target, ., .)
        loss = self.l_weight  self.l(pred, target) + self.mse_weight  self.mse(pred, target)
        return loss


 ============ 验证/测试集评估 ============
def _save_evaluation_images(pred_img, lr_img, hr_img, save_path, prefix):
    """保存评估图像（拆分自evaluate_val_set）"""
     归一化并保存
    pred_arr = _normalize_image_array(pred_img)
    lr_arr = _normalize_image_array(lr_img)
    hr_arr = _normalize_image_array(hr_img)

    Image.fromarray(pred_arr, mode="L").save(os.path.join(save_path, f"{prefix}_pred.png"))
    Image.fromarray(lr_arr, mode="L").save(os.path.join(save_path, f"{prefix}_lr.png"))
    Image.fromarray(hr_arr, mode="L").save(os.path.join(save_path, f"{prefix}_hr.png"))


def evaluate_val_set(model, val_loader, criterion, epoch, logger, writer, save_images=False):
    """验证集评估（重构降低圈复杂度）"""
    logger.write(f"\n开始Epoch {epoch} 验证集评估")
    model.eval()
    val_psnr = AverageMeter()
    val_ssim = AverageMeter()
    val_loss = AverageMeter()
    pin_memory = config["device"].startswith("cuda")

    with torch.no_grad():
        for batch_idx, data in enumerate(tqdm(val_loader, desc="Validating")):
            try:
                if len(data) < :
                    logger.write(f"验证批次{batch_idx}数据格式错误，跳过")
                    continue

                lr, hr = data[:]
                 核心修复：验证集也强制归一化
                if config["dataset"]["force_normalize"]:
                    lr = _force_image_normalization(lr)
                    hr = _force_image_normalization(hr)

                lr = lr.to(config["device"], non_blocking=pin_memory)
                hr = hr.to(config["device"], non_blocking=pin_memory)

                 推理与损失计算
                predict = model(lr)
                predict = torch.clamp(predict, ., .)
                loss = criterion(predict, hr)

                 指标计算
                predict_np, hr_np = _process_prediction_for_metrics(predict, hr)
                psnr = calc_psnr_torch(predict_np.float(), hr_np.float())
                ssim = calc_ssim_torch(predict_np.float(), hr_np.float())

                 更新指标
                val_psnr.update(psnr, n=lr.size())
                val_ssim.update(ssim, n=lr.size())
                val_loss.update(loss.item(), n=lr.size())

                 保存验证图像
                if save_images and batch_idx < :
                    val_inf_dir = os.path.join(config["output_path"], "val_inference", f"epoch_{epoch}")
                    os.makedirs(val_inf_dir, exist_ok=True)

                     处理单张图像
                    pred_img = predict_np[].cpu().numpy()
                    lr_img = lr[].squeeze().cpu().numpy()
                    hr_img = hr_np[].cpu().numpy()

                    _save_evaluation_images(pred_img, lr_img, hr_img, val_inf_dir, f"batch_{batch_idx}")

            except Exception as e:
                logger.write(f"验证批次{batch_idx}处理失败: {e}")
                continue

     记录验证结果到TensorBoard
    if writer is not None:
        writer.add_scalar("Validation/Loss", val_loss.avg, epoch)
        writer.add_scalar("Validation/PSNR", val_psnr.avg, epoch)
        writer.add_scalar("Validation/SSIM", val_ssim.avg, epoch)
        writer.add_scalar("Validation/PSNR_std", val_psnr.get_std(), epoch)
        writer.add_scalar("Validation/Loss_std", val_loss.get_std(), epoch)

     记录验证结果
    logger.write(f"验证集结果 - Epoch {epoch}:")
    logger.write(f"  PSNR: {val_psnr.avg:.f} dB, SSIM: {val_ssim.avg:.f}, Loss: {val_loss.avg:.f}")
    model.train()
    return val_psnr.avg, val_ssim.avg, val_loss.avg


def evaluate_test_set(model, logger, writer, save_images=False):
    """测试集评估（重构降低圈复杂度）"""
    logger.write("\n" + "="  )
    logger.write("开始测试集评估")
    logger.write("="  )

     加载测试集
    test_loader = _load_test_dataset(logger)
    if test_loader is None:
        return None

     初始化指标和损失函数
    criterion = _get_loss_function()

     执行测试评估
    test_results = _run_test_evaluation(model, test_loader, criterion, logger, writer, save_images)

     记录结果
    _log_test_results(test_results, logger, writer)
    model.train()
    return test_results


def _load_test_dataset(logger):
    """加载测试数据集（拆分自evaluate_test_set）"""
    try:
         动态导入数据集模块（修复未使用变量警告）
        module_name, class_name = config["dataset"]["interface"].split(".")
        dataset_module = importlib.import_module(f"base.datasets.{module_name}")
        DatasetClass = getattr(dataset_module, class_name)

        pin_memory = config["device"].startswith("cuda")
        num_workers = config["num_workers"] //  if pin_memory else 

        test_set = DatasetClass(
            hr_dir=config["dataset"]["test_hr_dir"],
            crop_size=config["dataset"]["crop_size"],
            scale_factor=config["dataset"]["scale_factor"],
            noise_std=config["dataset"]["noise_std"],
            phase="test",
            augment=False,
        )
        test_loader = DataLoader(
            test_set,
            batch_size=,
            shuffle=False,
            pin_memory=pin_memory,
            collate_fn=deeplesion_collate_fn,
            num_workers=num_workers,
        )
        logger.write(f"测试集大小: {len(test_set)}")

         数据健康检查（包含强制归一化）
        check_data_health(test_loader, config, logger, "test", check_batches=)
        validate_dataset_samples(test_loader, config, logger)
        return test_loader

    except Exception as e:
        logger.write(f"测试集加载失败: {e}")
        return None


def _get_loss_function():
    """获取损失函数（拆分自evaluate_test_set）"""
    if config["loss"]["use_mixed_loss"]:
        return MixedLoss(l_weight=config["loss"]["l_weight"], mse_weight=config["loss"]["mse_weight"])
    else:
        return nn.MSELoss()


def _run_test_evaluation(model, test_loader, criterion, logger, writer, save_images):
    """执行测试评估（拆分自evaluate_test_set）"""
    test_psnr = AverageMeter()
    test_ssim = AverageMeter()
    test_loss = AverageMeter()

    pin_memory = config["device"].startswith("cuda")
    test_start = time.time()
    test_inf_dir = os.path.join(config["output_path"], "test_inference")
    os.makedirs(test_inf_dir, exist_ok=True)

    model.eval()
    with torch.no_grad():
        for batch_idx, data in enumerate(tqdm(test_loader, desc="Testing")):
            try:
                 解包数据
                lr, hr, filename = (data + [f"batch_{batch_idx}"])[:]
                filename = filename[] if isinstance(filename, (list, tuple)) else filename

                 核心修复：测试集强制归一化
                if config["dataset"]["force_normalize"]:
                    lr = _force_image_normalization(lr)
                    hr = _force_image_normalization(hr)

                 设备迁移
                lr = lr.to(config["device"], non_blocking=pin_memory)
                hr = hr.to(config["device"], non_blocking=pin_memory)

                 推理与损失
                predict = model(lr)
                predict = torch.clamp(predict, ., .)
                loss = criterion(predict, hr)

                 指标计算
                predict_np, hr_np = _process_prediction_for_metrics(predict, hr)
                psnr = calc_psnr_torch(predict_np.float(), hr_np.float())
                ssim = calc_ssim_torch(predict_np.float(), hr_np.float())

                 更新指标
                test_psnr.update(psnr, n=lr.size())
                test_ssim.update(ssim, n=lr.size())
                test_loss.update(loss.item(), n=lr.size())

                 保存测试图像
                if save_images:
                    pred_img = predict_np[].cpu().numpy()
                    lr_img = lr[].squeeze().cpu().numpy()
                    hr_img = hr_np[].cpu().numpy()
                    _save_evaluation_images(pred_img, lr_img, hr_img, test_inf_dir, filename)

            except Exception as e:
                logger.write(f"测试批次{batch_idx}处理失败: {e}")
                continue

    test_time = time.time() - test_start
    return {
        "psnr": test_psnr.avg,
        "ssim": test_ssim.avg,
        "loss": test_loss.avg,
        "psnr_std": test_psnr.get_std(),
        "ssim_std": test_ssim.get_std(),
        "test_time": test_time,
        "num_samples": test_psnr.count
    }


def _log_test_results(test_results, logger, writer):
    """记录测试结果（拆分自evaluate_test_set）"""
    if test_results is None:
        logger.write("测试集评估失败，无结果可记录")
        return

     记录到日志
    logger.write("\n=== 测试集最终结果 ===")
    logger.write(f"PSNR: {test_results['psnr']:.f} dB (±{test_results['psnr_std']:.f})")
    logger.write(f"SSIM: {test_results['ssim']:.f} (±{test_results['ssim_std']:.f})")
    logger.write(f"Loss: {test_results['loss']:.f}")
    logger.write(f"测试耗时: {test_results['test_time']:.f} 秒 (共{test_results['num_samples']}个样本)")

     记录到TensorBoard
    if writer is not None:
        writer.add_scalar("Test/PSNR", test_results['psnr'], )
        writer.add_scalar("Test/SSIM", test_results['ssim'], )
        writer.add_scalar("Test/Loss", test_results['loss'], )
        writer.add_scalar("Test/Test_Time", test_results['test_time'], )


 ============ 训练核心逻辑 ============
def _init_optimizer(model):
    """初始化优化器（拆分自train函数，降低圈复杂度）"""
    optimizer = optim.AdamW(
        model.parameters(),
        lr=config["lr"],
        betas=(., .),
        eps=e-,
        weight_decay=e-
    )
    return optimizer


def _init_scheduler(optimizer):
    """初始化学习率调度器（拆分自train函数，降低圈复杂度）"""
     基础调度器
    scheduler = lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=config["epochs"],
        eta_min=e-
    )
     Warmup调度器

    def warmup_lr(epoch):
        if epoch < config["warmup_epochs"]:
            return (config["warmup_lr_end"] - config["warmup_lr_start"]) / config["warmup_epochs"]  epoch + config["warmup_lr_start"]
        else:
            return scheduler.get_lr()[]

    warmup_scheduler = lr_scheduler.LambdaLR(optimizer, lr_lambda=warmup_lr)
    return warmup_scheduler


def _train_one_epoch(model, train_loader, criterion, optimizer, epoch, logger, writer):
    """训练单个Epoch（拆分自train函数，降低圈复杂度）"""
    model.train()
    train_loss = AverageMeter()
    train_psnr = AverageMeter()
    pin_memory = config["device"].startswith("cuda")

    pbar = tqdm(enumerate(train_loader), total=len(train_loader), desc=f"Epoch {epoch} Training")
    for batch_idx, data in pbar:
        try:
             解包数据
            if len(data) < :
                logger.write(f"训练批次{batch_idx}数据格式错误，跳过")
                continue
            lr, hr = data[:]

             强制归一化
            if config["dataset"]["force_normalize"]:
                lr = _force_image_normalization(lr)
                hr = _force_image_normalization(hr)

             设备迁移
            lr = lr.to(config["device"], non_blocking=pin_memory)
            hr = hr.to(config["device"], non_blocking=pin_memory)

             前向传播
            optimizer.zero_grad()
            pred = model(lr)
            pred = torch.clamp(pred, ., .)
            loss = criterion(pred, hr)

             反向传播
            loss.backward()

             梯度裁剪
            torch.nn.utils.clip_grad_norm_(model.parameters(), config["grad_clip_norm"])

             梯度健康检查
            if batch_idx % config["gradient_check_interval"] == :
                check_gradient_health(model, logger, writer, epoch, batch_idx)

             优化器步进
            optimizer.step()

             计算训练集PSNR（用于监控）
            pred_np, hr_np = _process_prediction_for_metrics(pred, hr)
            psnr = calc_psnr_torch(pred_np.float(), hr_np.float())

             更新指标
            train_loss.update(loss.item(), n=lr.size())
            train_psnr.update(psnr, n=lr.size())

             更新进度条
            pbar.set_postfix({
                "Loss": f"{train_loss.avg:.f}",
                "PSNR": f"{train_psnr.avg:.f}",
                "LR": f"{optimizer.param_groups[]['lr']:.e}"
            })

             紧急修复NaN参数
            if torch.isnan(loss):
                logger.write(f"Epoch {epoch} Batch {batch_idx} 损失为NaN，执行紧急修复")
                emergency_model_repair(model, logger)
                continue

        except Exception as e:
            logger.write(f"训练批次{batch_idx}失败: {e}")
            continue

     记录训练指标到TensorBoard
    if writer is not None:
        writer.add_scalar("Training/Loss", train_loss.avg, epoch)
        writer.add_scalar("Training/PSNR", train_psnr.avg, epoch)
        writer.add_scalar("Training/Learning_Rate", optimizer.param_groups[]['lr'], epoch)

    logger.write(f"Epoch {epoch} 训练完成 - Loss: {train_loss.avg:.f}, PSNR: {train_psnr.avg:.f}")
    return train_loss.avg, train_psnr.avg


def train():
    """核心训练函数（重构后降低圈复杂度）"""
     初始化目录和日志
    init_directories()
    logger = get_logger()
    writer = SummaryWriter(log_dir=config["tb_log_dir"])

     初始化数据集
    logger.write("\n=== 加载训练数据集 ===")
    try:
        module_name, class_name = config["dataset"]["interface"].split(".")
        dataset_module = importlib.import_module(f"base.datasets.{module_name}")
        DatasetClass = getattr(dataset_module, class_name)

         训练集
        train_set = DatasetClass(
            hr_dir=config["dataset"]["train_hr_dir"],
            crop_size=config["dataset"]["crop_size"],
            scale_factor=config["dataset"]["scale_factor"],
            noise_std=config["dataset"]["noise_std"],
            phase="train",
            augment=config["dataset"]["augment"],
        )
        train_loader = DataLoader(
            train_set,
            batch_size=config["batch_size"],
            shuffle=True,
            pin_memory=config["device"].startswith("cuda"),
            num_workers=config["num_workers"],
            collate_fn=deeplesion_collate_fn,
            drop_last=True
        )

         验证集
        val_set = DatasetClass(
            hr_dir=config["dataset"]["val_hr_dir"],
            crop_size=config["dataset"]["crop_size"],
            scale_factor=config["dataset"]["scale_factor"],
            noise_std=config["dataset"]["noise_std"],
            phase="val",
            augment=False,
        )
        val_loader = DataLoader(
            val_set,
            batch_size=config["batch_size"],
            shuffle=False,
            pin_memory=config["device"].startswith("cuda"),
            num_workers=config["num_workers"] // ,
            collate_fn=deeplesion_collate_fn
        )

         数据健康检查
        check_data_health(train_loader, config, logger, "train")
        check_data_health(val_loader, config, logger, "val")
        validate_dataset_samples(train_loader, config, logger)

    except Exception as e:
        logger.write(f"数据集加载失败: {e}")
        return

     初始化模型、优化器、调度器
    logger.write("\n=== 初始化模型 ===")
    model = init_model()
    criterion = MixedLoss(
        l_weight=config["loss"]["l_weight"],
        mse_weight=config["loss"]["mse_weight"]
    ) if config["loss"]["use_mixed_loss"] else nn.MSELoss()
    optimizer = _init_optimizer(model)
    scheduler = _init_scheduler(optimizer)

     加载最新检查点
    start_epoch = 
    ckp_dir = os.path.join(config["output_path"], "ckp")
    latest_ckp = find_latest_checkpoint(ckp_dir)
    if latest_ckp:
        start_epoch = load_checkpoint(model, optimizer, scheduler, latest_ckp)

     初始化早停
    early_stopping = SuperEarlyStopping(
        patience=config["early_stopping"]["patience"],
        min_delta=config["early_stopping"]["min_delta"],
        min_improvement=config["early_stopping"]["min_improvement"],
        warmup_epochs=config["early_stopping"]["warmup_epochs"],
        strategy=config["early_stopping"]["strategy"],
        checkpoint_dir=ckp_dir
    )

     训练信息记录
    log_path = logger.log_file   定义log_path变量
    logger.write(f"\n=== 训练配置 ===")
    logger.write(f"日志文件: {log_path}")
    logger.write(f"学习率: {config['lr']}")
    logger.write(f"批次大小: {config['batch_size']}")
    logger.write(f"最大Epoch: {config['epochs']}")
    logger.write(f"缩放因子: {config['dataset']['scale_factor']}")
    logger.write(f"裁剪尺寸: {config['dataset']['crop_size']}")
    logger.write(f"噪声标准差: {config['dataset']['noise_std']}")
    logger.write(f"混合损失权重 (L/MSE): {config['loss']['l_weight']}/{config['loss']['mse_weight']}")

     开始训练
    logger.write("\n=== 开始训练 ===")
    best_val_psnr = .
    val_loss = AverageMeter()   初始化val_loss，避免未绑定错误

    for epoch in range(start_epoch, config["epochs"]):
         训练一个Epoch
        train_loss, train_psnr = _train_one_epoch(model, train_loader, criterion, optimizer, epoch, logger, writer)

         验证
        val_psnr, val_ssim, val_loss_avg = ., ., .
        if epoch % config["val_every"] ==  or epoch == config["epochs"] - :
            val_psnr, val_ssim, val_loss_avg = evaluate_val_set(model, val_loader, criterion, epoch, logger, writer, save_images=True)
            val_loss.update(val_loss_avg)   更新val_loss指标

         学习率调度
        scheduler.step()

         保存检查点
        if epoch %  ==  or epoch == config["epochs"] - :
            ckp_path = os.path.join(ckp_dir, f"epoch_{epoch}.pth")
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "scheduler_state_dict": scheduler.state_dict(),
                "train_loss": train_loss,
                "val_psnr": val_psnr,
                "val_loss": val_loss_avg,
            }, ckp_path)
            clean_old_checkpoints(ckp_dir, config["keep_checkpoints"])

         早停判断
        metrics = {   定义metrics变量
            "train_loss": train_loss,
            "train_psnr": train_psnr,
            "val_psnr": val_psnr,
            "val_ssim": val_ssim,
            "val_loss": val_loss_avg
        }
        early_stop, stop_reason = early_stopping.should_stop(epoch, val_psnr, val_ssim, val_loss_avg, model, optimizer, scheduler, logger)
        logger.write(f"早停状态: {early_stop}, 原因: {stop_reason}")   使用stop_reason变量

         更新最佳PSNR
        if val_psnr > best_val_psnr:
            best_val_psnr = val_psnr
            logger.write(f"更新最佳验证集PSNR: {best_val_psnr:.f} (Epoch {epoch})")

         触发早停
        if early_stop:
            logger.write(f"早停触发，终止训练 (Epoch {epoch})")
            break

     加载最佳模型并测试
    logger.write("\n=== 训练完成，加载最佳模型 ===")
    early_stopping.load_best_model(model)
    evaluate_test_set(model, logger, writer, save_images=True)

     关闭TensorBoard writer
    writer.close()
    logger.write("\n=== 训练流程全部完成 ===")


 主函数入口
if __name__ == "__main__":
    train()
