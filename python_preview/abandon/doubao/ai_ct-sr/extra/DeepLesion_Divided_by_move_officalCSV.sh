#!/bin/bash

# deeplesion_dataset_organizer_move.sh

# 配置变量
CSV_FILE="DL_info.csv"
SOURCE_DIR="key_slices"
TARGET_DIR="deeplesion_sr_dataset"

# 创建目录结构
mkdir -p $TARGET_DIR/{train,val,test}/{HR,LR}

# 检查文件是否存在
if [ ! -f "$CSV_FILE" ]; then
    echo "错误: 找不到 $CSV_FILE"
    exit 1
fi

if [ ! -d "$SOURCE_DIR" ]; then
    echo "错误: 找不到目录 $SOURCE_DIR"
    exit 1
fi

# 警告用户
echo "警告: 此操作将移动文件而不是复制，原始文件将被移动到新位置。"
read -p "确定要继续吗？(输入 'yes' 继续): " confirm
if [ "$confirm" != "yes" ]; then
    echo "操作已取消"
    exit 0
fi

echo "开始组织DeepLesion数据集（移动文件）..."

# 使用awk处理CSV文件并移动文件
awk -F, '
NR == 1 { next }  # 跳过标题行
{
    filename = $1
    split_type = $18  # Train_Val_Test列
    
    if (split_type == 1) dest = "train"
    else if (split_type == 2) dest = "val" 
    else if (split_type == 3) dest = "test"
    else next
    
    # 源文件路径
    source_hr = "'$SOURCE_DIR'/" filename
    
    # 目标文件路径
    target_hr = "'$TARGET_DIR'/" dest "/HR/" filename
    target_lr = "'$TARGET_DIR'/" dest "/LR/" filename
    
    # 移动文件
    if (system("test -f \"" source_hr "\"") == 0) {
        # 移动HR文件
        system("mv \"" source_hr "\" \"" target_hr "\"")
        
        # 创建硬链接到LR目录（节省空间）
        if (system("ln \"" target_hr "\" \"" target_lr "\" 2>/dev/null") != 0) {
            # 如果不支持硬链接，则复制文件
            system("cp \"" target_hr "\" \"" target_lr "\"")
        }
        
        counts[dest]++
        total++
    } else {
        print "警告: 文件不存在 - " source_hr
    }
}
END {
    print "数据集组织完成!"
    print "各集合图像数量:"
    print "  train:", counts["train"]
    print "  val:", counts["val"]
    print "  test:", counts["test"]
    print "总计:", total, "张图像"
}' $CSV_FILE

# 创建数据集信息文件
cat > $TARGET_DIR/dataset_info.txt << EOF
DeepLesion超分辨率数据集信息
========================================
train: $(find $TARGET_DIR/train/HR -name "*.png" | wc -l) 张图像
val: $(find $TARGET_DIR/val/HR -name "*.png" | wc -l) 张图像  
test: $(find $TARGET_DIR/test/HR -name "*.png" | wc -l) 张图像
总计: $(find $TARGET_DIR/{train,val,test}/HR -name "*.png" | wc -l) 张图像
组织时间: $(date)
操作: 移动文件（非复制）
EOF

echo "数据集已成功组织到: $TARGET_DIR"