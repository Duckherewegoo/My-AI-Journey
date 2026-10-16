"""
train.py —— VGGLite (CT-LPIPS 骨干) 分类训练脚本
任务：用 DeepLesion_Key_slices 训练 VGGLite，让 658 类分类器学 CT 特征
"""
from torchvision import transforms
from modell import VGGLite
from tqdm import tqdm
import numpy as np
from PIL import Image, ImageFile
import os
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.utils.tensorboard.writer import SummaryWriter
import random
import sys


# 基础配置
BATCH_SIZE = 32                                  # ← 按需调整（3060 8GB 推荐 32）
LEARNING_RATE = 1e-3                             # ← 分类任务 Adam 常用
EPOCH = 100                                      # ← 按需调整
INPUT_SIZE = (224, 224)                          # ✅ 从 ckp 反推
NUM_WORKERS = min(os.cpu_count(), 8)             # ← CPU 上限

# 标签提取配置（根据你的文件名格式调整）
LABEL_SEGMENT_INDEX = 0                          # ← 见 Q1，必须按文件名确认
ImageFile.LOAD_TRUNCATED_IMAGES = True
sys.setrecursionlimit(5000)                      # ← 常见值

# 全局变量：存储所有数据集的标签映射（自动生成）
GLOBAL_LABEL_MAP = {}
GLOBAL_LABEL_COUNT = 0                           # ✅ 计数器初值


class CTLPIPSDataset(Dataset):
    def __init__(self, ct_dir, input_size=INPUT_SIZE, is_train=True):
        super(CTLPIPSDataset, self).__init__()
        self.ct_files = []
        self.label_list = []
        self.is_train = is_train
        invalid_reasons = {}

        # 扫描所有文件，提取标签并生成全局映射
        for x in sorted(os.listdir(ct_dir)):
            if not x.lower().endswith('.png'):
                continue
            try:
                file_path = os.path.join(ct_dir, x)
                file_base = x.replace('.png', '')
                parts = file_base.split('_')

                # 检查分段数量
                if len(parts) <= LABEL_SEGMENT_INDEX:
                    raise ValueError(f"文件名分段不足，无法提取索引{LABEL_SEGMENT_INDEX}的标签")

                # 提取标签（去前导零）
                label_segment = parts[LABEL_SEGMENT_INDEX]
                raw_label = label_segment.lstrip('0')
                if not raw_label:
                    raw_label = '0'                  # ← 全 0 段（如 "000"）→ 归到 "0"

                # 全局标签映射（自动生成，无需手动配置）
                global GLOBAL_LABEL_MAP, GLOBAL_LABEL_COUNT
                if raw_label not in GLOBAL_LABEL_MAP:
                    GLOBAL_LABEL_MAP[raw_label] = GLOBAL_LABEL_COUNT
                    GLOBAL_LABEL_COUNT += 1

                # 存储文件路径和标签ID
                self.ct_files.append(file_path)
                self.label_list.append(GLOBAL_LABEL_MAP[raw_label])

            except Exception as e:
                reason = str(e)
                invalid_reasons[reason] = invalid_reasons.get(reason, 0) + 1
                print(f"跳过无效文件 {x}: {reason}")

        # 打印数据集统计
        print(f"\n===== 数据集 {os.path.basename(ct_dir)} 统计 =====")
        print(f"总文件数: {len(os.listdir(ct_dir))}")
        print(f"有效文件数: {len(self.ct_files)}")
        print(f"无效文件原因统计: {invalid_reasons}")
        print(f"当前全局标签数: {GLOBAL_LABEL_COUNT}")
        print("========================================\n")

        # 数据预处理
        self.transform = transforms.Compose([
            transforms.Resize(input_size),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.5], std=[0.5])   # ← 单通道归一化到 [-1, 1]
        ])

    def __getitem__(self, idx):
        try:
            if idx >= len(self.ct_files) or idx < 0:
                raise IndexError("索引超出数据集范围")

            # 加载图像（单通道）
            image = Image.open(self.ct_files[idx]).convert('L')
            image = self.transform(image)
            label = self.label_list[idx]

            return image, label
        except Exception as e:
            print(f"加载数据出错 (索引 {idx}): {str(e)}")
            # 随机返回一个有效样本（避免训练中断）
            if len(self) > 0:
                return self.__getitem__(random.randint(0, len(self)-1))
            else:
                raise RuntimeError("数据集为空，无法返回有效样本")

    def __len__(self):
        return len(self.ct_files)


# 路径配置
TRAIN_PATH = r'/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/train/HR/'
VAL_PATH = r'/home/dake/Documents/Projects/datasets/DeepLesion_Key_slices/val/HR/'
OUTPUT_PATH = r'./out'

# 创建输出目录
os.makedirs(OUTPUT_PATH, exist_ok=True)
ckp_dir = os.path.join(OUTPUT_PATH, 'ckp')
os.makedirs(ckp_dir, exist_ok=True)

# 设备配置
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"使用设备: {device}")

# 加载数据集（先训练集，再验证集，生成完整标签映射）
train_dataset = CTLPIPSDataset(TRAIN_PATH, is_train=True)
val_dataset = CTLPIPSDataset(VAL_PATH, is_train=False)

# 检查数据集是否为空
if len(train_dataset) == 0:
    raise RuntimeError("训练集为空，请检查数据路径或文件格式")
if len(val_dataset) == 0:
    raise RuntimeError("验证集为空，请检查数据路径或文件格式")

# 数据加载器
train_loader = DataLoader(
    dataset=train_dataset,
    batch_size=BATCH_SIZE,
    shuffle=True,
    num_workers=NUM_WORKERS,
    pin_memory=True if device.type == 'cuda' else False,
    drop_last=True
)

val_loader = DataLoader(
    dataset=val_dataset,
    batch_size=BATCH_SIZE,
    shuffle=False,
    num_workers=NUM_WORKERS,
    pin_memory=True if device.type == 'cuda' else False
)

# 模型初始化（关键：传入自动生成的标签数）
print(f"\n初始化模型，总类别数: {GLOBAL_LABEL_COUNT}")
vgg = VGGLite(n_classes=GLOBAL_LABEL_COUNT).to(device)

# 损失函数、优化器
cost = nn.CrossEntropyLoss()                          # 多分类交叉熵
optimizer = torch.optim.Adam(
    vgg.parameters(), lr=LEARNING_RATE, weight_decay=1e-4)   # ← 1e-4 防过拟合
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
    optimizer,
    mode='min',
    factor=0.5,                                       # ← 每次降为一半
    patience=5,                                       # ← 5 轮无提升才降
    verbose=True
)

# TensorBoard 日志
tb = SummaryWriter(os.path.join(OUTPUT_PATH, 'tensorboard'))

# 训练循环
for epoch in range(EPOCH):
    vgg.train()
    train_loss = 0.0
    train_steps = 0

    for images, labels in tqdm(train_loader, desc=f"Epoch {epoch+1}/{EPOCH} 训练"):
        images = images.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()
        _, outputs = vgg(images)                     # ← forward 返回 (fmap, out)
        loss = cost(outputs, labels)
        loss.backward()
        optimizer.step()

        train_loss += loss.item()
        train_steps += 1

    avg_train_loss = train_loss / train_steps if train_steps > 0 else 0.0
    print(f"[Epoch {epoch+1}] 训练损失: {avg_train_loss:.4f}")
    tb.add_scalar('Train/avg_loss', avg_train_loss, epoch)

    # 验证过程
    vgg.eval()
    correct = 0
    total = 0
    val_loss = 0.0
    val_steps = 0

    with torch.no_grad():
        for images, labels in tqdm(val_loader, desc=f"Epoch {epoch+1}/{EPOCH} 验证"):
            images = images.to(device)
            labels = labels.to(device)

            _, outputs = vgg(images)
            loss = cost(outputs, labels)
            val_loss += loss.item()

            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()
            val_steps += 1

    avg_val_loss = val_loss / val_steps if val_steps > 0 else 0.0
    val_acc = correct / total if total > 0 else 0.0
    print(f'[Epoch {epoch+1}]')
    print(f'验证损失: {avg_val_loss:.4f}')
    print(f'验证准确率: {val_acc:.4f} ({correct}/{total})')
    tb.add_scalar('Val/avg_loss', avg_val_loss, epoch)
    tb.add_scalar('Val/accuracy', val_acc, epoch)

    # 学习率调度
    scheduler.step(avg_val_loss)

    # 保存模型（每 5 个 epoch 保存一次）
    if (epoch + 1) % 5 == 0:                          # ← 每 5 轮保存
        torch.save(
            vgg.state_dict(),
            os.path.join(ckp_dir, f'vgglite_{epoch}.pth')
        )
        # 保存标签映射（方便后续推理）
        with open(os.path.join(ckp_dir, 'label_map.txt'), 'w') as f:
            for k, v in GLOBAL_LABEL_MAP.items():
                f.write(f"{k}:{v}\n")

print("训练完成!")
tb.close()

# 打印最终标签映射
print(f"\n最终标签映射表已保存到: {os.path.join(ckp_dir, 'label_map.txt')}")
print(f"总标签数: {GLOBAL_LABEL_COUNT}")
