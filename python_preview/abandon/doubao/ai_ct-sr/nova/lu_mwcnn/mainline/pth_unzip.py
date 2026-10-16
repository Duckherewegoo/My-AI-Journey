import torch
import os
from typing import Dict, Any


def inspect_pth_weights(pth_path: str, save_to_file: bool = True) -> Dict[str, Any]:
    """
    读取并解析 .pth 权重文件的完整信息（兼容 torch.save(model.state_dict()) / checkpoint）
    :param pth_path: pth权重文件路径
    :param save_to_file: 是否将完整信息保存为 txt
    :return: 权重完整信息字典
    """
     ===================== . 加载权重（强制CPU，适配你的环境） =====================
    if not os.path.exists(pth_path):
        raise FileNotFoundError(f" 文件不存在：{pth_path}")

    print(f" 正在加载权重：{pth_path}")
    try:
         兼容CPU推理，强制加载到内存
        checkpoint = torch.load(pth_path, map_location=torch.device("cpu"))
    except Exception as e:
        raise RuntimeError(f" 加载失败：{str(e)}")

     ===================== . 自动识别权重类型 =====================
    weight_info = {
        "file_path": pth_path,
        "file_name": os.path.basename(pth_path),
        "weight_type": "",
        "total_params": ,
        "layers": [],
        "extra_info": {}
    }

     情况：是训练断点（包含 model_state_dict / epoch / optimizer 等）
    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        weight_info["weight_type"] = "训练断点 checkpoint"
        state_dict = checkpoint["model_state_dict"]
         提取额外训练信息
        for key in ["epoch", "optimizer_state_dict", "loss"]:
            if key in checkpoint:
                weight_info["extra_info"][key] = checkpoint[key]

     情况：纯模型权重（你直接保存的 model.state_dict()）
    elif isinstance(checkpoint, dict):
        weight_info["weight_type"] = "纯模型权重 state_dict"
        state_dict = checkpoint

    else:
        raise TypeError(" 不支持的权重格式")

     ===================== . 解析每一层参数 =====================
    total_params = 
    print("\n" + "="  )
    print(f" 权重类型：{weight_info['weight_type']}")
    print(f" 文件名：{weight_info['file_name']}")
    print("="  )
    print(f"{'序号':<} {'层名称':<} {'形状':<} {'参数数量':<}")
    print("-"  )

    for idx, (layer_name, tensor) in enumerate(state_dict.items(), ):
         层形状
        shape = list(tensor.shape)
         该层参数数量
        param_count = tensor.numel()
        total_params += param_count

         权重统计信息
        stats = {
            "min": round(tensor.min().item(), ),
            "max": round(tensor.max().item(), ),
            "mean": round(tensor.mean().item(), )
        }

         保存层信息
        layer_info = {
            "index": idx,
            "name": layer_name,
            "shape": shape,
            "param_count": param_count,
            "stats": stats
        }
        weight_info["layers"].append(layer_info)

         控制台打印
        print(f"{idx:<} {layer_name:<} {str(shape):<} {param_count:<}")

    weight_info["total_params"] = total_params

     ===================== . 输出统计结果 =====================
    print("-"  )
    print(f" 模型总参数量：{total_params:,}")
    print(f" 模型总层数：{len(weight_info['layers'])}")
    print("="  )

     额外信息打印
    if weight_info["extra_info"]:
        print("\n 训练额外信息：")
        for k, v in weight_info["extra_info"].items():
            print(f"  - {k}: {v if not isinstance(v, dict) else '字典数据'}")

     ===================== . 保存完整信息到 TXT =====================
    if save_to_file:
        save_path = os.path.splitext(pth_path)[] + "_权重完整信息.txt"
        with open(save_path, "w", encoding="utf-") as f:
            f.write("="   + "\n")
            f.write(f"医学影像模型 PTH 权重完整信息\n")
            f.write(f"权重文件：{weight_info['file_name']}\n")
            f.write(f"权重类型：{weight_info['weight_type']}\n")
            f.write("="   + "\n\n")

            f.write(f"总参数量：{total_params:,}\n")
            f.write(f"总层数：{len(weight_info['layers'])}\n\n")

            f.write("-"   + "\n")
            f.write(f"{'序号':<} {'层名称':<} {'形状':<} {'参数数量':<}\n")
            f.write("-"   + "\n")
            for layer in weight_info["layers"]:
                f.write(f"{layer['index']:<} {layer['name']:<} {str(layer['shape']):<} {layer['param_count']:<}\n")
            f.write("-"   + "\n\n")

            if weight_info["extra_info"]:
                f.write("训练额外信息：\n")
                for k, v in weight_info["extra_info"].items():
                    f.write(f"  - {k}: {v}\n")

        print(f"\n 完整信息已保存至：{save_path}")

    print("\n 权重信息解析完成！")
    return weight_info


 ===================== 【使用示例】 =====================
if __name__ == "__main__":
     替换成你的 PTH 文件路径
    PTH_FILE = r"/home/dake/Documents/Project/Graduction_Projects/codes/nova/lu_mwcnn/mainline/continual_ckpt/luna/luna_ct_epoch_.pth"

     执行解析
    info = inspect_pth_weights(PTH_FILE, save_to_file=True)

     也可以单独获取总参数量
    print(f"\n 模型总参数量：{info['total_params']:,}")
