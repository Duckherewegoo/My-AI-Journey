'''
    计量器
'''


class AverageMeter:
    """滑动平均计量器，用于追踪训练指标（loss / PSNR / SSIM 等）"""

    def __init__(self):
        self.reset()

    def reset(self):
        """重置所有统计量"""
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0
        self.max = float('-inf')
        self.min = float('inf')
        self.var = 0
        self.std = 0
        self._sum_sq = 0    # 内部：平方和，用于正确计算方差

    def update(self, val, n=1):
        """
        批量更新统计量

        Args:
            val: 当前观测值（标量或张量）
            n:   批量样本数量（默认 1，支持 batch_size > 1 场景）
        """
        current_val = float(val)
        n = max(1, int(n))

        self.val = current_val
        self.sum += current_val * n
        self._sum_sq += (current_val ** 2) * n
        self.count += n
        self.avg = self.sum / self.count

        # max / min 更新（首次直接赋初值）
        if self.count > n:
            self.max = max(self.max, current_val)
            self.min = min(self.min, current_val)
        else:
            self.max = current_val
            self.min = current_val

        # 样本方差（Bessel 校正）
        if self.count > 1:
            mean_sq = self._sum_sq / self.count
            mean = self.avg
            self.var = (mean_sq - mean ** 2) * (self.count / (self.count - 1))
            self.std = self.var ** 0.5

    def get_stats(self):
        """获取完整统计信息字典"""
        return {
            'current':  self.val,
            'average':  self.avg,
            'total':    self.sum,
            'count':    self.count,
            'max':      self.max,
            'min':      self.min,
            'variance': self.var,
            'std_dev':  self.std,
        }

    def __repr__(self):
        """更友好的字符串表示"""
        return (f"AvgMeter(val={self.val:.4f}, avg={self.avg:.4f}, "
                f"min={self.min:.4f}, max={self.max:.4f}, std={self.std:.4f})")
