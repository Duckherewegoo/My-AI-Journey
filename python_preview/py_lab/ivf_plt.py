import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from sklearn.cluster import KMeans
import matplotlib.patches as patches

# ===================== 配置 =====================
plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei"]
plt.rcParams["axes.unicode_minus"] = False

# ===================== 1. 生成数据 =====================
np.random.seed(42)
dim = 2
n_data = 2000
n_clusters = 8
n_probe = 2
k = 10

# 生成聚类数据
db_vectors = np.vstack(
    [
        np.random.randn(n_data // n_clusters, 2) + [i * 3, j * 3]
        for i in [-2, -1, 1, 2]
        for j in [-2, -1, 1, 2]
    ]
)[:n_data].astype("float32")

query = np.array([[2.5, 1.5]], dtype="float32")

# ===================== 2. KMeans 聚类 =====================
kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
labels = kmeans.fit_predict(db_vectors)
centers = kmeans.cluster_centers_.astype("float32")

# 找到最近的聚类
dists = np.linalg.norm(centers - query, axis=1)
top_probe = np.argsort(dists)[:n_probe]

# 收集探测区域的向量
probe_idx = np.concatenate([np.where(labels == c)[0] for c in top_probe])
probe_vecs = db_vectors[probe_idx]

# 排序得到 Top-K
final_dists = np.linalg.norm(probe_vecs - query, axis=1)
topk_idx = probe_idx[np.argsort(final_dists)[:k]]
topk_vecs = db_vectors[topk_idx]

# ===================== 3. 绘图初始化 =====================
fig, ax = plt.subplots(figsize=(14, 9))
ax.set_xlim(-8, 8)
ax.set_ylim(-8, 8)
ax.set_title("IVF 倒排文件搜索 动画演示", fontsize=18)
ax.grid(alpha=0.3)

steps = [
    "1. 显示所有 2000 个向量",
    "2. KMeans 生成 8 个聚类中心",
    "3. 定位查询点（红色星号）",
    f"4. 探测最近 {n_probe} 个聚类（黄色高亮）",
    f"5. 在探测区内搜索 Top-{k} 最相似向量（绿色）",
]

# 散点（全部用 scatter，避免报错！）
scat_all = ax.scatter([], [], c="#ddd", s=10, alpha=0.6)
scat_centers = ax.scatter([], [], c="#1a535c", s=180, marker="^", edgecolors="black")
scat_query = ax.scatter([], [], c="#e74c3c", s=300, marker="*", edgecolors="black")
scat_probe = ax.scatter([], [], c="#ffc107", s=20, alpha=0.8)
scat_topk = ax.scatter([], [], c="#2ecc71", s=80, edgecolors="black")

# 聚类圆圈
circles = []
for _ in range(n_clusters):
    c = patches.Circle((0, 0), 0, fill=False, edgecolor="#1a535c", lw=1, alpha=0.5)
    ax.add_patch(c)
    circles.append(c)

# 探测高亮圈
probe_circles = []
for _ in range(n_probe):
    c = patches.Circle((0, 0), 0, fill=False, edgecolor="#ffc107", lw=3)
    ax.add_patch(c)
    probe_circles.append(c)

text = ax.text(
    0.02,
    0.98,
    "",
    transform=ax.transAxes,
    fontsize=14,
    bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
)

# ===================== 4. 动画 =====================


def update(frame):
    if frame == 0:
        scat_all.set_offsets(db_vectors)
        text.set_text(steps[0])

    elif frame == 1:
        scat_all.set_offsets(db_vectors)
        scat_centers.set_offsets(centers)
        for i in range(n_clusters):
            pts = db_vectors[labels == i]
            r = np.max(np.linalg.norm(pts - centers[i], axis=1)) + 0.3
            circles[i].set_center(centers[i])
            circles[i].set_radius(r)
        text.set_text(steps[1])

    elif frame == 2:
        scat_query.set_offsets(query)
        text.set_text(steps[2])

    elif frame == 3:
        mask = np.isin(labels, top_probe)
        scat_probe.set_offsets(db_vectors[mask])
        for i, c_idx in enumerate(top_probe):
            pts = db_vectors[labels == c_idx]
            r = np.max(np.linalg.norm(pts - centers[c_idx], axis=1)) + 0.3
            probe_circles[i].set_center(centers[c_idx])
            probe_circles[i].set_radius(r)
        text.set_text(steps[3])

    elif frame == 4:
        scat_topk.set_offsets(topk_vecs)
        text.set_text(steps[4])

    return (scat_all, scat_centers, scat_query, scat_probe, scat_topk, text)


ani = FuncAnimation(fig, update, frames=5, interval=2000, blit=True)
plt.tight_layout()
plt.show()
