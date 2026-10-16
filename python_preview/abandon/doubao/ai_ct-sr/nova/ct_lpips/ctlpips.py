"""
ctlpips.py —— CT 专用 LPIPS 距离计算脚本

配套文件：modell.py（VGGLite 定义）
输入：两张单通道 CT 灰度图（会 resize 到 224×224）
输出：归一化后的 LPIPS 距离
"""

from PIL import Image
from torchvision import transforms
import torch
import os
import os.path as path
import argparse
from modell import VGGLite


# ===================== 基础配置 =====================
# 设备配置：自动检测GPU，优先使用cuda
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# 基础路径：当前脚本所在目录
dirname = path.dirname(path.abspath(__file__))

# 可配置的默认路径（支持环境变量覆盖）
DEFAULT_MODEL_PATH = os.getenv(
    'CTLPIPS_MODEL_PATH',
    path.join(dirname, 'out/ckp/vgglite_658.pth')
)
DEFAULT_IMG1_PATH = os.getenv(
    'CTLPIPS_IMG1_PATH',
    path.join(dirname, 'val_inference/0000_lr.png')
)
DEFAULT_IMG2_PATH = os.getenv(
    'CTLPIPS_IMG2_PATH',
    path.join(dirname, 'val_inference/0000_pred.png')
)
# 模型输出维度配置（适配checkpoint，默认）
DEFAULT_MODEL_NUM_CLASSES = int(os.getenv('CTLPIPS_MODEL_NUM_CLASSES', 658))
# 模型训练时的输入尺寸（关键：需匹配模型预期）
MODEL_INPUT_SIZE = (224, 224)


def load_model(model_path: str, num_classes: int) -> VGGLite:
    """
    加载模型（独立函数，仅接收参数，无默认值避免歧义）
    :param model_path: 模型文件路径
    :param num_classes: VGGLite模型的输出维度（需匹配checkpoint）
    :return: 加载好的VGGLite模型（eval模式）
    """
    # 路径合法性校验
    if not path.exists(model_path):
        raise FileNotFoundError(
            f"模型文件未找到，请检查路径: {model_path}\n"
            f"可通过环境变量 CTLPIPS_MODEL_PATH 指定模型路径，或通过 "
            f"--model-path 命令行参数覆盖"
        )

    # 初始化模型（使用传入的num_classes）
    vgg_model: VGGLite = VGGLite(num_classes).to(device)
    try:
        # 加载模型时自动适配设备
        state_dict = torch.load(model_path, map_location=device)

        # 兼容 DataParallel 保存的 ckp（"module.xxx" 前缀）
        state_dict = {k.replace("module.", "", 1): v
                      for k, v in state_dict.items()}

        # 兼容 {"model_state_dict": ...} 形式的 ckp
        if "model_state_dict" in state_dict:
            state_dict = state_dict["model_state_dict"]

        # 校验关键参数维度（layer5.4 是分类头最后一层）
        ckpt_shape = state_dict.get('layer5.4.weight', torch.Tensor()).shape
        model_shape = vgg_model.layer5[4].weight.shape
        if ckpt_shape != model_shape:
            raise ValueError(
                f"模型维度与checkpoint不匹配！\n"
                f"当前模型layer5.4.weight形状: {model_shape} "
                f"(num_classes={num_classes})\n"
                f"Checkpoint中layer5.4.weight形状: {ckpt_shape}\n"
                f"解决方案：通过命令行参数 --num-classes {ckpt_shape[0]} 调整维度"
            )

        vgg_model.load_state_dict(state_dict)
        vgg_model.eval()
    except RuntimeError as e:
        if "size mismatch" in str(e):
            err_dim = str(e).split('torch.Size([')[1].split(',')[0]
            raise RuntimeError(
                f"模型参数维度不匹配！\n"
                f"错误详情：{str(e)}\n"
                f"解决方案：通过命令行参数 --num-classes {err_dim} 调整维度"
            )
        raise
    except Exception as e:
        raise RuntimeError(f"模型加载失败: {str(e)}")

    return vgg_model


def load_image(img_path: str, target_size: tuple = MODEL_INPUT_SIZE) -> torch.Tensor:
    """
    加载图像并转换为单通道张量（强制resize到模型训练尺寸）
    :param img_path: 图像路径
    :param target_size: 模型训练时的输入尺寸 (宽, 高)
    :return: 单通道、指定尺寸的CHW张量
    """
    if not path.exists(img_path):
        raise FileNotFoundError(
            f"图像文件未找到: {img_path}\n"
            f"可通过环境变量 CTLPIPS_IMG1_PATH/CTLPIPS_IMG2_PATH 指定默认"
            f"图像路径，或通过 --img1/--img2 命令行参数覆盖"
        )

    try:
        with Image.open(img_path) as img:
            # 1. 转灰度图 → 2. resize到模型训练尺寸 → 3. 转张量
            img_gray = img.convert('L')
            # 兼容不同Pillow版本的插值方式
            try:
                img_resized = img_gray.resize(
                    target_size, Image.Resampling.BILINEAR)
            except AttributeError:
                # 老版本 Pillow 用 Image.BILINEAR
                img_resized = img_gray.resize(target_size, Image.BILINEAR)
            # 转张量后是 (1, H, W)（CHW），确保单通道
            img_tensor = transforms.ToTensor()(img_resized)
            if img_tensor.shape[0] != 1:
                img_tensor = img_tensor.mean(dim=0, keepdim=True)
            print(f"\n===== 图片加载调试信息 =====")
            print(f"图片路径: {img_path}")
            print(f"张量维度: {img_tensor.shape}")
            print(f"张量类型: {img_tensor.dtype}")
            print(
                f"数值范围: [{img_tensor.min().item()}, {img_tensor.max().item()}]")
            return img_tensor
    except Exception as e:
        raise RuntimeError(f"图像加载失败: {str(e)}")


def get_ct_lpips(
    img1: torch.Tensor,
    img2: torch.Tensor,
    vgg_model: VGGLite
) -> float:
    """
    计算单通道CT图像的LPIPS距离
    :param img1: 输入图像1（CHW，单通道，匹配模型输入尺寸）
    :param img2: 输入图像2（CHW，单通道，匹配模型输入尺寸）
    :param vgg_model: 加载好的VGGLite模型
    :return: 归一化后的LPIPS距离值
    """
    import traceback   # 新增：导入栈追踪模块
    try:
        # 1. 校验输入尺寸是否匹配模型要求
        if img1.shape[1:] != MODEL_INPUT_SIZE or img2.shape[1:] != MODEL_INPUT_SIZE:
            raise ValueError(
                f"输入图像尺寸与模型训练尺寸不匹配！\n"
                f"模型预期尺寸: {MODEL_INPUT_SIZE}，实际img1:{img1.shape[1:]}, "
                f"img2:{img2.shape[1:]}\n"
                f"已自动resize到{MODEL_INPUT_SIZE}，若仍报错请确认模型训练尺寸"
            )
        # 2. 校验维度和通道数
        if len(img1.shape) != 3 or len(img2.shape) != 3:
            raise ValueError(
                f"输入维度错误！要求CHW 3维张量，实际img1:{img1.shape}, "
                f"img2:{img2.shape}"
            )
        if img1.shape[0] != 1 or img2.shape[0] != 1:
            raise ValueError(
                f"通道数错误！要求单通道，实际img1:{img1.shape[0]}, "
                f"img2:{img2.shape[0]}"
            )
        if img1.shape[1:] != img2.shape[1:]:
            raise ValueError(
                f"尺寸不匹配！img1:{img1.shape[1:]}, img2:{img2.shape[1:]}"
            )

        # 新增：检测全0张量，提前提示
        if torch.allclose(img1, torch.zeros_like(img1)):
            print("警告：img1是全0张量，LPIPS计算结果无意义！")
        if torch.allclose(img2, torch.zeros_like(img2)):
            print("警告：img2是全0张量，LPIPS计算结果无意义！")

        # 设备对齐（原有代码）
        img1 = img1.to(device, non_blocking=True)
        img2 = img2.to(device, non_blocking=True)

        # 特征提取
        def extract_features(img: torch.Tensor) -> torch.Tensor:
            with torch.no_grad():
                # 新增：先打印模型返回值，确认结构（关键调试）
                output = vgg_model(img.unsqueeze(0))
                print("===== 模型返回值调试信息 =====")
                print(f"模型forward返回值类型: {type(output)}")
                if isinstance(output, torch.Tensor):
                    print(f"模型返回值形状: {output.shape}")
                    fmap = output  # 单张量直接赋值
                else:
                    print(f"模型返回值长度: {len(output)}")
                    print(f"第一个返回值形状: {output[0].shape}")
                    fmap = output[0]  # 多返回值取第一个
                return fmap.squeeze(0)

        # 提取特征并验证
        fmap1 = extract_features(img1)
        fmap2 = extract_features(img2)
        if fmap1.shape != fmap2.shape:
            raise ValueError(
                f"特征图维度不匹配！fmap1:{fmap1.shape}, fmap2:{fmap2.shape}"
            )

        # 标准LPIPS计算
        # 新增：给norm添加极小值，避免除以0
        eps = 1e-8  # 极小值，防止分母为0
        fmap1_norm = fmap1 / (
            torch.norm(fmap1, dim=(2, 3), keepdim=True) + eps)
        fmap2_norm = fmap2 / (
            torch.norm(fmap2, dim=(2, 3), keepdim=True) + eps)

        # 替换nan/inf为0
        fmap1_norm = torch.nan_to_num(
            fmap1_norm, nan=0.0, posinf=1.0, neginf=-1.0)
        fmap2_norm = torch.nan_to_num(
            fmap2_norm, nan=0.0, posinf=1.0, neginf=-1.0)

        channel_dist = torch.norm(fmap1_norm - fmap2_norm, dim=(2, 3))
        total_dist = torch.sum(channel_dist)

        # 面积归一化
        area = img1.shape[1] * img1.shape[2]
        lpips_dist = (total_dist / (area + eps)).item()  # 避免area为0

        return lpips_dist

    except Exception as e:
        # 新增：打印完整的异常栈，定位具体错误行
        print("===== 计算LPIPS失败详情 =====")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        print("完整错误栈:")
        traceback.print_exc()
        print("============================")
        return float('nan')


if __name__ == '__main__':
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='计算CT图像的LPIPS距离')

    # 模型路径参数
    parser.add_argument(
        '--model-path',
        type=str,
        default=DEFAULT_MODEL_PATH,
        help=f'模型文件路径（默认：{DEFAULT_MODEL_PATH}，可通过环境变量 '
             f'CTLPIPS_MODEL_PATH 覆盖）'
    )

    # 图像路径参数
    parser.add_argument(
        '--img1',
        type=str,
        default=DEFAULT_IMG1_PATH,
        help=f'第一张图像路径（默认：{DEFAULT_IMG1_PATH}，可通过环境变量 '
             f'CTLPIPS_IMG1_PATH 覆盖）'
    )
    parser.add_argument(
        '--img2',
        type=str,
        default=DEFAULT_IMG2_PATH,
        help=f'第二张图像路径（默认：{DEFAULT_IMG2_PATH}，可通过环境变量 '
             f'CTLPIPS_IMG2_PATH 覆盖）'
    )

    # 模型维度参数
    parser.add_argument(
        '--num-classes',
        type=int,
        default=DEFAULT_MODEL_NUM_CLASSES,
        help=f'VGGLite模型输出维度（默认：{DEFAULT_MODEL_NUM_CLASSES}，'
             f'可通过环境变量 CTLPIPS_MODEL_NUM_CLASSES 覆盖）'
    )

    args = parser.parse_args()

    # 加载模型（使用解析后的参数）
    try:
        vgg_model = load_model(args.model_path, args.num_classes)
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"模型加载失败: {str(e)}")
        exit()

    # 加载图像（强制resize到模型训练尺寸）
    try:
        img1 = load_image(args.img1, target_size=MODEL_INPUT_SIZE)
        img2 = load_image(args.img2, target_size=MODEL_INPUT_SIZE)
    except FileNotFoundError as e:
        print(f"图像加载失败: {str(e)}")
        exit()

    # 计算并打印结果
    try:
        distance = get_ct_lpips(img1, img2, vgg_model)
        print(f"CT-LPIPS距离: {distance:.6f}")
    except Exception as e:
        print(f"计算失败: {str(e)}")
        exit()
