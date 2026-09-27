import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ===================== 配置 =====================
plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei"]
plt.rcParams["axes.unicode_minus"] = False

# ===================== 1. 生成数据 =====================
np.random.seed(42)
n_data = 800  # 800 个向量
dim = 2

# 随机生成向量
db = np.random.rand(n_data, 2) * 10 - 5
query = np.array([2.5, 1.5])  # 查询点
k = 10  # 找最近 10 个

# ===================== 2. 暴力搜索核心（硬算所有距离） =====================
distances = np.sqrt(((db - query) ** 2).sum(axis=1))  # 逐个算距离！
topk_indices = np.argsort(distances)[:k]  # 排序取前10

# ===================== 3. 绘图 =====================
fig, ax = plt.subplots(figsize=(12, 7))
ax.set_xlim(-6, 6)
ax.set_ylim(-6, 6)
ax.set_title("暴力搜索 Brute-force Search（逐个计算距离）", fontsize=16)
ax.grid(alpha=0.3)

# 散点
scat_all = ax.scatter([], [], c="#cccccc", s=20, alpha=0.7)
scat_query = ax.scatter([], [], c="#e74c3c", s=300, marker="*", label="查询点")
scat_checked = ax.scatter([], [], c="#ffcc00", s=25, alpha=0.9)  # 正在检查
scat_topk = ax.scatter([], [], c="#2ecc71", s=80, label="最近10个")

# 文字 ✅ 修复这里：transAxes
text = ax.text(
    0.02,
    0.98,
    "",
    transform=ax.transAxes,
    fontsize=13,
    bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
)

# ===================== 4. 动画：暴力遍历每一个点 =====================


def update(frame):
    if frame == 0:
        scat_all.set_offsets(db)
        scat_query.set_offsets(query)
        text.set_text("步骤1：展示所有向量 + 查询点")

    elif frame == 1:
        text.set_text("步骤2：暴力搜索开始 → 逐个计算距离")

    else:
        # 逐步高亮正在检查的点
        check_until = min((frame - 2) * 20, n_data)
        checked = db[:check_until]
        scat_checked.set_offsets(checked)

        # 全部检查完，显示最终结果
        if check_until == n_data:
            scat_topk.set_offsets(db[topk_indices])
            text.set_text(f"步骤3：完成！遍历了全部 {n_data} 个向量，找到最近10个")
        else:
            text.set_text(f"正在计算距离：已检查 {check_until}/{n_data} 个向量")

    return scat_all, scat_query, scat_checked, scat_topk, text


# ===================== 启动动画 =====================
ani = FuncAnimation(fig, update, frames=45, interval=100, blit=True)
plt.legend()
plt.tight_layout()
plt.show()
