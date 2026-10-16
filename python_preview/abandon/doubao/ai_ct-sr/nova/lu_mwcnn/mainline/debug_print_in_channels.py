"""
checkpoint_channel_analyzer.py
检查检查点中的模型通道数，判断是否支持RGB/灰度图像
"""

import torch
import os
import sys
import argparse
import re


def print_section(title, char="=", width=):
    """打印标题分割线"""
    print(f"\n{char  width}")
    print(f"{title.center(width)}")
    print(f"{char  width}")


def format_size(bytes):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < .:
            return f"{bytes:.f} {unit}"
        bytes /= .
    return f"{bytes:.f} TB"


def analyze_model_channels(checkpoint_path, device='cpu'):
    """
    分析检查点中的模型通道数
    """
    if not os.path.exists(checkpoint_path):
        print(f" 检查点文件不存在: {checkpoint_path}")
        return None, None, None

    try:
         加载检查点
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)

        if 'model_state_dict' not in checkpoint:
            print(f" 检查点中没有模型参数: {checkpoint_path}")
            return None, None, None

        model_state = checkpoint['model_state_dict']

         查找各种可能的输入卷积层
        input_conv_patterns = [
            'l_conv..model..weight',   你的LUMWCNN模型的第一层
            'conv.weight',                其他常见模型
            'features..weight',           VGG风格
            'conv.conv.weight',           ResNet风格
            'layer..conv.weight',       更深层的模型
        ]

        input_channels = None
        found_key = None

         按优先级查找卷积权重
        for pattern in input_conv_patterns:
            for key in model_state.keys():
                if pattern in key and 'weight' in key:
                    weight = model_state[key]
                    if weight.dim() == :   确保是卷积权重 [out_ch, in_ch, h, w]
                        input_channels = weight.shape[]
                        found_key = key
                        print(f" 找到输入卷积层: {key}")
                        print(f"   权重形状: {list(weight.shape)}")
                        print(f"   输入通道数: {input_channels}")
                        return input_channels, found_key, model_state
                    elif weight.dim() == :   线性层
                        print(f"️  找到线性层而不是卷积层: {key}")

         如果没有找到，尝试其他方法
        if input_channels is None:
            print("️ 无法找到标准的输入卷积层，尝试其他方法...")

             查找所有卷积层
            conv_layers = []
            for key, param in model_state.items():
                if 'weight' in key and param.dim() == :
                    conv_layers.append((key, param))

            if conv_layers:
                print(f"找到 {len(conv_layers)} 个卷积层")

                 尝试通过输入通道数推断
                for key, weight in conv_layers:
                    in_channels = weight.shape[]
                    if in_channels in [, ]:
                        input_channels = in_channels
                        found_key = key
                        print(f" 推测输入通道数: {input_channels} (来自 {key})")
                        return input_channels, found_key, model_state

        return input_channels, found_key, model_state

    except Exception as e:
        print(f" 加载检查点时出错: {e}")
        return None, None, None


def check_model_rgb_capability(model_state, input_channels, found_key):
    """
    检查模型是否具有RGB图像处理能力
    """
    if input_channels is None:
        return False, "无法确定输入通道数"

    if input_channels == :
        return True, f" 模型支持RGB图像 (输入通道数: )"
    elif input_channels == :
        return False, f"️ 模型仅支持灰度图像 (输入通道数: )"
    else:
        return False, f" 模型输入通道数异常: {input_channels}"


def analyze_upsample_modules(model_state, input_channels):
    """
    分析上采样模块的通道数配置
    """
    print_section("上采样模块分析", "-")

    upsample_layers = {}

     查找上采样相关层
    for key, param in model_state.items():
        if 'upsample' in key.lower() and 'weight' in key and param.dim() == :
            upsample_layers[key] = param
        elif 'up' in key.lower() and 'weight' in key and param.dim() == :
            upsample_layers[key] = param

    if not upsample_layers:
        print("️ 未找到明确的上采样卷积层")
        return

    print(f" 找到 {len(upsample_layers)} 个上采样相关卷积层:")

    for i, (key, weight) in enumerate(upsample_layers.items()):
        in_ch = weight.shape[]
        out_ch = weight.shape[]
        scale = None

         尝试推断上采样比例
        if out_ch == input_channels  :
            scale = 
        elif out_ch == input_channels  :
            scale = 
        elif out_ch == input_channels  :
            scale = 

        scale_info = f" (推测上采样比例: {scale}x)" if scale else ""
        print(f"  {i+}. {key}")
        print(f"     形状: [{out_ch}, {in_ch}, {weight.shape[]}, {weight.shape[]}]")
        print(f"     输入通道: {in_ch}, 输出通道: {out_ch}{scale_info}")

         检查通道数是否合理
        if in_ch != input_channels and in_ch != input_channels  :
            print(f"     ️ 警告: 输入通道数({in_ch})与模型输入({input_channels})不匹配")

        if scale and out_ch != input_channels  (scale  ):
            print(f"     ️ 警告: 输出通道数不符合预期")


def analyze_checkpoint(checkpoint_path, device='cpu'):
    """
    分析检查点文件
    """
    if not os.path.exists(checkpoint_path):
        print(f" 检查点文件不存在: {checkpoint_path}")
        return

     文件基本信息
    file_size = os.path.getsize(checkpoint_path)
    file_name = os.path.basename(checkpoint_path)
    print_section(f"检查点分析报告: {file_name}")
    print(f" 文件路径: {checkpoint_path}")
    print(f" 文件大小: {format_size(file_size)}")

    try:
         . 分析模型通道数
        print_section(". 模型通道数分析", "-")
        input_channels, found_key, model_state = analyze_model_channels(checkpoint_path, device)

        if input_channels is None:
            print(" 无法分析模型通道数")
            return

         . 检查RGB处理能力
        rgb_capable, rgb_message = check_model_rgb_capability(model_state, input_channels, found_key)
        print(f"\n {rgb_message}")

         . 提供使用建议
        print_section(". 使用建议", "-")
        if rgb_capable:
            print(" 这个模型可以直接用于RGB图像训练/推理")
            print("   支持的输入图像类型: 彩色图片 (通道)")
            print("   支持的输出图像类型: 彩色图片 (通道)")
        else:
            print("️ 这个模型只能处理灰度图像")
            print("   支持的输入图像类型: 灰度图片 (通道)")
            print("   支持的输出图像类型: 灰度图片 (通道)")
            print("\n 如果需要处理RGB图像，需要:")
            print("   . 修改模型输入通道数为")
            print("   . 使用通道适配加载预训练权重")

         . 检查上采样模块
        analyze_upsample_modules(model_state, input_channels)

         . 检查模型中的通道相关层
        print_section(". 关键卷积层分析", "-")

         查找所有输入通道为或的卷积层
        input_convs = []
        other_convs = []

        for key, param in model_state.items():
            if 'weight' in key and param.dim() == :
                in_ch = param.shape[]
                if in_ch == input_channels:
                    input_convs.append((key, param))
                elif in_ch in [, ]:
                    other_convs.append((key, param))

        print(f" 输入相关卷积层 (输入通道数={input_channels}): {len(input_convs)} 个")
        for i, (key, param) in enumerate(input_convs[:]):   只显示前个
            print(f"  {key}: {list(param.shape)}")

        if len(input_convs) > :
            print(f"  ... 还有 {len(input_convs)-} 个")

         . 检查模型参数数量
        print_section(". 模型参数统计", "-")
        total_params = 
        for param in model_state.values():
            if isinstance(param, torch.Tensor):
                total_params += param.numel()

        print(f" 总模型参数数量: {total_params:,}")

         . 检查文件名中的提示
        print_section(". 文件命名提示", "-")
        filename_lower = file_name.lower()

        if 'rgb' in filename_lower:
            print(" 文件名包含 'rgb'，应为RGB模型")
            if not rgb_capable:
                print("   ️ 警告: 文件名提示RGB但模型是灰度!")
        elif 'gray' in filename_lower or 'grey' in filename_lower or 'ct' in filename_lower:
            print(" 文件名包含灰度相关词汇，应为灰度模型")
            if rgb_capable:
                print("   ️ 警告: 文件名提示灰度但模型是RGB!")
        else:
            print(" 文件名未明确指示通道类型")

         . 检查点元数据
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        print_section(". 检查点元数据", "-")

        if 'epoch' in checkpoint:
            print(f" 训练轮次: {checkpoint.get('epoch', '未知')}")

        if 'best_psnr' in checkpoint:
            best_psnr = checkpoint.get('best_psnr', .)
            if isinstance(best_psnr, torch.Tensor):
                best_psnr = best_psnr.item()
            print(f" 最佳PSNR: {best_psnr:.f}")

         . 输出总结
        print_section("分析完成", "=")
        print(" 模型通道数分析完成")
        print(f" 模型类型: {'RGB (通道)' if rgb_capable else '灰度 (通道)'}")
        print(f" 建议用途: {'彩色图像超分' if rgb_capable else '灰度图像超分'}")

    except Exception as e:
        print(f" 分析检查点时出错: {e}")
        import traceback
        traceback.print_exc()


def batch_analyze_checkpoints(checkpoint_dir, device='cpu'):
    """
    批量分析目录中的检查点
    """
    if not os.path.exists(checkpoint_dir):
        print(f" 目录不存在: {checkpoint_dir}")
        return

    print_section(f"批量分析检查点目录: {checkpoint_dir}")

     收集所有.pth文件
    checkpoint_files = []
    for root, dirs, files in os.walk(checkpoint_dir):
        for file in files:
            if file.endswith('.pth'):
                checkpoint_files.append(os.path.join(root, file))

    if not checkpoint_files:
        print("️ 目录中没有找到.pth文件")
        return

    print(f" 找到 {len(checkpoint_files)} 个检查点文件")

     分析每个检查点
    results = []
    for i, ckpt_path in enumerate(sorted(checkpoint_files)):
        print(f"\n{'='}")
        print(f"分析文件 {i+}/{len(checkpoint_files)}: {os.path.basename(ckpt_path)}")
        print(f"{'='}")

        try:
            input_channels, found_key, _ = analyze_model_channels(ckpt_path, device)
            rgb_capable, rgb_message = check_model_rgb_capability({}, input_channels, found_key) if input_channels else (False, "分析失败")

            results.append({
                'file': os.path.basename(ckpt_path),
                'path': ckpt_path,
                'channels': input_channels,
                'rgb_capable': rgb_capable,
                'message': rgb_message
            })

        except Exception as e:
            print(f" 分析失败: {e}")
            results.append({
                'file': os.path.basename(ckpt_path),
                'path': ckpt_path,
                'channels': None,
                'rgb_capable': False,
                'message': f"分析失败: {e}"
            })

     输出总结报告
    print_section("批量分析总结报告", "=")

    rgb_models = [r for r in results if r.get('channels') == ]
    gray_models = [r for r in results if r.get('channels') == ]
    other_models = [r for r in results if r.get('channels') not in [, , None]]
    failed_models = [r for r in results if r.get('channels') is None]

    print(f" 统计:")
    print(f"  RGB模型 (通道): {len(rgb_models)} 个")
    print(f"  灰度模型 (通道): {len(gray_models)} 个")
    print(f"  其他通道模型: {len(other_models)} 个")
    print(f"  分析失败: {len(failed_models)} 个")

    if rgb_models:
        print(f"\n RGB模型列表:")
        for r in rgb_models[:]:   只显示前个
            print(f"  - {r['file']}")
        if len(rgb_models) > :
            print(f"  ... 还有 {len(rgb_models)-} 个")

    if gray_models:
        print(f"\n 灰度模型列表:")
        for g in gray_models[:]:
            print(f"  - {g['file']}")
        if len(gray_models) > :
            print(f"  ... 还有 {len(gray_models)-} 个")

    if failed_models:
        print(f"\n 分析失败的模型:")
        for f in failed_models[:]:
            print(f"  - {f['file']}: {f['message']}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="PyTorch检查点文件分析工具 - 专门检查模型通道数"
    )
    parser.add_argument("checkpoint", help="检查点文件路径或目录")
    parser.add_argument("--device", default="cpu", help="设备 (cpu/cuda)")
    parser.add_argument("--batch", action="store_true", help="批量分析目录中的所有检查点")

    args = parser.parse_args()

    if not os.path.exists(args.checkpoint):
        print(f" 路径不存在: {args.checkpoint}")
        sys.exit()

    if args.batch and os.path.isdir(args.checkpoint):
        batch_analyze_checkpoints(args.checkpoint, args.device)
    elif os.path.isfile(args.checkpoint):
        analyze_checkpoint(args.checkpoint, args.device)
    else:
        print(f" 路径不是文件: {args.checkpoint}")
        print("   使用 --batch 参数分析目录")
        sys.exit()


if __name__ == "__main__":
    main()
