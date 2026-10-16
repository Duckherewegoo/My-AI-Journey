import torch
import cv
import numpy as np
from PIL import Image
from torchvision import transforms
import torch.nn as nn
 加载模型（和训练时的定义一致）


class LUMWCNN(nn.Module):
    def __init__(self, in_channels=, upscale_factor=):
        super().__init__()
        self.upscale_factor = upscale_factor
        self.features = nn.Sequential(
            nn.Convd(in_channels, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True),
            nn.Convd(, , kernel_size=, padding=),
            nn.ReLU(inplace=True)
        )
        self.upsample = nn.Sequential(
            nn.Convd(,   (upscale_factor), kernel_size=, padding=),
            nn.PixelShuffle(upscale_factor),
            nn.Convd(, in_channels, kernel_size=, padding=),
            nn.Sigmoid()
        )

    def forward(self, x):
        features = self.features(x)
        out = self.upsample(features)
        return out


 加载最佳模型权重
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = LUMWCNN(in_channels=, upscale_factor=).to(device)
model.load_state_dict(torch.load('./output_divk_opt/best_model.pth')['model'])
model.eval()

 测试单张图像


def super_resolve_image(image_path, output_path):
     加载并预处理图像
    img = Image.open(image_path).convert('RGB')
    transform = transforms.ToTensor()
    lr_tensor = transform(img).unsqueeze().to(device)   [,,H,W]

     超分推理
    with torch.no_grad():
        hr_tensor = model(lr_tensor)

     转换为图像并保存
    hr_img = hr_tensor.squeeze().cpu().numpy().transpose(, , )
    hr_img = (hr_img  ).astype(np.uint)
    cv.imwrite(output_path, cv.cvtColor(hr_img, cv.COLOR_RGBBGR))
    print(f"超分图像已保存到: {output_path}")


 使用示例
super_resolve_image("./cat_test.png", "cat_hr.png")
