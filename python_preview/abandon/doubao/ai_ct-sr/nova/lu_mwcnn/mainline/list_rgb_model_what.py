import torch
ckp = torch.load("./best_pth/rgb_best_model.pth", map_location="cpu")
sd = ckp["model_state_dict"] if "model_state_dict" in ckp else ckp
print("总 key 数:", len(sd))
print("有 upsample 吗:", any("upsample" in k for k in sd))
print("所有顶层模块:", sorted(set(k.split(".")[0] for k in sd)))
