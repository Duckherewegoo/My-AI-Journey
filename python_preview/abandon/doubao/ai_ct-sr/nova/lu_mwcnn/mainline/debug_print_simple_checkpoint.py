"""
simple_checkpoint_viewer.py
简化版检查点查看工具
"""

import torch
import os
import sys


def print_dict_structure(d, indent=, max_items=):
    """递归打印字典结构"""
    prefix = "  "  indent

    if isinstance(d, dict):
        for i, (key, value) in enumerate(d.items()):
            if i >= max_items:
                print(f"{prefix}... 还有 {len(d) - max_items} 项")
                break

            print(f"{prefix}{key}: ", end="")
            if isinstance(value, (dict, list, tuple)):
                print(f"{type(value).__name__} ({len(value)})")
                if isinstance(value, dict) and indent < :   限制递归深度
                    print_dict_structure(value, indent + , max_items)
            elif isinstance(value, torch.Tensor):
                print(f"Tensor {list(value.shape)}")
            else:
                print(f"{type(value).__name__}: {value}")
    elif isinstance(d, (list, tuple)):
        for i, value in enumerate(d[:max_items]):
            print(f"{prefix}[{i}]: {type(value).__name__}")
    else:
        print(f"{prefix}{type(d).__name__}: {d}")


def main():
    if len(sys.argv) < :
        print("用法: python simple_checkpoint_viewer.py <checkpoint_path>")
        sys.exit()

    checkpoint_path = sys.argv[]

    if not os.path.exists(checkpoint_path):
        print(f"检查点文件不存在: {checkpoint_path}")
        sys.exit()

    print(f" 检查点文件: {checkpoint_path}")
    print(f" 文件大小: {os.path.getsize(checkpoint_path) / :.f} MB")
    print("="  )

    try:
         加载检查点
        checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)

        print(" 检查点结构:")
        print_dict_structure(checkpoint)

        print("\n" + "="  )

         显示具体信息
        if 'epoch' in checkpoint:
            print(f" 训练轮次: {checkpoint['epoch']}")

        if 'best_psnr' in checkpoint:
            print(f" 最佳PSNR: {checkpoint['best_psnr']}")

        if 'best_ssim' in checkpoint:
            print(f" 最佳SSIM: {checkpoint['best_ssim']}")

        if 'best_lpips' in checkpoint:
            print(f" 最佳LPIPS: {checkpoint['best_lpips']}")

        if 'model_state_dict' in checkpoint:
            model_state = checkpoint['model_state_dict']
            print(f"\n 模型参数: {len(model_state)} 个")

             计算总参数
            total_params = 
            for param in model_state.values():
                total_params += param.numel()
            print(f" 总参数数量: {total_params:,}")

             显示前几个参数
            print("\n 前个参数:")
            for i, (name, param) in enumerate(list(model_state.items())[:]):
                print(f"  {i+}. {name}: {list(param.shape)}")

        if 'optimizer_state_dict' in checkpoint:
            optimizer_state = checkpoint['optimizer_state_dict']
            print(f"\n️  优化器状态:")

            if 'param_groups' in optimizer_state:
                param_groups = optimizer_state['param_groups']
                print(f"  参数组数量: {len(param_groups)}")

                for i, group in enumerate(param_groups):
                    params = len(group['params'])
                    lr = group.get('lr', 'N/A')
                    print(f"  组{i}: {params}个参数, 学习率: {lr}")

            if 'state' in optimizer_state:
                states = len(optimizer_state['state'])
                print(f"  状态条目: {states}个")

    except Exception as e:
        print(f" 加载检查点时出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
