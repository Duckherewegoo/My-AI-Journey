import random
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np

# ==============================================
# 超简单手工模拟 HNSW：分层 + 长连接 + 搜索路径
# ==============================================
plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei"]  # 你的常用中文字体
plt.rcParams["axes.unicode_minus"] = False  # 解决负号显示异常
np.random.seed(42)
random.seed(42)

# 1. 生成一批 2D 点（多一点，看得清楚）
n_points = 80
points = np.random.rand(n_points, 2) * 10

# 2. 手动构建 3 层 HNSW（真实结构就是这样！）
# - 顶层：点最少，全是长连接（高速路）
# - 中层：中等连接
# - 底层：所有点，短连接（精细搜索）
max_level = 2
level_points = {
    0: list(range(n_points)),  # 底层：全部点
    1: random.sample(range(n_points), 40),  # 中层：一半点
    2: random.sample(range(n_points), 15),  # 顶层：极少点（长距离跳转）
}

# 给每个点分配层级
point_level = {}
for p in range(n_points):
    for l in sorted(level_points.keys(), reverse=True):
        if p in level_points[l]:
            point_level[p] = l
            break

# 3. 生成连接：层级越高，连接越“长”（跨越大片区域）
edges = {l: [] for l in range(max_level + 1)}
for level in range(max_level + 1):
    nodes = level_points[level]
    for u in nodes:
        neighbors = []
        # 高层：长连接（跨很远）
        # 低层：短连接（只连附近）
        if level == 2:
            candidates = [v for v in nodes if v != u]
            neighbors = random.sample(candidates, min(3, len(candidates)))
        elif level == 1:
            candidates = [v for v in nodes if v != u and abs(u - v) < 20]
            neighbors = random.sample(candidates, min(4, len(candidates)))
        else:
            candidates = [v for v in nodes if v != u and abs(u - v) < 12]
            neighbors = random.sample(candidates, min(5, len(candidates)))
        for v in neighbors:
            edges[level].append((u, v))

# 4. 模拟 HNSW 搜索路径：顶层跳入 → 逐层缩小 → 底层精搜
query_idx = 50
path = [query_idx]
current = query_idx
visited = set([query_idx])

# 高层跳远距离
for _ in range(2):
    candidates = [v for u, v in edges[2] if u == current] + [
        u for u, v in edges[2] if v == current
    ]
    candidates = [c for c in candidates if c not in visited]
    if candidates:
        current = random.choice(candidates)
        path.append(current)
        visited.add(current)

# 中层缩小范围
for _ in range(2):
    candidates = [v for u, v in edges[1] if u == current] + [
        u for u, v in edges[1] if v == current
    ]
    candidates = [c for c in candidates if c not in visited]
    if candidates:
        current = random.choice(candidates)
        path.append(current)
        visited.add(current)

# 底层精确定位
for _ in range(2):
    candidates = [v for u, v in edges[0] if u == current] + [
        u for u, v in edges[0] if v == current
    ]
    candidates = [c for c in candidates if c not in visited]
    if candidates:
        current = random.choice(candidates)
        path.append(current)
        visited.add(current)

# ==============================================
# 绘图：三层 HNSW + 搜索路径
# ==============================================
plt.rcParams["figure.figsize"] = 14, 9
plt.rcParams["figure.dpi"] = 100

fig, (ax1, ax2, ax3) = plt.subplots(1, 3, sharex=True, sharey=True)
axes = [ax3, ax2, ax1]
colors = ["#ff6b6b", "#4ecdc4", "#1a535c"]
labels = [
    "底层（全点·短连接·精细搜索）",
    "中层（中点·中连接·缩圈）",
    "顶层（少点·长连接·高速跳转）",
]

for level in range(max_level, -1, -1):
    ax = axes[level]
    ax.set_title(labels[level], fontsize=13, pad=15)
    ax.scatter(points[:, 0], points[:, 1], c="#ddd", s=30, alpha=0.6)

    # 画当前层的点
    nodes = level_points[level]
    ax.scatter(points[nodes, 0], points[nodes, 1], c=colors[level], s=60, alpha=0.8)

    # 画边
    for u, v in edges[level]:
        ax.plot(
            [points[u, 0], points[v, 0]],
            [points[u, 1], points[v, 1]],
            c=colors[level],
            lw=1.5,
            alpha=0.6,
        )

# 画出搜索路径（真正的 HNSW 搜索过程）
path_x = points[path, 0]
path_y = points[path, 1]
ax1.plot(path_x, path_y, c="gold", lw=4, alpha=0.9, label="搜索路径")
ax1.scatter(path_x, path_y, c="gold", s=120, edgecolors="black", label="搜索经过节点")
ax1.scatter(
    points[query_idx, 0],
    points[query_idx, 1],
    c="red",
    s=200,
    marker="*",
    label="查询点",
)

ax1.legend(fontsize=10)
plt.tight_layout()
plt.suptitle("✅ 真正的 HNSW 分层导航小世界 可视化", fontsize=16, y=1.02)
plt.show()

# 打印搜索逻辑
print("\n🔍 HNSW 搜索路径（层级从高到低）：")
print(" → ".join(map(str, path)))
print("\n✅ 原理：顶层长跳快速靠近 → 中层缩圈 → 底层精确定位")
