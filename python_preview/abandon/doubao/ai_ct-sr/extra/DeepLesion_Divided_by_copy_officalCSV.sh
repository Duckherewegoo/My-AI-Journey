#!/bin/bash

# deeplesion_dataset_organizer.sh

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

echo "开始组织DeepLesion数据集..."

# 使用awk处理CSV文件并复制文件
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
    
    # 复制文件
    if (system("test -f \"" source_hr "\"") == 0) {
        system("cp \"" source_hr "\" \"" target_hr "\"")
        system("cp \"" source_hr "\" \"" target_lr "\"")
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
EOF

echo "数据集已成功组织到: $TARGET_DIR"