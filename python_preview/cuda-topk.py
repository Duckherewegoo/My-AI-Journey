# 需要NVIDIA GPU和RAPIDS环境（cuda>=11.0, rapids>=23.0）
import cudf
import cupy as cp
import numpy as np
import time
import psutil
from typing import List


def check_gpu_env() -> None:
    """检查GPU环境和显存是否满足基础要求"""
    try:
        # 检查CUDA可用
        if not cp.cuda.is_available():
            raise RuntimeError("未检测到可用的NVIDIA GPU或CUDA环境")
        # 检查GPU显存（至少4GB）
        gpu_mem = cp.cuda.Device(0).mem_info[1] / (1024**3)
        if gpu_mem < 4:
            raise RuntimeError(f"GPU显存不足（当前{gpu_mem:.1f}GB），至少需要4GB")
        print(f"GPU环境检测通过：显存{gpu_mem:.1f}GB")
    except Exception as e:
        raise RuntimeError(f"环境检查失败：{str(e)}")


def gpu_topk_trillion(
    total_samples: int = 1_000_000_000,  # 总样本数（实际万亿级需分批次）
    k: int = 100,
    batch_size: int = 100_000_000,  # 单批次样本数（适配显存）
) -> np.ndarray:
    """
    GPU加速的TopK查找（适配万亿级数据，分批次处理）
    Args:
        total_samples: 总样本数（建议不超过GPU显存可承载的范围）
        k: 要查找的TopK数量
        batch_size: 单批次处理的样本数（避免显存溢出）
    Returns:
        TopK的数值数组（降序）
    """
    # 前置检查
    check_gpu_env()
    start_time = time.time()

    all_topk: List[cp.ndarray] = []  # 存储各批次的TopK结果

    try:
        # 分批次生成/加载数据（模拟万亿级数据的分块处理）
        num_batches = (total_samples + batch_size - 1) // batch_size  # 向上取整
        print(f"开始分{num_batches}批次处理，总样本数：{total_samples:,}")

        for batch_idx in range(num_batches):
            # 计算当前批次的起止索引
            start = batch_idx * batch_size
            end = min((batch_idx + 1) * batch_size, total_samples)
            current_batch_size = end - start

            # 1. 生成当前批次的GPU数据（实际场景应从GPU显存加载，如cuDF读取Parquet）
            data_gpu = cp.random.normal(100, 50, current_batch_size).astype(cp.float32)

            # 2. 过滤无效数据（NaN/Inf）
            mask = ~(cp.isnan(data_gpu) | cp.isinf(data_gpu))
            data_clean = data_gpu[mask]
            if len(data_clean) == 0:
                continue  # 空批次跳过

            # 3. cuDF排序（GPU加速）
            df = cudf.DataFrame({"values": data_clean})
            df_sorted = df.sort_values("values", ascending=False)

            # 4. 提取当前批次的TopK并暂存
            batch_topk = df_sorted.head(k)["values"].to_cupy()
            all_topk.append(batch_topk)

            # 释放当前批次显存（避免累积）
            del data_gpu, data_clean, df, df_sorted
            cp.cuda.Stream.null.synchronize()  # 等待GPU操作完成

            print(
                f"批次{batch_idx+1}/{num_batches}处理完成，已提取{len(all_topk)*k}个候选值"
            )

        # 5. 合并所有批次的TopK候选值，最终排序得到全局TopK
        if not all_topk:
            raise ValueError("所有批次数据均为无效值，无可用数据")

        combined_topk = cp.concatenate(all_topk)
        # 最终排序（GPU端）
        sorted_indices = cp.argsort(combined_topk)[::-1]  # 降序
        final_topk = combined_topk[sorted_indices[:k]].get()  # 转到CPU

        # 输出耗时
        elapsed = time.time() - start_time
        print(f"\nGPU TopK完成！耗时：{elapsed:.2f}秒")
        print(f"Top{k}最大值：{final_topk[0]:.2f}，最小值：{final_topk[-1]:.2f}")

        return final_topk

    except cp.cuda.OutOfMemoryError:
        raise RuntimeError("GPU显存不足！请减小batch_size或total_samples")
    except Exception as e:
        raise RuntimeError(f"TopK处理失败：{str(e)}")


# 主函数调用（测试用）
if __name__ == "__main__":
    try:
        # 注意：1万亿（1e12）样本需分布式GPU集群，单机建议测试10亿级
        topk_result = gpu_topk_trillion(
            total_samples=1_000_000_000,  # 10亿（单机GPU可承载）
            k=100,
            batch_size=100_000_000,
        )
        # 打印前10个TopK结果
        print("\nTop10结果：", topk_result[:10])
    except Exception as e:
        print(f"执行失败：{e}")
