from thop import profile
from model_cpu import LUMWCNN_CPU
import torch
your_model = LUMWCNN_CPU()
 计算 FLOPs 和 Params
input = torch.randn(, , , )  根据你的输入尺寸改
flops, params = profile(your_model, inputs=(input, ))
print(f"FLOPs: {flops / e:.f} G")   转换成 GFLOPs
print(f"Params: {params / e:.f} M")  转换成 Million
