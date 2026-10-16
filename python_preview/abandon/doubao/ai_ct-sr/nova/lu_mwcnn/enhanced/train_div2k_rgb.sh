export CUDA_VISIBLE_DEVICES=0
# 基础显存优化（混合精度）
#python div2k_rgb.py --mixed_precision
# 极致显存优化（混合精度+梯度检查点+梯度累积）
#python div2k_rgb.py --mixed_precision --use_checkpoint --gradient_accumulation_steps 2 --batch_size 4
#python div2k_rgb.py --mixed_precision --quick_validate
# python div2k_rgb.py --mixed_precision --use_checkpoint --gradient_accumulation_steps 4 --batch_size 4 --crop_size 64
python div2k_rgb.py --batch_size 16 --grad_accum_steps 2 --mixed_precision
#python div2k_rgb.py --batch_size 8 --use_checkpoint --grad_accum_steps 4
#python div2k_rgb.py --image_mode gray --lpips_weight 0.005

