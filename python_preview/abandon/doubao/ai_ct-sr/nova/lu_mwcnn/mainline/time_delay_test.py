import torch
import time
import numpy as np
from model_cpu import LUMWCNN_CPU
import os

 设置 OpenMP 使用的线程数
 通常设置为物理核心数的一半或全核，取决于你的服务器配置
 例如：核CPU就设为或
os.environ["OMP_NUM_THREADS"] = ""
os.environ["MKL_NUM_THREADS"] = ""

 如果是用 PyTorch，这句也很重要（控制 PyTorch 自己的算子并行）
torch.set_num_threads()
 假设你的输入数据叫 input_tensor (尺寸例如 [, , , ])
your_model = LUMWCNN_CPU()


def calculate_cpu_latency(model, input_tensor, device='cpu', num_runs=):
    model.eval()   切换到评估模式（关掉Dropout等）
    model.to(device)
    input_tensor = input_tensor.to(device)

     . 预热 (Warm-up)，跑次让CPU进入状态
    print("Warming up...")
    with torch.no_grad():
        for _ in range():
            _ = model(input_tensor)

     . 正式计时
    print("Benchmarking...")
    latencies = []
    with torch.no_grad():
        for i in range(num_runs):
            start_time = time.time()
            _ = model(input_tensor)
            end_time = time.time()
            latencies.append((end_time - start_time)  )   转为毫秒 ms

     . 统计数据
    latencies = np.array(latencies)
    avg_latency = latencies.mean()
    std_latency = latencies.std()

    print(f"Device: {device}")
    print(f"Average Latency: {avg_latency:.f} ms")
    print(f"Std Deviation: {std_latency:.f} ms")
    print(f"FPS: { / avg_latency:.f}")

    return avg_latency


 ======= 运行示例 =======
dummy_input = torch.randn(, , , )   假设输入是x的CT单通道图
latency = calculate_cpu_latency(your_model, dummy_input, device='cpu')
