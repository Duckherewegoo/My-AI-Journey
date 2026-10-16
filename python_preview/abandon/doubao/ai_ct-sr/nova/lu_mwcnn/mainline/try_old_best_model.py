 -- coding: utf- --
"""模型评估脚本（最终版：修复SSIM计算+完整评估）"""
import torch as torch_main
import sys
import os
import traceback
import numpy as np
from tqdm import tqdm
from PIL import Image
import warnings

 ===================== . 基础配置 =====================
warnings.filterwarnings('ignore')

 安装必要库（skimage用于SSIM计算）
try:
    from skimage.metrics import structural_similarity as ssim
    print(" skimage导入成功")
except ImportError:
    print("️ skimage未安装，正在自动安装...")
    os.system("pip install scikit-image")
    from skimage.metrics import structural_similarity as ssim

 安装lpips
try:
    from lpips import LPIPS
    print(" lpips库导入成功")
except ImportError:
    print("️ lpips未安装，正在自动安装...")
    os.system("pip install lpips")
    from lpips import LPIPS

 全局torch
print(f" 全局torch初始化 | 版本: {torch_main.__version__} | CUDA: {torch_main.cuda.is_available()} | ID: {id(torch_main)}")
torch_main.set_default_device('cuda:' if torch_main.cuda.is_available() else 'cpu')

 ===================== . 配置参数 =====================
config = {
    "device": "cuda:" if torch_main.cuda.is_available() else "cpu",
    "dataset": {
        "test_hr_dir": r"/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/test/HR",
        "interface": "deeplesions.DeepLesionDataset",
        "crop_size": ,
        "scale_factor": ,
        "noise_std": .,
    },
    "model_path": r"/home/dake/Documents/Projects/Graduction_Projects/codes/nova/lu_mwcnn/output_deeplesion/deeplesion_train_bravo_ckpt/best_model.pth",
    "save_pred_samples": True,
    "sample_save_dir": "./model_evaluation_samples",
    "max_eval_samples": ,
}

 ===================== . 工具函数（修复SSIM） =====================


def calc_psnr_np(pred, target):
    """计算PSNR（纯NumPy实现，稳定可靠）"""
    pred = np.array(pred, dtype=np.float)
    target = np.array(target, dtype=np.float)

     确保输入是二维图像
    if len(pred.shape) == :
        pred = pred.squeeze()
    if len(target.shape) == :
        target = target.squeeze()

    mse = np.mean((pred - target)  )
    return float('inf') if mse ==  else   np.log(. / np.sqrt(mse))


def calc_ssim_np(pred, target):
    """计算SSIM（使用skimage行业标准实现，避免自己写的bug）"""
    pred = np.array(pred, dtype=np.float)
    target = np.array(target, dtype=np.float)

     确保输入是二维图像（去除通道维度）
    if len(pred.shape) == :
        pred = pred.squeeze()
    if len(target.shape) == :
        target = target.squeeze()

     验证形状匹配
    if pred.shape != target.shape:
        print(f"️ SSIM形状不匹配 | pred.shape: {pred.shape} | target.shape: {target.shape}")
        return .

     计算SSIM（适用于灰度图，data_range=.因为图像已归一化到-）
    ssim_score = ssim(pred, target, data_range=., win_size=)
    return ssim_score


def normalize_image(arr):
    """归一化图像到-"""
    arr = arr - arr.min()
    arr = arr / (arr.max() + e-)
    return (arr  ).astype(np.uint)


def calc_lpips(img, img):
    """LPIPS计算函数"""
    lpips_model = LPIPS(net='vgg').to(config["device"])
    lpips_model.eval()
    with torch_main.no_grad():
        lpips_score = lpips_model(img, img).detach().cpu().squeeze().mean()
    return lpips_score

 ===================== . 核心模型函数 =====================


def load_model_isolated(model_path, device):
    """加载模型"""
    print("\n 进入load_model_isolated函数")
    try:
        import torch as local_torch
        print(f"   - local_torch导入 | ID: {id(local_torch)} | 全局torch ID: {id(torch_main)} | 是否同一对象: {local_torch is torch_main}")
        print(f"   - local_torch设备 | CUDA可用: {local_torch.cuda.is_available()} | 默认设备: {local_torch.get_default_device()}")

         模型路径处理
        model_dir = os.path.dirname(model_path)
        sys.path.insert(, model_dir)
        print(f"   - 模型路径: {model_dir} | sys.path包含: {model_dir in sys.path}")

         导入模型
        from model import LUMWCNN as LocalLUMWCNN
        print(f"   - 模型类导入成功 | 类名: {LocalLUMWCNN.__name__}")

         初始化模型
        model = LocalLUMWCNN()
        model = model.to(device)
        print(f"   - 模型初始化成功 | 设备: {next(model.parameters()).device}")

         加载权重
        checkpoint = local_torch.load(model_path, map_location=device, weights_only=False)
        state_dict = checkpoint.get('model_state_dict', checkpoint)
        print(f"   - 权重加载成功 | 权重key数: {len(state_dict)}")

         适配权重
        matched_dict = {}
        model_state_dict = model.state_dict()
        for k, v in state_dict.items():
            k_clean = k.replace('module.', '')
            if k_clean in model_state_dict and model_state_dict[k_clean].shape == v.shape:
                matched_dict[k_clean] = v
        model.load_state_dict(matched_dict, strict=False)
        model.eval()
        print(f"   - 权重适配完成 | 匹配key数: {len(matched_dict)} / {len(model_state_dict)}")

        return model, local_torch

    except Exception as e:
        print(f" load_model_isolated失败: {str(e)}")
        traceback.print_exc()
        raise


def infer_single_sample(model, lr_tensor, local_torch, device):
    """推理函数"""
    print("\n 进入infer_single_sample函数")
    try:
         调试入参
        print(f"   - local_torch ID: {id(local_torch)} | 是否可用: {local_torch is not None}")
        print(f"   - 输入张量 | 形状: {lr_tensor.shape} | 设备: {lr_tensor.device}")

         张量设备对齐
        lr_tensor = lr_tensor.to(device, non_blocking=True)
        print(f"   - 张量设备调整后 | 设备: {lr_tensor.device}")

         推理
        with local_torch.no_grad():
            pred = model(lr_tensor)
            pred = local_torch.clamp(pred, ., .)
        print(f"   - 推理完成 | 输出形状: {pred.shape}")

         转NumPy
        pred_np = pred.detach().cpu().squeeze().numpy()
        print(f"   - 转NumPy完成 | 形状: {pred_np.shape} | 数值范围: [{pred_np.min():.f}, {pred_np.max():.f}]")

        return pred_np

    except Exception as e:
        print(f" infer_single_sample失败: {str(e)}")
        traceback.print_exc()
        raise

 ===================== . 主评估函数 =====================


def evaluate_model():
    """主评估流程"""
    print("\n" + "="  )
    print(" 开始模型评估流程")
    print("="  )

     . 加载模型
    model, local_torch = None, None
    try:
        model, local_torch = load_model_isolated(config['model_path'], config['device'])
        print(f" 模型加载完成 | model ID: {id(model)} | local_torch ID: {id(local_torch)}")
    except Exception as e:
        print(f" 模型加载总失败: {str(e)}")
        traceback.print_exc()
        return

     . 随机张量测试
    try:
        test_lr = local_torch.randn(, , , , device=config['device'])
        print(f"\n 随机张量测试 | 张量形状: {test_lr.shape} | 设备: {test_lr.device}")
        pred_np = infer_single_sample(model, test_lr, local_torch, config['device'])
        print(f" 随机张量测试成功 | 输出形状: {pred_np.shape}")
    except Exception as e:
        print(f" 随机张量测试总失败: {str(e)}")
        traceback.print_exc()
        return

     . 加载数据集
    test_loader = None
    try:
        print("\n 开始加载数据集")
        import importlib
        module_name, class_name = config["dataset"]["interface"].split(".")
        dataset_mod = importlib.import_module(f"base.datasets.{module_name}")
        DatasetClass = getattr(dataset_mod, class_name)
        print(f"   - 数据集类导入成功 | 类名: {DatasetClass.__name__}")

        test_set = DatasetClass(
            hr_dir=config["dataset"]["test_hr_dir"],
            crop_size=config["dataset"]["crop_size"],
            scale_factor=config["dataset"]["scale_factor"],
            noise_std=config["dataset"]["noise_std"],
            phase="test",
            augment=False,
        )
        print(f"   - 数据集初始化成功 | 样本数: {len(test_set)}")

        test_loader = torch_main.utils.data.DataLoader(
            test_set, batch_size=, shuffle=False, pin_memory=False, num_workers=
        )
        print(f" 数据集加载完成 | 批次数量: {len(test_loader)}")
    except Exception as e:
        print(f" 数据集加载总失败: {str(e)}")
        traceback.print_exc()
        return

     . 逐样本评估
    psnr_list, ssim_list = [], []
    os.makedirs(config["sample_save_dir"], exist_ok=True)

    print("\n 开始逐样本评估")
    pbar = tqdm(test_loader, desc="Evaluating")
    for sample_idx, data in enumerate(pbar):
        if config["max_eval_samples"] and sample_idx >= config["max_eval_samples"]:
            break

        print(f"\n 处理样本 {sample_idx}")
        try:
            lr, hr = data[:]
            print(f"   - 样本张量 | LR形状: {lr.shape} | HR形状: {hr.shape} | LR设备: {lr.device}")

             推理
            pred_np = infer_single_sample(model, lr, local_torch, config['device'])
            hr_np = hr.cpu().squeeze().numpy()

             验证形状
            print(f"   - 形状验证 | pred_np: {pred_np.shape} | hr_np: {hr_np.shape}")

             计算指标
            psnr = calc_psnr_np(pred_np, hr_np)
            ssim_score = calc_ssim_np(pred_np, hr_np)

            psnr_list.append(psnr)
            ssim_list.append(ssim_score)
            print(f"   - 指标计算完成 | PSNR: {psnr:.f} | SSIM: {ssim_score:.f}")

             保存样本
            if sample_idx < :
                pred_img = Image.fromarray(normalize_image(pred_np), mode='L')
                pred_img.save(f"{config['sample_save_dir']}/sample_{sample_idx}_pred.png")
                print(f"   - 样本保存成功 | 路径: {config['sample_save_dir']}/sample_{sample_idx}_pred.png")

            pbar.set_postfix({
                'Avg PSNR': f"{np.mean(psnr_list):.f}",
                'Avg SSIM': f"{np.mean(ssim_list):.f}",
            })

        except Exception as e:
            print(f" 样本{sample_idx}处理失败: {str(e)}")
            traceback.print_exc()
            continue

     . 结果汇总
    print("\n" + "="  )
    print(" 评估结果汇总")
    print("="  )
    if len(psnr_list) > :
        print(f"有效样本数: {len(psnr_list)}")
        print(f"平均PSNR: {np.mean(psnr_list):.f} dB")
        print(f"平均SSIM: {np.mean(ssim_list):.f}")
        print(f"PSNR最大值: {np.max(psnr_list):.f} dB")
        print(f"PSNR最小值: {np.min(psnr_list):.f} dB")
    else:
        print(" 无有效评估样本")

 ===================== . 运行入口 =====================


if __name__ == "__main__":
    try:
        evaluate_model()
    except Exception as e:
        print("\n 程序总异常")
        traceback.print_exc()
    finally:
        print("\n 程序结束")
