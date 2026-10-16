import torch
ckp = torch.load('./best_pth/rgb_best_model.pth', map_location='cpu')
for k, v in ckp['model_state_dict'].items():
    if v.dim() == 4:
        print(k, tuple(v.shape))   # 例如 (16, 3, 3, 3) 表示 in=3, out=16
