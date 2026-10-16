import os
import torch
from torch.utils.tensorboard import SummaryWriter
import numpy as np
from skimage.metrics import peak_signal_noise_ratio as psnr
from skimage.metrics import structural_similarity as ssim


class TBLogger:
    def __init__(self, log_dir="./tb_logs"):
        """
        初始化TensorBoard日志记录器
        :param log_dir: 日志保存根目录
        """
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.writers = {}   不同数据集的writer分开存储

    def get_writer(self, dataset_type):
        """
        获取指定数据集的SummaryWriter
        :param dataset_type: 数据集类型（如luna_ct、covid_ct、voc_rgb）
        :return: SummaryWriter实例
        """
        if dataset_type not in self.writers:
            writer_dir = os.path.join(self.log_dir, dataset_type)
            self.writers[dataset_type] = SummaryWriter(writer_dir)
        return self.writers[dataset_type]

    @staticmethod
    def calculate_metrics(sr_img, hr_img, data_range=.):
        """
        计算PSNR和SSIM指标
        :param sr_img: 超分图像 (Tensor, BxCxHxW)
        :param hr_img: 高清图像 (Tensor, BxCxHxW)
        :param data_range: 数据范围（默认.，因为图像已归一化到[,]）
        :return: 平均PSNR、平均SSIM
        """
         转换为numpy数组并调整维度 (BxCxHxW -> BxHxWxC)
        sr_np = sr_img.detach().cpu().numpy().transpose(, , , )
        hr_np = hr_img.detach().cpu().numpy().transpose(, , , )

        psnr_vals = []
        ssim_vals = []

        for i in range(len(sr_np)):
             计算PSNR
            psnr_val = psnr(hr_np[i], sr_np[i], data_range=data_range)
            psnr_vals.append(psnr_val)

             计算SSIM（灰度图用通道，RGB图用multichannel=True）
            if sr_np[i].shape[-] == :
                ssim_val = ssim(hr_np[i][..., ], sr_np[i][..., ], data_range=data_range)
            else:
                ssim_val = ssim(hr_np[i], sr_np[i], data_range=data_range, multichannel=True, channel_axis=-)
            ssim_vals.append(ssim_val)

        return np.mean(psnr_vals), np.mean(ssim_vals)

    def log_batch_metrics(self, dataset_type, epoch, batch_idx, loss, psnr_val, ssim_val):
        """
        记录批次级别的指标
        :param dataset_type: 数据集类型
        :param epoch: 轮次
        :param batch_idx: 批次索引
        :param loss: 批次损失
        :param psnr_val: 批次PSNR
        :param ssim_val: 批次SSIM
        """
        global_step = epoch   + batch_idx   全局步数（避免不同轮次批次重叠）
        writer = self.get_writer(dataset_type)
        writer.add_scalar('train/batch_loss', loss, global_step)
        writer.add_scalar('train/batch_psnr', psnr_val, global_step)
        writer.add_scalar('train/batch_ssim', ssim_val, global_step)

    def log_epoch_metrics(self, dataset_type, epoch, avg_loss, avg_psnr, avg_ssim):
        """
        记录轮次级别的平均指标
        :param dataset_type: 数据集类型
        :param epoch: 轮次
        :param avg_loss: 平均损失
        :param avg_psnr: 平均PSNR
        :param avg_ssim: 平均SSIM
        """
        writer = self.get_writer(dataset_type)
        writer.add_scalar('train/epoch_loss', avg_loss, epoch)
        writer.add_scalar('train/epoch_psnr', avg_psnr, epoch)
        writer.add_scalar('train/epoch_ssim', avg_ssim, epoch)

    def close_all(self):
        """关闭所有SummaryWriter"""
        for writer in self.writers.values():
            writer.close()
