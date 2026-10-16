import torch


def print_ckpt_structure(ckpt, prefix=""):
    """递归打印 ckpt 结构。tensor 只打印 shape，避免刷屏。"""
    if not isinstance(ckpt, dict):
        print(f"{prefix}{type(ckpt)}")
        return

    for key, value in ckpt.items():
        if isinstance(value, dict):
            print(f"{prefix}{key}: (dict, {len(value)} keys)")
            print_ckpt_structure(value, prefix + "  ")
        elif isinstance(value, torch.Tensor):
            print(f"{prefix}{key}: Tensor{tuple(value.shape)} {value.dtype}")
        else:
            print(f"{prefix}{key}: {type(value).__name__} = {repr(value)[:80]}")


if __name__ == "__main__":
    ckpt_path = './output_divk/ckp_rgb/best_model.pth'
    ckpt = torch.load(ckpt_path, map_location='cpu')

    print("权重文件中的键：", list(ckpt.keys()))
    print("=" * 60)
    print_ckpt_structure(ckpt)
