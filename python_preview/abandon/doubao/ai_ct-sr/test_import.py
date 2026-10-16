import torch

from base import DWSR, LPIPS, calc_psnr
from base.utils.meters import AverageMeter


def test():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 模型
    model = DWSR().to(device).eval()

    # 指标
    lpips_metric = LPIPS().to(device).eval()
    psnr_meter = AverageMeter()

    # 假数据：batch=1, 1 通道, 64x64
    lr = torch.rand(1, 1, 64, 64).to(device)
    hr = torch.rand(1, 1, 256, 256).to(device)

    with torch.no_grad():
        sr = model(lr)

        # 尺寸对齐，防止 SR 和 HR 差一两个像素
        mh = min(sr.shape[-2], hr.shape[-2])
        mw = min(sr.shape[-1], hr.shape[-1])
        sr_c = sr[..., :mh, :mw]
        hr_c = hr[..., :mh, :mw]

        psnr_val = calc_psnr(sr_c, hr_c)
        lpips_val = lpips_metric(sr_c, hr_c).mean().item()

    psnr_meter.update(psnr_val)

    print(f"SR shape   : {tuple(sr.shape)}")
    print(f"PSNR       : {psnr_meter.avg:.2f} dB")
    print(f"LPIPS      : {lpips_val:.4f}")


if __name__ == "__main__":
    test()
