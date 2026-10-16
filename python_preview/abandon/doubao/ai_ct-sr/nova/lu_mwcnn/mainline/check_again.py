import torch
import os
from model_cpu import LUMWCNN_CPU   替换成你的模型文件名

 权重路径
WEIGHT_PATH = "/run/media/dake/Software/Projects/Graduction_Projects/codes/nova/lu_mwcnn/mainline/continual_ckpt/luna/luna_ct_epoch_.pth"

 加载模型
model = LUMWCNN_CPU()

 尝试加载权重（宽松模式）
try:
    checkpoint = torch.load(WEIGHT_PATH, map_location="cpu", weights_only=False)
     提取模型参数
    state_dict = checkpoint["model_state_dict"] if "model_state_dict" in checkpoint else checkpoint
    
     加载权重（不严格匹配）
    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    
    print("=")
    print(" 权重加载兼容性测试结果")
    print("=")
    print(f" 缺失参数（模型有，权重无）: {len(missing)} 个")
    print(f" 多余参数（权重有，模型无）: {len(unexpected)} 个")
    print("\n缺失参数（BatchNorm为主，新增层）：")
    for m in missing[:]: print(f"  - {m}")
    print("\n多余参数（Dropout为主，训练时的层）：")
    for u in unexpected[:]: print(f"  - {u}")
    print("=")
    print(" 结论：权重结构不兼容，无法使用！")
    
except Exception as e:
    print(f" 加载失败: {str(e)}")

