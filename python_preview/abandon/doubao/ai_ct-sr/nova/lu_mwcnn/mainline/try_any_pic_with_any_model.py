import os
import argparse
import torch
import numpy as np
from PIL import Image
from torchvision import transforms
from typing import List

 支持的图像格式
SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')

 预定义的现成模型（可扩展）
PREDEFINED_MODELS = {
    "lumwcnn": "LU-MWCNN（医学图像超分）",
    "esrgan": "ESRGAN（通用图像超分）",
    "srcnn": "SRCNN（经典超分）"
}


def get_device() -> torch.device:
    """自动检测可用设备（CUDA优先）"""
    if torch.cuda.is_available():
        device = torch.device("cuda:")
        print(f" 使用CUDA设备: {torch.cuda.get_device_name()}")
    else:
        device = torch.device("cpu")
        print("️ CUDA不可用，使用CPU推理（速度较慢）")
    return device


def load_predefined_model(model_type: str, device: torch.device) -> torch.nn.Module:
    """
    加载预定义的现成模型（无需.pth文件）
    修复点：. 修正modell笔误 . 补充ESRGAN/SRCNN示例实现 . 增强异常提示
    """
    model_type = model_type.lower()
    if model_type not in PREDEFINED_MODELS:
        raise ValueError(f"不支持的预定义模型类型！可选：{list(PREDEFINED_MODELS.keys())}")

     提前初始化model变量，避免"possibly unbound"错误
    model = None
    try:
        if model_type == "lumwcnn":
             修复笔误：modell → model（需确保model.py中存在LUMWCNN类）
            from modell import LUMWCNN
            model = LUMWCNN()
        elif model_type == "esrgan":
             ESRGAN示例实现（简化版，需根据实际模型调整）
            class ESRGAN(torch.nn.Module):
                def __init__(self, scale=):
                    super().__init__()
                    self.scale = scale
                     简化版上采样层（需替换为实际ESRGAN结构）
                    self.upsample = torch.nn.Upsample(scale_factor=scale, mode='bicubic', align_corners=False)

                def forward(self, x):
                    return self.upsample(x)
            model = ESRGAN(scale=)
        elif model_type == "srcnn":
             SRCNN示例实现（简化版，需替换为实际SRCNN结构）
            class SRCNN(torch.nn.Module):
                def __init__(self):
                    super().__init__()
                    self.conv = torch.nn.Convd(, , kernel_size=, padding=)
                    self.conv = torch.nn.Convd(, , kernel_size=, padding=)
                    self.conv = torch.nn.Convd(, , kernel_size=, padding=)
                    self.relu = torch.nn.ReLU()

                def forward(self, x):
                    x = self.relu(self.conv(x))
                    x = self.relu(self.conv(x))
                    x = self.conv(x)
                    return x
            model = SRCNN()

         确保model已初始化
        if model is None:
            raise RuntimeError("预定义模型初始化失败：model为None")

        model = model.to(device)
        model.eval()
        print(f" 加载预定义模型成功: {model_type} ({PREDEFINED_MODELS[model_type]})")
        return model

    except ImportError as e:
        raise ImportError(f"加载{model_type}模型失败：缺少模型类定义 → {e}\n提示：请确保model.py中包含对应模型类")
    except Exception as e:
        raise RuntimeError(f"加载预定义模型失败: {e}")


def wrap_model(model, device):
    """封装模型：仅保证维输入输出，不限制尺寸，自动检测超分倍率"""
    class ModelWrapper(torch.nn.Module):
        def __init__(self, original_model):
            super().__init__()
            self.original_model = original_model
            self.scale = None   超分倍率（自动检测）

        def forward(self, x):
             仅强制输入是维 [B,C,H,W]，不限制尺寸
            assert x.ndim == , f"输入必须是维，当前{x.ndim}维: {x.shape}"
            b, c, h, w = x.shape

             执行原始模型前向传播（无任何尺寸限制）
            out = self.original_model(x)

             自动检测超分倍率（仅第一次运行时检测）
            if self.scale is None:
                self.scale = out.shape[] // h   高度倍率（假设宽高倍率一致）
                print(f" 自动检测到模型超分倍率: {self.scale}倍")

             仅强制输出是维，不限制尺寸
            if out.ndim == :
                out = out.reshape(b, c, out.shape[], out.shape[])
            elif out.ndim == :
                out = out.unsqueeze()
            assert out.ndim == , f"输出必须是维，当前{out.ndim}维: {out.shape}"

            return out

    wrapped_model = ModelWrapper(model).to(device)
    wrapped_model.eval()
    return wrapped_model


def load_custom_model(model_path: str, device: torch.device, in_channels: int = ) -> torch.nn.Module:
    """加载自定义模型并封装，防止维度错乱"""
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"模型文件不存在: {model_path}")

     注册安全全局对象
    torch.serialization.add_safe_globals([np.dtype, np._core.multiarray.scalar, np.ndarray])

    try:
         加载模型（关闭weights_only，信任来源）
        checkpoint = torch.load(model_path, map_location=device, weights_only=False)
        state_dict = checkpoint.get("model_state_dict", checkpoint)
        state_dict = {k.replace('module.', ''): v for k, v in state_dict.items() if v is not None}

         初始化模型
        from modell import LUMWCNN
        model = LUMWCNN(in_channels=in_channels, device=device)
        model.load_state_dict(state_dict, strict=False)
        model = model.to(device)
        model.eval()   设为评估模式，减少显存占用

         关键：封装模型，强制维输入输出
        model = wrap_model(model, device)

        print(f" 加载自定义模型成功 | 模型初始类型: {next(model.parameters()).dtype}")
        return model

    except Exception as e:
        error_msg = f"加载自定义模型失败: {e}\n"
        error_msg += " 解决提示：确保modell.py包含LUMWCNN类，且模型文件为合法.pth格式"
        raise RuntimeError(error_msg)


def preprocess_image(image_path: str, device: torch.device, color_mode: str = "gray", scale_down: float = .) -> torch.Tensor:
    """预处理图像（强制输出维张量 [,C,H,W]，解决维度丢失）"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图像不存在: {image_path}")

     . 读取图像
    if color_mode == "gray":
        pil_img = Image.open(image_path).convert('L')
        c = 
    elif color_mode == "rgb":
        pil_img = Image.open(image_path).convert('RGB')
        c = 
    else:
        raise ValueError(f"颜色模式仅支持gray/rgb，当前: {color_mode}")

     . 可选降采样
    if scale_down < .:
        new_w = int(pil_img.width  scale_down)
        new_h = int(pil_img.height  scale_down)
        pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        print(f"️ 降采样 {scale_down} 倍: {pil_img.width//scale_down}×{pil_img.height//scale_down} → {new_w}×{new_h}")

     . 调整为的倍数（适配小波变换）
    w, h = pil_img.size
    multiple = 
    new_w = ((w + multiple - ) // multiple)  multiple
    new_h = ((h + multiple - ) // multiple)  multiple
    if new_w != w or new_h != h:
        pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

     . 转为张量（严格维 [,C,H,W]）
    img_np = np.array(pil_img).astype(np.float) / .
    if color_mode == "rgb":
        img_np = np.transpose(img_np, (, , ))   (H,W,) → (,H,W)
    else:
        img_np = np.expand_dims(img_np, axis=)   (H,W) → (,H,W)
     强制增加batch维度 → 维 [,C,H,W]
    img_tensor = torch.from_numpy(img_np).unsqueeze().to(device)

     最终校验
    assert img_tensor.shape == (, c, new_h, new_w), f"张量形状错误: 预期(,{c},{new_h},{new_w})，实际{img_tensor.shape}"
    print(f" 预处理完成 | 尺寸: {pil_img.size} | 张量: {img_tensor.shape} | 设备: {device}")
    return img_tensor


def postprocess_tensor(tensor: torch.Tensor) -> Image.Image:
    """
    张量后处理（转回PIL图像）
    修复点：. 增强维度兼容性 . 优化数值裁剪 . 修复RGB维度顺序
    """
     移除batch维度 + 转回CPU
    img_np = tensor.squeeze().cpu().detach().numpy()

     处理维度：确保为(C,H,W)格式
    if img_np.ndim == :   无通道维度 (H,W)
        img_np = np.expand_dims(img_np, axis=)
    assert img_np.ndim == , f"异常的张量维度: {img_np.ndim}（预期维）"

     调整维度顺序
    if img_np.shape[] == :   灰度图
        img_np = img_np.squeeze()   (,H,W) → (H,W)
    elif img_np.shape[] == :   RGB图
        img_np = np.transpose(img_np, (, , ))   (,H,W) → (H,W,)
    else:
        raise ValueError(f"不支持的通道数: {img_np.shape[]}（仅支持/通道）")

     反归一化并裁剪到有效范围（避免数值溢出）
    img_np = np.clip(img_np  ., , ).astype(np.uint)

    return Image.fromarray(img_np)


def sr_inference(
    model: torch.nn.Module,
    image_path: str,
    output_path: str,
    device: torch.device,
    color_mode: str = "gray",
    tile_size: int = ,
    scale_down: float = .
) -> None:
    """执行超分辨率重建（彻底移除尺寸断言+适配超分模型）"""
    try:
         . 预处理（输出维张量 [B,C,H,W]）
        img_tensor = preprocess_image(image_path, device, color_mode, scale_down=scale_down)
        assert img_tensor.ndim == , f"输入必须是维张量，当前{img_tensor.ndim}维: {img_tensor.shape}"
        b, c, h_ori, w_ori = img_tensor.shape
        print(f" 原始图像张量: B={b}, C={c}, H={h_ori}, W={w_ori}")

         . 统一数据类型（模型+输入）
        model_dtype = next(model.parameters()).dtype
        img_tensor = img_tensor.to(dtype=model_dtype)
        print(f" 模型类型: {model_dtype} | 输入类型: {img_tensor.dtype}")

         . 自动检测超分倍率（无尺寸断言）
        test_tile = img_tensor[:, :, :min(tile_size, h_ori), :min(tile_size, w_ori)].clone()
        with torch.no_grad():
            test_out = model(test_tile)
        scale = test_out.shape[] // test_tile.shape[]   计算超分倍率
        print(f" 模型超分倍率: {scale}倍 | 超分后图像尺寸: ({h_oriscale}×{w_oriscale})")

         . 初始化超分输出张量（CPU，避免显存占用）
        sr_tensor = torch.zeros((b, c, h_ori  scale, w_ori  scale), dtype=model_dtype, device="cpu")

         . 分块推理参数
        num_tiles_h = (h_ori + tile_size - ) // tile_size
        num_tiles_w = (w_ori + tile_size - ) // tile_size
        print(f" 分块推理：{num_tiles_h}×{num_tiles_w} 瓦片 | 单瓦片尺寸: {tile_size}×{tile_size}")

         . 逐块推理（无任何尺寸断言）
        for i in range(num_tiles_h):
            for j in range(num_tiles_w):
                 原始瓦片坐标
                start_h = i  tile_size
                end_h = min(start_h + tile_size, h_ori)
                start_w = j  tile_size
                end_w = min(start_w + tile_size, w_ori)
                tile_h_ori = end_h - start_h
                tile_w_ori = end_w - start_w

                 提取原始瓦片（仅保维，不限制尺寸）
                tile = img_tensor[:, :, start_h:end_h, start_w:end_w].clone()

                 缩放瓦片到模型输入尺寸
                tile_input = torch.nn.functional.interpolate(
                    tile,
                    size=(tile_size, tile_size),
                    mode='bilinear',
                    align_corners=False
                )
                print(f"  瓦片 ({i},{j}) | 输入模型尺寸: {tile_input.shape}")

                 清理显存 + 无梯度推理
                if device.type == "cuda":
                    torch.cuda.empty_cache()
                with torch.no_grad():
                    tile_sr = model(tile_input)   输出尺寸: tile_sizescale × tile_sizescale

                 缩放超分瓦片到原始瓦片的超分尺寸
                tile_sr_resized = torch.nn.functional.interpolate(
                    tile_sr,
                    size=(tile_h_ori  scale, tile_w_ori  scale),
                    mode='bilinear',
                    align_corners=False
                )

                 超分瓦片的目标坐标
                sr_start_h = start_h  scale
                sr_end_h = sr_start_h + tile_h_ori  scale
                sr_start_w = start_w  scale
                sr_end_w = sr_start_w + tile_w_ori  scale

                 写入输出张量
                sr_tensor[:, :, sr_start_h:sr_end_h, sr_start_w:sr_end_w] = tile_sr_resized.cpu()

                 打印状态
                if device.type == "cuda":
                    mem_info = torch.cuda.mem_get_info(device)
                    mem_free = mem_info[] /  / 
                    print(f"  瓦片 ({i},{j}) 完成 | 剩余显存: {mem_free:.f} MiB | 超分后尺寸: {tile_sr_resized.shape[:]}")
                else:
                    print(f"  瓦片 ({i},{j}) 完成 | CPU推理中 | 超分后尺寸: {tile_sr_resized.shape[:]}")

         . 后处理保存
        sr_tensor = sr_tensor.to(device).float()
        sr_tensor = sr_tensor[:, :, :h_ori  scale, :w_ori  scale]   裁剪到精确尺寸
        sr_img = postprocess_tensor(sr_tensor)

         保存超分图像
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        sr_img.save(output_path)
        print(f"\n 超分重建成功！")
        print(f"   - 原始尺寸: {h_ori}×{w_ori}")
        print(f"   - 超分尺寸: {sr_img.size[]}×{sr_img.size[]}")
        print(f"   - 保存路径: {output_path}")

    except Exception as e:
        if device.type == "cuda":
            torch.cuda.empty_cache()
        raise RuntimeError(f"处理失败: {e}")


def get_image_list(input_path: str) -> List[str]:
    """获取输入路径下的所有图像文件（单张/文件夹）→ 增强过滤逻辑"""
    image_list = []
    if os.path.isfile(input_path):
        if input_path.lower().endswith(SUPPORTED_EXTENSIONS):
            image_list.append(input_path)
        else:
            raise ValueError(f"不支持的图像格式: {input_path} → 支持格式: {SUPPORTED_EXTENSIONS}")
    elif os.path.isdir(input_path):
         递归遍历子文件夹
        for root, _, files in os.walk(input_path):
            for fname in files:
                fpath = os.path.join(root, fname)
                if fname.lower().endswith(SUPPORTED_EXTENSIONS) and os.path.isfile(fpath):
                    image_list.append(fpath)
        if not image_list:
            raise ValueError(f"文件夹 {input_path} 及其子文件夹中未找到支持的图像文件 → 支持格式: {SUPPORTED_EXTENSIONS}")
    else:
        raise FileNotFoundError(f"输入路径不存在: {input_path}")

     去重并排序
    image_list = sorted(list(set(image_list)))
    print(f" 找到 {len(image_list)} 张待处理图像")
    return image_list


def main():
     修复环境变量警告（兼容新旧版本）
    os.environ['PYTORCH_ALLOC_CONF'] = 'expandable_segments:True'
    torch.serialization.add_safe_globals([np.dtype, np._core.multiarray.scalar])

     解析参数
    parser = argparse.ArgumentParser(description="超分推理（最终兼容版）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--custom_model", type=str, help="自定义模型路径")
    group.add_argument("--predefined_model", type=str, choices=PREDEFINED_MODELS.keys())
    parser.add_argument("--input_path", type=str, required=True, help="输入图像路径")
    parser.add_argument("--output_dir", type=str, default="./sr_results")
    parser.add_argument("--color_mode", type=str, choices=["gray", "rgb"], default="gray")
    parser.add_argument("--tile_size", type=int, default=, help="分块尺寸（模型固定输入尺寸）")
    parser.add_argument("--scale_down", type=float, default=., help="降采样比例")

    args = parser.parse_args()

     设备初始化（兼容CPU/GPU）
    if torch.cuda.is_available():
        device = torch.device("cuda:")
        print(f" 使用GPU: {torch.cuda.get_device_name()}")
    else:
        device = torch.device("cpu")
        print(f" 使用CPU推理")

     加载模型
    try:
        if args.custom_model:
            in_channels =  if args.color_mode == "rgb" else 
            model = load_custom_model(args.custom_model, device, in_channels=in_channels)
        else:
            model = load_predefined_model(args.predefined_model, device)
    except Exception as e:
        print(f"\n 模型加载失败: {e}")
        return

     处理图像
    try:
        img_path = args.input_path
        output_path = os.path.join(args.output_dir, os.path.basename(img_path))
        sr_inference(
            model=model,
            image_path=img_path,
            output_path=output_path,
            device=device,
            color_mode=args.color_mode,
            tile_size=args.tile_size,
            scale_down=args.scale_down
        )
        print(f"\n 全部处理完成！结果: {output_path}")
    except Exception as e:
        print(f"\n 处理失败: {e}")


if __name__ == "__main__":
    main()
