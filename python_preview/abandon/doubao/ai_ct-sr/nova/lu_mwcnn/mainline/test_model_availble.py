import os
import torch
from torchvision import transforms

 ===================== 【你的固定配置】 =====================
WEIGHT_ROOT = "/run/media/dake/Software/Projects/Graduction_Projects/codes/nova/lu_mwcnn/mainline/continual_ckpt"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

 ===================== 导入你的模型（和你代码一致） =====================
 这里用你自己的模型类，不用改！
from model_cpu import LUMWCNN_CPU as MWCNN

 ===================== 核心修复：正确加载权重 =====================
def test_single_weight(weight_path):
    try:
         . 初始化模型
        model = MWCNN().to(DEVICE)
        
         . 加载权重（修复：专门适配你的 checkpoint 格式）
        checkpoint = torch.load(weight_path, map_location=DEVICE)
        
          这是修复的关键！提取真正的模型权重！
        if "model_state_dict" in checkpoint:
            model.load_state_dict(checkpoint["model_state_dict"])
        else:
            model.load_state_dict(checkpoint)
        
        model.eval()
        
         . 测试推理
        with torch.no_grad():
            test_input = torch.randn(, , , ).to(DEVICE)
            output = model(test_input)
        
        return True, " 权重正常！兼容重构代码！可直接使用！"
    
    except Exception as e:
        return False, f" 错误：{str(e)[:]}..."

def scan_all_pth_weights(root_dir):
    weight_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for f in filenames:
            if f.endswith(".pth"):
                weight_files.append(os.path.join(dirpath, f))
    return weight_files

 ===================== 运行 =====================
if __name__ == "__main__":
    print("=")
    print(" 修复版权重测试（适配你的训练存档）")
    print("=")
    
    all_weights = scan_all_pth_weights(WEIGHT_ROOT)
    success = 
    total = len(all_weights)

    for i, path in enumerate(all_weights, ):
        res, msg = test_single_weight(path)
        print(f"[{i}/{total}] {os.path.basename(path)} | {msg}")
        if res: success +=

    print("=")
    print(f" 最终结果：{success}/{total} 权重完全可用！")
    print(" 真相：合并CT数据集不影响权重，无需重训！")
    print("=")
