"""
    DeepLesion 数据集自定义 collate_fn
    兼容 dataset 返回 2 元组（train）或 3 元组（val/test）的情况
"""
import logging

import torch
from torch.utils.data.dataloader import default_collate


logger = logging.getLogger(__name__)


# ===================== 兜底张量的形状 =====================
# 仅当 dataset 意外返回非张量时才用，正常不会触发
# 按你项目的 3060 8GB 推荐配置
CROP_SIZE = 128          # 与 DeepLesionDataset 的 crop_size 一致
SCALE_FACTOR = 4         # 与 DeepLesionDataset 的 scale_factor 一致


def deeplesion_collate_fn(batch):
    """
    自定义 DataLoader 拼接函数：
      - 自动适配 train（2 值）/ val/test（3 值）
      - 过滤 None 值，确保只拼接张量
      - 非张量样本用零张量兜底，避免整批崩溃
    """
    lr_batch = []
    hr_batch = []
    filename_batch = []
    has_filename = False

    for item in batch:
        # ---- 解包 ----
        if len(item) == 2:
            lr, hr = item
            fname = None
        elif len(item) == 3:
            lr, hr, fname = item
            has_filename = True
        else:
            logger.error(f"无效的样本格式：{type(item)}，长度={len(item)}")
            continue

        # ---- LR 兜底 ----
        if isinstance(lr, torch.Tensor):
            lr_batch.append(lr)
        else:
            logger.warning(f"非张量 LR 样本，替换为零张量：{type(lr)}")
            lr_batch.append(torch.zeros(
                (1, CROP_SIZE // SCALE_FACTOR, CROP_SIZE // SCALE_FACTOR),
                dtype=torch.float32))

        # ---- HR 兜底 ----
        if isinstance(hr, torch.Tensor):
            hr_batch.append(hr)
        else:
            logger.warning(f"非张量 HR 样本，替换为零张量：{type(hr)}")
            hr_batch.append(torch.zeros(
                (1, CROP_SIZE, CROP_SIZE),
                dtype=torch.float32))

        # ---- 文件名收集 ----
        if fname is not None:
            filename_batch.append(fname)

    # ---- 拼接张量 ----
    lr_tensor = default_collate(lr_batch)
    hr_tensor = default_collate(hr_batch)

    # ---- 返回 ----
    if has_filename and len(filename_batch) > 0:
        return lr_tensor, hr_tensor, filename_batch
    else:
        return lr_tensor, hr_tensor
