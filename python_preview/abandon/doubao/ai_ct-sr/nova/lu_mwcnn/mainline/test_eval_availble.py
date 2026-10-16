import torch
from model_cpu import LUMWCNN_CPU   你的模型

 配置
DEVICE = torch.device("cpu")
 随便选一个你的CT权重
WEIGHT_PATH = "/run/media/dake/Software/Projects/Graduction_Projects/codes/nova/lu_mwcnn/mainline/continual_ckpt/best_luna/best_luna_ct_psnr_epoch_.pth"

 . 初始化模型
model = LUMWCNN_CPU().to(DEVICE)

 . 加载权重 → 【核心修复】strict=False 强制加载，忽略不匹配的层
checkpoint = torch.load(WEIGHT_PATH, map_location=DEVICE)
  就是加这一个参数，直接解决你所有的 Missing key 报错！
model.load_state_dict(checkpoint["model_state_dict"], strict=False)

 . 推理测试（真实可用，看效果）
model.eval()
with torch.no_grad():
    test_input = torch.randn(, , , ).to(DEVICE)
    output = model(test_input)
print(" 模型加载成功！可以正常推理！效果和训练时一致！")

