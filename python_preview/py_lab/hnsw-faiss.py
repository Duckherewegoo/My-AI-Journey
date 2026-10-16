import numpy as np
import faiss

# ===================== 1. 模拟数据：生成高维向量（贴合实际AI场景） =====================
# 实际场景：这里的向量可以是BERT词向量、图片特征、大模型嵌入向量（Embedding）
dim = 128  # 向量维度（常用128/768/1024，可随意修改）
n_data = 10000  # 数据库向量数量（模拟1万条数据，HNSW对百万/千万级更有优势）
n_query = 5  # 查询向量数量（模拟5个查询）

# 随机生成归一化向量（faiss推荐归一化，提升搜索精度，实际场景需对自己的向量做归一化）
np.random.seed(42)  # 固定随机种子，结果可复现
db_vectors = np.random.randn(n_data, dim).astype("float32")  # 数据库向量：[10000, 128]
query_vectors = np.random.randn(n_query, dim).astype("float32")  # 查询向量：[5, 128]
# 向量归一化（L2归一化，转为单位向量）
faiss.normalize_L2(db_vectors)
faiss.normalize_L2(query_vectors)

# ===================== 2. 构建HNSW索引（核心步骤，极简配置） =====================
# HNSW核心参数（极简版仅需配置维度，默认参数已适配大部分场景）
# 进阶参数：hnsw_m=16（每个节点的连接数，越大精度越高/速度越慢，默认16）、efConstruction=200（构建时的搜索范围，默认200）
index = faiss.IndexHNSWFlat(dim, 16)  # IndexHNSWFlat：基础HNSW索引（无量化，精度最高）
# 设置搜索时的efSearch（搜索范围，越大精度越高/速度越慢，默认10，这里设为50平衡精度/速度）
index.hnsw.efSearch = 50
# 向索引中添加数据库向量（构建索引）
index.add(db_vectors)

print(f"✅ HNSW索引构建完成，数据库向量数量：{index.ntotal}")

# ===================== 3. 近邻搜索：找每个查询向量的Top-K最相似向量 =====================
k = 10  # 找每个查询的前10个最相似向量
# 搜索返回两个结果：
# D：距离数组 [n_query, k]，值越小越相似（归一化后为余弦距离，范围0-2）
# I：索引数组 [n_query, k]，对应数据库中相似向量的下标
D, I = index.search(query_vectors, k)

# ===================== 4. 打印搜索结果 =====================
print("\n📊 近邻搜索结果（前3个查询示例）：")
for i in range(3):
    print(f"\n查询向量{i+1}：")
    print(f"  最相似的Top3向量下标：{I[i][:3]}")
    print(f"  对应余弦距离：{np.round(D[i][:3], 4)}")  # 保留4位小数
