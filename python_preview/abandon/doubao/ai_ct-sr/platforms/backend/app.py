from time import time
import os
from os import path
import string
import random

import torch
import torchvision
import torch.nn.functional as F
import flask
from PIL import Image

from nova.lu_mwcnn.mainline.model_cpu import LUMWCNN_CPU


# ===================== 线程配置 =====================
# laptop 建议设为物理核心数（避免线程争抢）
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"
torch.set_num_threads(4)


# ===================== 基础配置 =====================
APP_PORT = 9191
app = flask.Flask(__name__)

# ===================== 路径 =====================
weight_file = r'/home/dake/Documents/Project/Graduction_Projects/codes/nova/lu_mwcnn/mainline/continual_ckpt/luna/luna_ct_epoch_56.pth'
input_directory = r'./input'
output_directory = r'./output'
os.makedirs(input_directory, exist_ok=True)
os.makedirs(output_directory, exist_ok=True)

sr_model = None
SCALE = 4


# ===================== 工具 =====================
def gen_temp_name():
    return f"{int(time())}_{''.join(random.sample(string.ascii_letters + string.digits, 8))}"


def load_model():
    model = LUMWCNN_CPU(in_channels=1, scale=4)
    try:
        checkpoint = torch.load(weight_file, map_location='cpu')
        model.load_state_dict(checkpoint['model_state_dict'])
        model.eval()
        print("✅ 模型加载成功 | 医学CT 4倍超分")
        return model
    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        return None


def adaptive_input_size(img: Image.Image):
    """小波模型专用：尺寸补全为 2 的倍数"""
    w, h = img.size
    new_w = w if w % 2 == 0 else w + 1
    new_h = h if h % 2 == 0 else h + 1
    if new_w != w or new_h != h:
        # 医学CT专用：最近邻插值，不破坏纹理
        img = img.resize((new_w, new_h), Image.Resampling.NEAREST)
    return img, (w, h)   # ← 顺便返回原始尺寸


# ===================== 主接口 =====================
@app.route('/predict', methods=['POST'])
def predict():
    global sr_model
    if sr_model is None:
        return flask.jsonify({"success": False, "error": "模型未加载"}), 500

    try:
        file = flask.request.files['image']
        # 前端预留参数（当前不生效）
        target_w = int(flask.request.form.get('width', 0))
        target_h = int(flask.request.form.get('height', 0))

        if target_w < 0 or target_h < 0:
            return flask.jsonify({"success": False, "error": "目标尺寸非法"}), 400

        # 严格加载单通道灰度图
        img = Image.open(file).convert('L')
        original_w, original_h = img.size
        img, _ = adaptive_input_size(img)

        # 转 Tensor (1, 1, H, W)，模型内部已做归一化
        tensor = torchvision.transforms.ToTensor()(img).unsqueeze(0)

        with torch.no_grad():
            sr_tensor = sr_model(tensor)

        # ✅ 关键裁剪：adaptive_input_size 补的像素，输出后要裁掉
        target_w_out = original_w * SCALE
        target_h_out = original_h * SCALE
        output_tensor = sr_tensor[..., :target_h_out, :target_w_out]

        # 保存
        filename = gen_temp_name()
        save_path = path.join(output_directory, f"{filename}.png")
        output_pil = torchvision.transforms.ToPILImage()(
            output_tensor.squeeze().cpu())
        output_pil.save(save_path, format='PNG', compress_level=6)

        return flask.jsonify({
            "success": True,
            "filename": filename,
            "original_size": f"{original_w}x{original_h}",
            "output_size": f"{output_tensor.shape[-1]}x{output_tensor.shape[-2]}",
            "scale": 4,
        })

    except Exception as e:
        return flask.jsonify({"success": False, "error": str(e)}), 500


# ===================== 基础路由 =====================
@app.route('/')
@app.route('/ping')
def index():
    return flask.jsonify({"status": "running", "msg": "CT超分服务-4倍小波模型"})


@app.route('/get_output')
def get_output():
    name = flask.request.args.get('filename')
    img_path = path.join(output_directory, f"{name}.png")
    if not path.exists(img_path):
        return flask.jsonify({"success": False, "error": "文件不存在"}), 404
    return flask.send_file(img_path, mimetype='image/png')


# ===================== CORS =====================
@app.after_request
def cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


if __name__ == '__main__':
    sr_model = load_model()
    app.run(host='0.0.0.0', port=APP_PORT, debug=False)
