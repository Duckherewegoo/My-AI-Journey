"""
LU-MWCNN 训练代码 @ DeepLesion (修复版)
修复点：解决 AverageMeter.update() 参数不匹配问题，增强类型兼容性
新增：超强Early-Stopping机制
新增：测试集评估环节
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
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter


 从 utils 导入所需工具（若不存在请确保实现）
 这里补充完整 AverageMeter 类的正确实现，避免参数错误


class AverageMeter:
    """计算并存储平均值和当前值的工具类（修复参数匹配问题）"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.val =    当前值
        self.avg =    平均值
        self.sum =    总和
        self.count =    计数

    def update(self, val, n=):
        """
        更新指标
        :param val: 当前批次的指标值
        :param n: 批次大小（默认）
        """
        self.val = val
        self.sum += val  n
        self.count += n
        self.avg = self.sum / self.count   计算平均值


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
        """降低学习率"""
        for param_group in optimizer.param_groups:
            param_group["lr"] = .
        if self.verbose:
            logger.write(f"学习率衰减: {param_group['lr']:.e}")

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


 配置参数 - 集中管理可配置项
config = {
     训练参数（针对RTX  Mobile优化）
    "lr": e-,
    "epochs": ,
    "batch_size": ,    Mobile显存有限，降低批次大小避免溢出
    "val_every": ,
    "num_workers": min(os.cpu_count(), ),   根据CPU核心数自动调整，避免内存占用过高
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
    "output_path": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/nova/lu_mwcnn/output_deeplesion",
     数据集配置 - 更新为HR/LR结构
    "dataset": {
        "train_hr_dir": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/train/HR",
        "train_lr_dir": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/train/LR",
        "val_hr_dir": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/val/HR",
        "val_lr_dir": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/val/LR",
        "test_hr_dir": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/test/HR",
        "test_lr_dir": r"/home/dake/Documents/Projects/Station/Clone/gpm_only_for_study/datasets/Key_slices_opt/test/LR",
        "interface": "deeplesion.DeepLesionDataset",
        "crop_size": ,
        "scale_factor": ,   超分辨率缩放因子
    },
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


def get_logger():
    """创建日志记录器"""
    log_file = os.path.join(
        config["output_path"],
        "logs",
        f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
    )

    class Logger:
        def __init__(self, log_file):
            self.log_file = log_file

        def write(self, message):
            """同时写入控制台和日志文件"""
            print(message)
            with open(self.log_file, "a", encoding="utf-") as f:
                f.write(message + "\n")

    return Logger(log_file)


 模型初始化与恢复


def init_model():
    """初始化模型并尝试从检查点恢复"""
     假设 LUMWCNN 是已定义的模型类
    from model import LUMWCNN   显式导入模型，避免类型错误

    model = LUMWCNN().to(config["device"])

     支持多卡训练（如果有多个GPU）
    if torch.cuda.device_count() > :
        model = nn.DataParallel(model)
        print(f"使用 {torch.cuda.device_count()} 张GPU进行训练")

    return model


def load_checkpoint(model, optimizer, scheduler, ckp_path):
    try:
        checkpoint = safe_torch_load(ckp_path, config["device"])
        model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        start_epoch = checkpoint["epoch"] + 
        print(f"成功从 {ckp_path} 恢复，将从epoch {start_epoch} 开始训练")
        return start_epoch
    except Exception as e:
        print(f"检查点加载失败: {e}")
        raise   加载失败时终止训练


 测试集评估函数


def evaluate_test_set(model, logger, save_images=False):
    """
    在测试集上评估模型性能
    参数:
        model: 训练好的模型
        logger: 日志记录器
        save_images: 是否保存推理图像
    """
    logger.write("\n" + "="  )
    logger.write("开始测试集评估")
    logger.write("="  )

     加载测试数据集
    try:
        dataset_module = importlib.import_module(
            "." + config["dataset"]["interface"].split(".")[], "datasets"
        )
        DatasetClass = eval(
            f"dataset_module.{config['dataset']['interface'].split('.')[]}"
        )

        test_set = DatasetClass(
            hr_dir=config["dataset"]["test_hr_dir"],
            lr_dir=config["dataset"]["test_lr_dir"],
            crop_size=config["dataset"]["crop_size"],
            scale_factor=config["dataset"]["scale_factor"],
            phase="test",   测试模式
        )
        test_loader = DataLoader(
            test_set,
            batch_size=,   测试时批次大小为
            shuffle=False,
            pin_memory=True,
            num_workers=config["num_workers"] // ,
        )
    except Exception as e:
        logger.write(f"测试集加载失败: {e}")
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

     测试推理
    with torch.no_grad():
        for data in tqdm(test_loader, ncols=, desc="Testing"):
            filename = ["unknown"]
            try:
                lr, hr, filename = data
                lr = lr.to(config["device"], non_blocking=True)
                hr = hr.to(config["device"], non_blocking=True)

                 模型推理
                predict = model(lr)
                loss = criterion(predict, hr)

                 数据处理
                predict = predict.detach().cpu().clamp(, ).squeeze()
                hr_np = hr.squeeze().cpu()

                 计算指标
                from utils.metrics import calc_psnr_torch, calc_ssim_torch

                psnr = calc_psnr_torch(predict, hr_np)
                ssim = calc_ssim_torch(predict, hr_np)

                 更新指标
                test_psnr.update(psnr)
                test_ssim.update(ssim)
                test_loss.update(loss.item())

                 保存测试结果图像（可选）
                if save_images:
                    predict_y = np.array(predict.numpy()  , dtype=np.uint)
                    predict_gray = Image.fromarray(predict_y, mode="L")

                     保存预测结果
                    base_name = filename[]
                    pred_filename = base_name + "_pred.png"
                    pred_path = os.path.join(test_inference_dir, pred_filename)
                    predict_gray.save(pred_path)

                     保存输入图
                    lr_array = lr.detach().cpu().numpy()
                    lr_squeezed = lr_array.squeeze()
                    lr_scaled = lr_squeezed  
                    lr_y = np.array(lr_scaled, dtype=np.uint)
                    lr_filename = base_name + "_lr.png"
                    lr_path = os.path.join(test_inference_dir, lr_filename)
                    Image.fromarray(lr_y, mode="L").save(lr_path)

                     保存参考图
                    hr_array = hr_np.numpy()
                    hr_scaled = hr_array  
                    hr_y = np.array(hr_scaled, dtype=np.uint)
                    hr_filename = base_name + "_hr.png"
                    hr_path = os.path.join(test_inference_dir, hr_filename)
                    Image.fromarray(hr_y, mode="L").save(hr_path)
            except Exception as e:
                logger.write(f"测试样本 {filename[]} 处理失败: {e}")
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
    optimizer = optim.Adam(
        model.parameters(),
        lr=config["lr"],
        weight_decay=e-,
        betas=(., .),
        eps=e-,
    )
    scheduler = lr_scheduler.MultiStepLR(
        optimizer, list(range(, config["epochs"], )), gamma=.
    )

     加载数据集 - 适配HR/LR结构
    try:
        logger.write(f"加载数据集: {config['dataset']['interface']}")
        dataset_module = importlib.import_module(
            "." + config["dataset"]["interface"].split(".")[], "datasets"
        )
        DatasetClass = eval(
            f"dataset_module.{config['dataset']['interface'].split('.')[]}"
        )

         训练集
         修改后（使用正确的参数名和关键字参数）：
        train_set = DatasetClass(
            hr_dir=config["dataset"]["train_hr_dir"],
            lr_dir=config["dataset"]["train_lr_dir"],
            crop_size=config["dataset"]["crop_size"],
            phase="train",   使用 phase 而不是 mode
            scale_factor=config["dataset"]["scale_factor"],
        )
        train_loader = DataLoader(
            train_set,
            batch_size=config["batch_size"],
            shuffle=True,
            num_workers=config["num_workers"],
            pin_memory=True,
            drop_last=True,   避免最后一个批次尺寸不一致
        )

         验证集
        val_set = DatasetClass(
            hr_dir=config["dataset"]["val_hr_dir"],
            lr_dir=config["dataset"]["val_lr_dir"],
            crop_size=config["dataset"]["crop_size"],
            scale_factor=config["dataset"]["scale_factor"],
            phase="val",
        )
        val_loader = DataLoader(
            val_set,
            batch_size=,
            shuffle=False,
            pin_memory=True,
            num_workers=config["num_workers"] // ,   验证时减少worker
        )

        logger.write(f"训练集大小: {len(train_set)}")
        logger.write(f"验证集大小: {len(val_set)}")

    except Exception as e:
        logger.write(f"数据集加载失败: {e}")
        return

     初始化TensorBoard
    tb_writer = SummaryWriter(os.path.join(config["output_path"], "tensorboard"))

     检查断点续传
    ckp_dir = os.path.join(config["output_path"], "ckp")
    latest_ckp = find_latest_checkpoint(ckp_dir)
    start_epoch = 
    if latest_ckp:
        start_epoch = load_checkpoint(model, optimizer, scheduler, latest_ckp)
    epoch = start_epoch - 

     训练主循环
    try:
        for epoch in range(start_epoch, config["epochs"]):
            epoch_start_time = time.time()
            model.train()
            epoch_loss = AverageMeter()   使用修复后的AverageMeter

             训练阶段
            with tqdm(
                total=len(train_loader)  config["batch_size"],
                ncols=,
                desc=f'Training Epoch {epoch + }/{config["epochs"]}',
            ) as t:

                for batch_idx, data in enumerate(train_loader):
                    try:
                        lr, hr = data
                        lr = lr.to(config["device"], non_blocking=True)
                        hr = hr.to(config["device"], non_blocking=True)

                         前向传播
                        predict = model(lr)
                        loss = criterion(predict, hr)

                         反向传播
                        optimizer.zero_grad(set_to_none=True)   更高效的梯度清零
                        loss.backward()
                        optimizer.step()

                         更新 metrics（修复参数传递：val=loss.item(), n=当前批次大小）
                        batch_size = lr.size()
                        epoch_loss.update(val=loss.item(), n=batch_size)

                         更新进度条（修复tqdm参数格式）
                        t.set_postfix(
                            {
                                "loss": f"{epoch_loss.avg:.f}",
                                "lr": f'{optimizer.param_groups[]["lr"]:.f}',
                            }
                        )
                        t.update(batch_size)   按实际批次大小更新进度

                         每个批次记录一次中间损失
                        if batch_idx %  == :
                            tb_writer.add_scalar(
                                "Train/Batch Loss",
                                loss.item(),
                                epoch  len(train_loader) + batch_idx,
                            )
                    except Exception as e:
                        logger.write(f"批次 {batch_idx} 处理失败: {e}")
                        continue   跳过错误批次

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
                    for data in tqdm(val_loader, ncols=, desc="Validation"):
                        filename = ["unknown"]
                        try:
                            lr, hr, filename = data
                            lr = lr.to(config["device"], non_blocking=True)
                            hr = hr.to(config["device"], non_blocking=True)

                             模型推理
                            predict = model(lr).detach().cpu().clamp(, )

                             数据处理
                            predict = predict.squeeze()
                            hr_np = hr.squeeze().cpu()

                             计算指标（假设已有实现）
                            from utils.metrics import calc_psnr_torch, calc_ssim_torch

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
                            logger.write(f"验证样本 {filename[]} 处理失败: {e}")
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
                if early_stopping and config["early_stopping"]["enabled"]:
                    should_stop, reason = early_stopping.should_stop(
                        epoch,
                        epoch_psnr.avg,
                        epoch_ssim.avg,
                        epoch_loss.avg,
                        model,
                        optimizer,
                        scheduler,
                        logger,
                    )

                     记录early stopping状态
                    status = early_stopping.get_status_report()
                    logger.write(f"Early-Stopping状态: {status}")

                    if should_stop:
                        logger.write(
                            f"训练提前停止! 最佳epoch: {status['best_epoch']}, "
                            f"最佳PSNR: {status['best_psnr']:.f}"
                        )

                         加载最佳模型进行最终验证
                        best_checkpoint = early_stopping.load_best_model(
                            model, optimizer, scheduler
                        )
                        if best_checkpoint:
                            logger.write("已加载最佳模型进行最终验证")

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
         保存中断时的检查点
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

         中断时也进行测试（可选）
        if epoch > :   至少训练了一个epoch
            response = input("\n是否在中断前进行测试集评估？(y/n): ").lower().strip()
            if response == "y":
                test_results = evaluate_test_set(model, logger, save_images=False)
    except Exception as e:
        logger.write(f"训练过程发生错误: {e}")
         保存错误时的检查点
        error_ckp = os.path.join(ckp_dir, f"error_epoch_{epoch}.pth")
        torch.save({"epoch": epoch, "model_state_dict": model.state_dict()}, error_ckp)
        logger.write(f"错误检查点已保存: {error_ckp}")
    finally:
        tb_writer.close()


if __name__ == "__main__":
    main()
