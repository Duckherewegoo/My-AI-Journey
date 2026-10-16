!/usr/bin/env python
 -- coding: utf- --
"""
修正版：验证 DatasetClass 是否正确导入 + noise_std 参数是否存在
"""
import inspect
import sys
import importlib
from pathlib import Path

 ========== 步骤：强制导入并刷新模块（避免缓存） ==========
 把项目根目录加入Python路径（确保导入正确）
project_root = "/home/dake/Documents/Projects/Graduction_Projects/codes/nova/lu_mwcnn"
sys.path.insert(, str(project_root))

 强制导入并刷新 deeplesions 模块
try:
     先卸载旧模块（如果存在）
    if "base.datasets.deeplesions" in sys.modules:
        del sys.modules["base.datasets.deeplesions"]
    
     重新导入
    from base.datasets import deeplesions
    importlib.reload(deeplesions)   强制刷新，跳过缓存
    DeepLesionDataset = deeplesions.DeepLesionDataset
    print(" 成功导入 DeepLesionDataset 类")
except Exception as e:
    print(f" 导入失败：{type(e).__name__}: {e}")
    sys.exit()

 ========== 步骤：正确获取类的定义文件路径（修复 __file__ 错误） ==========
print("\n=== 验证类的定义文件 ===")
 方法：通过 inspect 获取类的定义模块，再访问模块的 __file__
try:
     获取类所在的模块
    class_module = inspect.getmodule(DeepLesionDataset)
    class_file = class_module.__file__   模块的 __file__ 是合法的
    print(f"DeepLesionDataset 定义文件：{class_file}")
     验证文件是否是你修改的版本
    expected_file = "/home/dake/Documents/Projects/Graduction_Projects/codes/base/datasets/deeplesions.py"
    if class_file == expected_file:
        print(" 导入的是正确的文件！")
    else:
        print(f" 导入的是错误文件！期望：{expected_file}，实际：{class_file}")
except Exception as e:
    print(f"️ 获取文件路径失败：{type(e).__name__}: {e}")

 ========== 步骤：核心验证：检查 __init__ 是否包含 noise_std 参数 ==========
print("\n=== 验证 __init__ 参数（关键！） ===")
try:
     获取 __init__ 方法的参数签名
    init_sig = inspect.signature(DeepLesionDataset.__init__)
    init_params = list(init_sig.parameters.keys())
    print(f"DeepLesionDataset __init__ 参数列表：{init_params}")
    
     检查是否包含 noise_std 和 scale_factor
    if "noise_std" in init_params:
        print(" __init__ 包含 noise_std 参数！")
    else:
        print(" __init__ 缺少 noise_std 参数（导入的是旧版本类）！")
    
    if "scale_factor" in init_params:
        print(" __init__ 包含 scale_factor 参数！")
    else:
        print(" __init__ 缺少 scale_factor 参数！")
except Exception as e:
    print(f" 校验参数失败：{type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

 ========== 步骤：验证配置 + 实例化数据集（最终测试） ==========
print("\n=== 验证配置并实例化数据集 ===")
import os
import torch
 复制你的真实配置
config = {
    "lr": e-,
    "epochs": ,
    "batch_size": ,
    "val_every": ,
    "num_workers": min(os.cpu_count() or , ),
    "device": "cuda:" if torch.cuda.is_available() else "cpu",
    "keep_checkpoints": ,
    "early_stopping": {
        "enabled": True,
        "patience": ,
        "min_delta": e-,
        "min_improvement": .,
        "warmup_epochs": ,
        "strategy": "composite",
    },
    "output_path": r"/home/dake/Documents/Projects/Graduation_Projects/codes/nova/lu_mwcnn/output_deeplesion",
    "dataset": {
        "train_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/train/HR/",
        "val_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/val/HR",
        "test_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/test/HR",
        "interface": "deeplesions.DeepLesionDataset",
        "crop_size": ,
        "scale_factor": ,
        "noise_std": .,
    },
}
config["noise_std"] = config["dataset"]["noise_std"]
config["grad_clip_norm"] = .
config["psnr_max"] = .
config["gradient_check_interval"] = 

 验证配置中的 noise_std
print(f"配置中的 noise_std: {config['dataset']['noise_std']}")

 尝试实例化数据集
try:
    train_set = DeepLesionDataset(
        hr_dir=config["dataset"]["train_hr_dir"],
        crop_size=config["dataset"]["crop_size"],
        noise_std=config["dataset"]["noise_std"],
        phase="train",
        scale_factor=config["dataset"]["scale_factor"],
    )
    print(f" 数据集实例化成功！HR文件数：{len(train_set)}")
     测试加载第一个样本
    lr, hr = train_set[]
    print(f" 加载样本成功！LR形状：{lr.shape}，HR形状：{hr.shape}")
except Exception as e:
    print(f" 实例化/加载数据集失败：{type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
