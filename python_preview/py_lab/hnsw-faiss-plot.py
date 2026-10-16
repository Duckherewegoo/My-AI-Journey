import numpy as np
import faiss
import matplotlib.pyplot as plt

# ===================== 1. 全局配置（适配中文字体，解决负号显示问题） =====================
plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei"]  # 你的常用中文字体
plt.rcParams["axes.unicode_minus"] = False  # 解决负号显示异常
plt.rcParams["figure.figsize"] = (12, 8)  # 画布大小
plt.rcParams["figure.dpi"] = 100  # 分辨率

# ===================== 2. 生成二维模拟向量（方便可视化，核心逻辑与高维一致） =====================
dim = 2  # 固定为2维，用于绘图
n_data = 500  # 数据库向量数量（500个点，分布更直观）
n_query = 3  # 3个查询向量，分别用不同颜色标注
k = 5  # 每个查询找Top5最相似向量

# 固定随机种子，结果可复现
np.random.seed(42)
# 生成数据库向量（二维正态分布，模拟真实数据的散点分布）
db_vectors = np.random.randn(n_data, dim).astype("float32")
# 生成查询向量（手动偏移，让搜索结果更易观察）
query_vectors = np.array([[2, 2], [-2, -2], [2, -2]], dtype="float32")

# 向量归一化（faiss HNSW推荐，保证余弦相似度计算精度）
faiss.normalize_L2(db_vectors)
faiss.normalize_L2(query_vectors)

# ===================== 3. 构建HNSW索引并执行近邻搜索 =====================
# 构建HNSW二维索引（hnsw_m=8，二维数据无需太大连接数）
index = faiss.IndexHNSWFlat(dim, 8)
index.hnsw.efSearch = 30  # 搜索范围，平衡精度和速度
index.add(db_vectors)  # 添加数据库向量到索引

# 执行近邻搜索，得到「距离数组D」和「索引数组I」
D, I = index.search(query_vectors, k)

# ===================== 4. 可视化绘制核心代码 =====================
fig, ax = plt.subplots()

# 绘制数据库所有向量（浅灰色散点，基础底图）
ax.scatter(
    db_vectors[:, 0], db_vectors[:, 1], c="#e0e0e0", s=20, label="数据库向量", alpha=0.6
)

# 定义查询向量的颜色、标记（区分3个查询）
query_colors = ["#e74c3c", "#2ecc71", "#3498db"]  # 红、绿、蓝
query_markers = ["*", "P", "X"]
query_sizes = [200, 200, 200]  # 查询向量放大显示，突出重点

# 遍历每个查询向量，绘制+标注Top-K相似向量
for q_idx in range(n_query):
    # 获取当前查询向量的坐标
    q_x, q_y = query_vectors[q_idx]
    # 绘制查询向量
    ax.scatter(
        q_x,
        q_y,
        c=query_colors[q_idx],
        marker=query_markers[q_idx],
        s=query_sizes[q_idx],
        label=f"查询向量{q_idx+1}",
        edgecolors="black",
        linewidth=1,
    )

    # 获取当前查询的Top-K相似向量的下标
    top_k_idx = I[q_idx]
    # 提取Top-K相似向量的坐标
    top_k_vectors = db_vectors[top_k_idx]
    # 绘制Top-K相似向量（对应查询的颜色，稍大尺寸）
    ax.scatter(
        top_k_vectors[:, 0],
        top_k_vectors[:, 1],
        c=query_colors[q_idx],
        s=80,
        alpha=0.8,
        edgecolors="black",
        linewidth=0.5,
    )

    # 绘制「查询向量→每个Top-K相似向量」的连线（浅一点的同色系，展示关联）
    for vec in top_k_vectors:
        ax.plot(
            [q_x, vec[0]], [q_y, vec[1]], c=query_colors[q_idx], alpha=0.4, linewidth=1
        )

# ===================== 5. 图表美化与标注 =====================
ax.set_title("HNSW 近邻搜索可视化（二维向量）", fontsize=18, pad=20)
ax.set_xlabel("向量维度1", fontsize=14)
ax.set_ylabel("向量维度2", fontsize=14)
ax.grid(True, linestyle="--", alpha=0.3)  # 网格线，辅助观察
ax.legend(loc="best", fontsize=12)  # 图例
plt.tight_layout()  # 自适应布局，防止标签重叠

# 显示图表
plt.show()

# 打印搜索结果数据（辅助分析）
print("=" * 50)
print("HNSW 近邻搜索Top-K结果（距离越小，相似度越高）")
print("=" * 50)
for q_idx in range(n_query):
    print(f"\n查询向量{q_idx+1}：")
    print(f"  Top{k}相似向量下标：{I[q_idx]}")
    print(f"  对应余弦距离：{np.round(D[q_idx], 4)}")
