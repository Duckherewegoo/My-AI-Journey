from train_wavelet import load_model_for_inference, infer_image
import numpy as np
import torch
import warnings
 抑制无关警告（LPIPS/torchvision）
warnings.filterwarnings("ignore", category=UserWarning, module="torchvision")
warnings.filterwarnings("ignore", category=UserWarning, module="lpips")
warnings.filterwarnings("ignore", category=FutureWarning, module="torch")

 解决numpy标量的安全加载问题（可选，推荐）
torch.serialization.add_safe_globals([np._core.multiarray.scalar])


 ========== 核心修复：重新定义load_model_for_inference（适配PyTorch .+） ==========

def load_model_for_inference_fixed(model_path, image_mode='color', device=None):
    """
    修复PyTorch .+的weights_only加载问题，适配超分模型
    """
    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

     初始化模型
    in_channels =  if image_mode == 'color' else 
     从modell.py导入LUMWCNN（确保模型定义可访问）
    from modell import LUMWCNN
    model = LUMWCNN(in_channels=in_channels, scale=, device=device)   scale根据训练时的参数调整
    model = model.to(device)

     修复：设置weights_only=False（信任该checkpoint的前提下）
     或使用add_safe_globals后仍用weights_only=True（更安全）
    ckpt = torch.load(
        model_path,
        map_location=device,
        weights_only=False   关键修复：关闭weights_only限制
         weights_only=True   若已执行add_safe_globals，也可保留True
    )

     兼容两种保存格式：包含model键的checkpoint / 直接保存的state_dict
    if 'model' in ckpt:
        model.load_state_dict(ckpt['model'])
    else:
        model.load_state_dict(ckpt)

    model.eval()
    print(f" 模型加载成功！设备：{device} | 图像模式：{image_mode}")
    return model


 ========== 测试推理 ==========
if __name__ == "__main__":
     加载模型（使用修复后的函数）
    model = load_model_for_inference_fixed(
        './output_divk_wavelet/best_model.pth',
        image_mode='color'
    )

     单张图像推理
    output_img = infer_image(model, 'Hachimi.jpg', image_mode='color')

     保存结果
    output_img.save('test_output.jpg')
    print(f" 超分推理完成！结果已保存为 test_output.jpg")
