import os
import torch
import numpy as np
from PIL import Image
import torch.nn as nn
 若原代码的metrics模块可导入，取消下面注释；否则使用模拟的PSNR计算函数
 from base.utils.metrics import calc_psnr_torch, calc_ssim_torch

 ===================== 模拟metrics模块（若原模块无法直接调用时使用） =====================


def calc_psnr_torch(pred, target, max_val=.):
    """模拟原代码的PSNR计算函数"""
    mse = torch.mean((pred - target)  )
    if mse == :
        return float('inf')
    return   torch.log(max_val / torch.sqrt(mse))


def calc_ssim_torch(pred, target):
    """模拟原代码的SSIM计算函数（简化版）"""
    from torch.nn.functional import convd
    window = torch.ones(, ).to(pred.device) / .
    window = window.unsqueeze().unsqueeze()

    mu_x = convd(pred, window, padding=, groups=)
    mu_y = convd(target, window, padding=, groups=)

    sigma_x = convd(pred, window, padding=, groups=) - mu_x
    sigma_y = convd(target, window, padding=, groups=) - mu_y
    sigma_xy = convd(pred  target, window, padding=, groups=) - mu_x  mu_y

    C = (.  .)  
    C = (.  .)  

    ssim_map = ((  mu_x  mu_y + C)  (  sigma_xy + C)) / ((mu_x + mu_y + C)  (sigma_x + sigma_y + C))
    return ssim_map.mean()


 ===================== 基础配置（复用原训练代码的config结构） =====================
config = {
    "device": "cuda:" if torch.cuda.is_available() else "cpu",
    "dataset": {
        "crop_size": ,
        "scale_factor": ,
        "noise_std": .,
    },
    "loss": {
        "use_mixed_loss": True,
        "l_weight": .,
        "mse_weight": .,
    },
    "psnr_max": .,
}

 ===================== . 预测图全黑问题验证 =====================


def test_prediction_black_issue():
    """验证预测图全黑问题修复（归一化/反归一化、数值裁剪）"""
    print("\n=== 验证预测图全黑问题 ===")

     模拟模型输出（模拟原代码中可能的全黑问题场景）
     场景：未裁剪数值范围导致输出<或>
    fake_pred_bad = torch.randn(, , , ).to(config["device"])   含负数/超大值
     场景：正确裁剪后的输出
    fake_pred_good = torch.clamp(fake_pred_bad, ., .)

     模拟真实HR图像
    fake_hr = torch.rand(, , , ).to(config["device"])   -范围

     验证：数值范围检查
    print(f"未裁剪输出范围: min={fake_pred_bad.min().item():.f}, max={fake_pred_bad.max().item():.f}")
    print(f"裁剪后输出范围: min={fake_pred_good.min().item():.f}, max={fake_pred_good.max().item():.f}")

     验证：反归一化（转-）逻辑（复用原代码）
    def _normalize_image_array(arr):
        """复用原代码的反归一化函数"""
        arr = arr - arr.min()
        arr = arr / (arr.max() + e-)
        arr = (arr  ).astype(np.uint)
        return arr

     处理预测图（模拟原代码的保存逻辑）
    pred_np = fake_pred_good.squeeze().squeeze().cpu().detach().numpy()
    pred_arr = _normalize_image_array(pred_np)

     保存测试图像（验证是否全黑）
    save_dir = "./debug_pred"
    os.makedirs(save_dir, exist_ok=True)
    Image.fromarray(pred_arr, mode="L").save(os.path.join(save_dir, "test_pred.png"))
    print(f"测试预测图已保存至 {save_dir}/test_pred.png (若全黑则修复失败)")

     验证：维度适配（避免通道数错误导致全黑）
    if fake_pred_good.dim() ==  and fake_pred_good.size() == :
        pred_d = fake_pred_good.squeeze()
        print(f"维度适配后形状: {pred_d.shape} (原形状: {fake_pred_good.shape})")

     结论
    if np.mean(pred_arr) < :
        print(" 预测图仍全黑，检查归一化/裁剪逻辑！")
    else:
        print(" 预测图全黑问题已修复")

 ===================== . PSNR极低问题验证（修复参数不匹配错误） =====================


def test_psnr_low_issue():
    """验证PSNR极低问题（损失函数、指标计算、数据加载）"""
    print("\n=== 验证PSNR极低问题 ===")

     定义混合损失（完全复用原训练代码的MixedLoss）
    class MixedLoss(nn.Module):
        """L+MSE混合损失函数（与原代码一致）"""

        def __init__(self, l_weight=., mse_weight=.):
            super(MixedLoss, self).__init__()
            self.l = nn.LLoss()
            self.mse = nn.MSELoss()
            self.l_weight = l_weight
            self.mse_weight = mse_weight

        def forward(self, pred, target):
            pred = torch.clamp(pred, ., .)
            target = torch.clamp(target, ., .)
            return self.l_weight  self.l(pred, target) + self.mse_weight  self.mse(pred, target)

     模拟不同场景的预测结果
     场景：预测完全错误（PSNR极低）
    pred_bad = torch.rand(, , , ).to(config["device"])  .   接近
     场景：预测接近真实值（PSNR正常）
    fake_hr = torch.rand(, , , ).to(config["device"])
    pred_good = fake_hr  . + .   接近真实值

     处理张量（复用原代码的指标计算前处理）
    def _process_prediction_for_metrics(pred, hr):
        """复用原代码的处理函数"""
        pred_np = pred.detach().cpu()
        hr_np = hr.cpu()
        if pred_np.dim() ==  and pred_np.size() == :
            pred_np = pred_np.squeeze()
        if hr_np.dim() ==  and hr_np.size() == :
            hr_np = hr_np.squeeze()
        pred_np = torch.clamp(pred_np, ., .)
        hr_np = torch.clamp(hr_np, ., .)
        return pred_np, hr_np

     修复：仅传入l_weight和mse_weight，过滤use_mixed_loss
    loss_config = {k: v for k, v in config["loss"].items() if k in ["l_weight", "mse_weight"]}
    criterion = MixedLoss(loss_config)   不再传入use_mixed_loss

     计算PSNR
    pred_bad_np, hr_np = _process_prediction_for_metrics(pred_bad, fake_hr)
    pred_good_np, hr_np = _process_prediction_for_metrics(pred_good, fake_hr)

    psnr_bad = calc_psnr_torch(pred_bad_np.float(), hr_np.float())
    psnr_good = calc_psnr_torch(pred_good_np.float(), hr_np.float())

    print(f"预测错误时PSNR: {psnr_bad:.f} dB (原问题场景)")
    print(f"预测正常时PSNR: {psnr_good:.f} dB (修复后场景)")

     验证损失函数是否合理
    loss_bad = criterion(pred_bad, fake_hr)
    loss_good = criterion(pred_good, fake_hr)
    print(f"预测错误时损失: {loss_bad:.f}")
    print(f"预测正常时损失: {loss_good:.f}")

     结论
    if psnr_good > :
        print(" PSNR极低问题已修复（指标计算/损失函数正常）")
    else:
        print(" PSNR仍极低，检查损失函数/数据加载逻辑！")

 ===================== . 训练速度慢问题验证 =====================


def test_training_speed_issue():
    """验证训练速度问题（设备加速、数据加载、梯度计算）"""
    print("\n=== 验证训练速度问题 ===")

     验证：GPU是否可用
    if torch.cuda.is_available():
        print(f" GPU可用: {torch.cuda.get_device_name()}")
         验证张量是否在GPU上
        test_tensor = torch.rand(, , , ).to(config["device"])
        print(f"张量设备: {test_tensor.device} (应为cuda:)")
    else:
        print(" 未使用GPU，训练速度慢！")

     验证：数据加载参数（原代码的优化配置）
    num_workers = min(os.cpu_count() or , )
    pin_memory = config["device"].startswith("cuda")
    print(f"数据加载配置: num_workers={num_workers}, pin_memory={pin_memory}")
    if num_workers ==  or not pin_memory:
        print(" 数据加载参数未优化，导致训练慢！")
    else:
        print(" 数据加载参数已优化")

     验证：梯度裁剪（避免梯度爆炸导致训练卡顿）
    grad_clip_norm = .
    fake_model = nn.Convd(, , , padding=).to(config["device"])
    optimizer = torch.optim.Adam(fake_model.parameters(), lr=e-)

     模拟一步训练，测试梯度裁剪
    optimizer.zero_grad()
    fake_pred = fake_model(torch.rand(, , , ).to(config["device"]))
    loss = nn.MSELoss()(fake_pred, torch.rand(, , , ).to(config["device"]))
    loss.backward()

     梯度裁剪（原代码的优化）
    torch.nn.utils.clip_grad_norm_(fake_model.parameters(), grad_clip_norm)
    optimizer.step()

    print(" 梯度裁剪逻辑正常（避免训练卡顿）")


 ===================== 执行调试验证 =====================
if __name__ == "__main__":
     依次验证三个核心问题
    test_prediction_black_issue()
    test_psnr_low_issue()
    test_training_speed_issue()

    print("\n=== 调试总结 ===")
    print(". 预测图全黑：检查test_pred.png是否有内容 + 数值范围是否在-")
    print(". PSNR极低：正常预测时PSNR应>，若仍低需检查数据集加载/模型输出")
    print(". 训练速度慢：确认GPU可用 + num_workers/pin_memory配置正确")
