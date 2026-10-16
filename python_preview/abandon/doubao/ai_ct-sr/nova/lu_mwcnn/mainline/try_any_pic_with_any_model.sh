#!/bin/bash
# 示例执行脚本，根据实际路径修改
# 灰度模式 + 分块256（模型固定输入尺寸） + 无降采样
python try_any_pic_with_any_model.py --custom_model ./output_deeplesion/deeplesion_train_bravo_ckpt/best_model.pth --input_path ./a.png --color_mode gray --tile_size 256
