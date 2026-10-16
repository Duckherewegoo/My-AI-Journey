# 反编译源文件: /home/dake/Documents/Projects/Graduction_Projects/codes/base/utils/__pycache__/meters.cpython-311.pyc
# 生成时间: 2026-09-14 16:06:15.158646
# ============================================================================

# Source Generated with Decompyle++
# File: meters.cpython-311.pyc (Python 3.11)

'''
    计量器
'''

class AverageMeter:
    
    def __init__(self):
        self.reset()

    
    def reset(self):
        '''重置所有统计量'''
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0
        self.max = float('-inf')
        self.min = float('inf')
        self.var = 0
        self.std = 0

    
    def update(self, val, n = (1,)):
        '''
        批量更新统计量
        参数：

            val: 当前观测值（标量或张量）

            n: 批量样本数量（默认1，支持batch_size>1场景）
        '''
        current_val = float(val)
        n = max(1, int(n))
        self.val = current_val
        self.sum / self.count = self, self.count += n, .count
        self.max = max(self.max, current_val) if self.count > n else current_val
        self.min = min(self.min, current_val) if self.count > n else current_val
        if self.count > 1:
            self.var = (self.sum / self.count - self.sum ** 2 / self.count ** 2) * (self.count / (self.count - 1))
            self.std = self.var ** 0.5
            return None
        return self, self.sum += current_val * n, .sum

    
    def get_stats(self):
        '''获取完整统计信息字典'''
        return {
            'current': self.val,
            'average': self.avg,
            'total': self.sum,
            'count': self.count,
            'max': self.max,
            'min': self.min,
            'variance': self.var,
            'std_dev': self.std }

    
    def __repr__(self):
        '''更友好的字符串表示'''
        return f'''AvgMeter(val={self.val:.4f}, avg={self.avg:.4f}, min={self.min:.4f}, max={self.max:.4f}, std={self.std:.4f})'''


