"""联合损失：MSE + SSIM + LPIPS，可选 PixelShuffle 上采样（RGB 版用）"""
import torch
import torch.nn as nn
from torchmetrics.image import StructuralSimilarityIndexMeasure


class JointLoss(nn.Module):
    def __init__(self, lpips_model, alpha=1.0, beta=0.1, gamma=0.1,
                 in_channels=1, need_upsample=False):
        super().__init__()
        self.alpha, self.beta, self.gamma = alpha, beta, gamma
        self.mse = nn.MSELoss()
        self.lpips_model = lpips_model
        self.need_upsample = need_upsample

        self.ssim_metric = StructuralSimilarityIndexMeasure(
            kernel_size=11, sigma=1.5, data_range=1.0, k1=0.01, k2=0.03)

        if need_upsample:
            self.upsample_block = nn.Sequential(
                nn.Conv2d(in_channels, in_channels * 4, 3, 1, 1),
                nn.PixelShuffle(2),
                nn.Conv2d(in_channels, in_channels * 4, 3, 1, 1),
                nn.PixelShuffle(2))
        else:
            self.upsample_block = None

    def forward(self, sr, hr):
        if self.upsample_block is not None:
            sr = self.upsample_block(sr)

        h = min(sr.shape[2], hr.shape[2])
        w = min(sr.shape[3], hr.shape[3])
        sr, hr = sr[:, :, :h, :w], hr[:, :, :h, :w]

        mse = self.mse(sr, hr)
        self.ssim_metric = self.ssim_metric.to(sr.device)
        ssim = 1.0 - self.ssim_metric(sr, hr)

        if sr.shape[1] == 1:
            sr_l, hr_l = sr.repeat(1, 3, 1, 1), hr.repeat(1, 3, 1, 1)
        else:
            sr_l, hr_l = sr, hr
        lpips_val = self.lpips_model(sr_l, hr_l).mean()

        return self.alpha * mse + self.beta * ssim + self.gamma * lpips_val
