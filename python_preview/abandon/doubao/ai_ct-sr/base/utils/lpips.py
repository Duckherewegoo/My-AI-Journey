'''
    自然图像感知损失计算
'''
from lpips import LPIPS

# 全局单例：模块加载时创建，避免每次调用重新加载 VGG
lpips = LPIPS(net='vgg')
lpips.eval()


def calc_lpips(img1, img2):
    """
    计算 LPIPS 感知距离

    Args:
        img1, img2: torch.Tensor，形状 (N, C, H, W)，值域 [-1, 1]

    Returns:
        scalar tensor：感知距离均值
    """
    return lpips(img1, img2).detach().cpu().squeeze().mean()
