"""
debug_print_checkpoint_fixed.py
修复语法错误的检查点查看脚本
"""

import torch
import os
import sys
import argparse


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
         加载检查点
        print(f"️ 使用设备: {device}")
        checkpoint = torch.load(checkpoint_path,
                                map_location=device,
                                weights_only=False)

         . 检查点基本信息
        print_section(". 检查点基本信息", "-")
        print(f" 检查点键数量: {len(checkpoint)}")
        print(" 所有键:")
        for i, key in enumerate(checkpoint.keys()):
            print(f"  {i+:d}. {key}")

         . 训练状态
        print_section(". 训练状态", "-")
        training_keys = ['epoch', 'best_loss', 'best_psnr',
                         'best_ssim', 'best_lpips']

        for key in training_keys:
            if key in checkpoint:
                value = checkpoint[key]
                if isinstance(value, torch.Tensor):
                    value = value.item()
                print(f"  {key}: {value}")

         . 模型状态字典
        if 'model_state_dict' in checkpoint:
            print_section(". 模型状态字典", "-")
            model_state = checkpoint['model_state_dict']

            print(f" 模型参数数量: {len(model_state)}")

             参数统计
            total_params = 
            param_shapes = {}

            print("\n 模型参数详细信息 (前个):")
            header = f"{'参数名':<} {'形状':<} {'参数数量':<} {'数据类型':<}"
            print(header)
            print("-"  )

            for i, (name, param) in enumerate(model_state.items()):
                if i < :   只显示前个参数
                    shape = str(list(param.shape))
                    num_params = param.numel()
                    dtype = str(param.dtype).replace('torch.', '')

                    line = f"{name:<} {shape:<} {num_params:<,} {dtype:<}"
                    print(line)

                total_params += param.numel()
                shape_str = str(param.shape)
                param_shapes[shape_str] = param_shapes.get(shape_str, ) + 

            if len(model_state) > :
                remaining = len(model_state) - 
                print(f"... 还有 {remaining} 个参数未显示")

            print(f"\n 总模型参数数量: {total_params:,}")

             形状统计
            print("\n 参数形状统计:")
            sorted_shapes = sorted(param_shapes.items())[:]
            for shape, count in sorted_shapes:
                print(f"  {shape}: {count} 个")

            if len(param_shapes) > :
                remaining_shapes = len(param_shapes) - 
                print(f"  ... 还有 {remaining_shapes} 种形状")

         . 优化器状态字典
        if 'optimizer_state_dict' in checkpoint:
            print_section(". 优化器状态字典", "-")
            optimizer_state = checkpoint['optimizer_state_dict']

            print(f"优化器状态字典键: {list(optimizer_state.keys())}")

            if 'param_groups' in optimizer_state:
                param_groups = optimizer_state['param_groups']
                print(f"\n 参数组数量: {len(param_groups)}")

                for i, group in enumerate(param_groups):
                    print(f"\n 参数组 {i}:")
                    print(f"  ├─ 参数数量: {len(group['params'])}")

                     显示超参数
                    hyperparams = {k: v for k, v in group.items()
                                   if k != 'params'}

                    for key, value in hyperparams.items():
                        if isinstance(value, torch.Tensor):
                            value = value.item()
                        print(f"  ├─ {key}: {value}")

                     显示参数ID
                    param_ids = group['params']
                    param_ids_str = str(param_ids[:])

                    if len(param_ids) > :
                        param_ids_str += "..."

                    print(f"  └─ 参数ID: {param_ids_str}")

            if 'state' in optimizer_state:
                state_dict = optimizer_state['state']
                print(f"\n 状态条目数量: {len(state_dict)}")

                 显示前几个状态
                print("\n 状态条目示例 (前个):")
                state_items = list(state_dict.items())[:]

                for i, (param_id, state) in enumerate(state_items):
                    print(f"  ├─ 参数ID: {param_id}")

                    for key, value in state.items():
                        if isinstance(value, torch.Tensor):
                            shape_str = str(list(value.shape))
                            print(f"  │  ├─ {key}: 张量 {shape_str}")
                        elif isinstance(value, (int, float)):
                            print(f"  │  ├─ {key}: {value}")
                        else:
                            type_name = type(value).__name__
                            print(f"  │  ├─ {key}: {type_name}")

                    if len(state) > :
                        print("  │  └─ ...")
                    else:
                        print("  │")

                if len(state_dict) > :
                    remaining_states = len(state_dict) - 
                    print(f"  └─ ... 还有 {remaining_states} 个状态条目")

         . 调度器状态字典
        scheduler_key = 'scheduler_state_dict'
        if scheduler_key in checkpoint and checkpoint[scheduler_key] is not None:
            print_section(". 调度器状态字典", "-")
            scheduler_state = checkpoint[scheduler_key]

            print(f"调度器状态字典键: {list(scheduler_state.keys())}")

            for key, value in scheduler_state.items():
                if isinstance(value, torch.Tensor):
                    shape_str = str(list(value.shape))
                    print(f"  {key}: 张量 {shape_str}")
                elif isinstance(value, (int, float)):
                    print(f"  {key}: {value}")
                elif isinstance(value, list):
                    print(f"  {key}: 列表 [{len(value)} 个元素]")
                else:
                    type_name = type(value).__name__
                    print(f"  {key}: {type_name}")

         . 内存使用分析
        print_section(". 内存使用分析", "-")

         估算内存使用
        memory_estimate = 
        tensor_info = []

        def estimate_memory(obj, path=""):
            nonlocal memory_estimate
            if isinstance(obj, torch.Tensor):
                mem = obj.element_size()  obj.nelement()
                memory_estimate += mem
                tensor_info.append({
                    'path': path,
                    'shape': obj.shape,
                    'dtype': obj.dtype,
                    'memory': mem
                })
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    new_path = f"{path}.{k}" if path else k
                    estimate_memory(v, new_path)
            elif isinstance(obj, (list, tuple)):
                for i, v in enumerate(obj):
                    new_path = f"{path}[{i}]" if path else f"[{i}]"
                    estimate_memory(v, new_path)

        estimate_memory(checkpoint)

        print(f" 总内存估计: {format_size(memory_estimate)}")

         按内存排序显示最大的张量
        if tensor_info:
            print(f"\n 最大的张量 (前个):")
            tensor_info.sort(key=lambda x: x['memory'], reverse=True)

            for i, info in enumerate(tensor_info[:]):
                shape_str = " × ".join(str(d) for d in info['shape'])
                memory_str = format_size(info['memory'])
                print(f"  {i+}. {info['path']}: {shape_str} "
                      f"({info['dtype']}), {memory_str}")

         . 保存格式和版本
        print_section(". 保存格式信息", "-")

         检查是否有保存的模型架构
        model_class_keys = ['_model_class', 'model_class', 'model_type']
        has_model_class = any(k in checkpoint for k in model_class_keys)

        print(f" 是否包含模型类信息: {'是' if has_model_class else '否'}")

         检查保存的设备
        print(f" 保存时使用的设备:")

        for k, v in checkpoint.items():
            if isinstance(v, torch.Tensor):
                print(f"  {k}: 设备 {v.device}")
                break

         . 完整性检查
        print_section(". 完整性检查", "-")

         检查必需键
        required_keys = ['model_state_dict', 'optimizer_state_dict']
        missing_keys = [k for k in required_keys if k not in checkpoint]

        if missing_keys:
            print(f" 缺少必需键: {missing_keys}")
        else:
            print(" 包含所有必需键")

         检查模型和优化器参数匹配
        model_key = 'model_state_dict'
        optimizer_key = 'optimizer_state_dict'

        if model_key in checkpoint and optimizer_key in checkpoint:
            model_params = set(checkpoint[model_key].keys())

             获取优化器中的所有参数ID
            optimizer_param_ids = set()
            if 'param_groups' in checkpoint[optimizer_key]:
                for group in checkpoint[optimizer_key]['param_groups']:
                    optimizer_param_ids.update(group['params'])

            print(f" 模型参数数量: {len(model_params)}")
            print(f" 优化器参数ID数量: {len(optimizer_param_ids)}")

            if optimizer_param_ids:
                 尝试计算匹配的参数数量
                model_param_ids = {id(param) for param
                                   in checkpoint[model_key].values()}

                matched_ids = model_param_ids.intersection(optimizer_param_ids)
                matched_count = len(matched_ids)
                total_optimizer = len(optimizer_param_ids)
                print(f"存在的id: {model_param_ids}")
                print(f" 匹配的参数ID数量: {matched_count} / {total_optimizer}")

        print_section("分析完成", "=")

    except Exception as e:
        print(f" 加载检查点时出错: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description="PyTorch检查点文件分析工具"
    )
    parser.add_argument("checkpoint", help="检查点文件路径")
    parser.add_argument("--device", default="cpu",
                        help="设备 (cpu/cuda)")

    args = parser.parse_args()

    if not os.path.exists(args.checkpoint):
        print(f" 检查点文件不存在: {args.checkpoint}")
        sys.exit()

    analyze_checkpoint(args.checkpoint, args.device)


if __name__ == "__main__":
    main()
