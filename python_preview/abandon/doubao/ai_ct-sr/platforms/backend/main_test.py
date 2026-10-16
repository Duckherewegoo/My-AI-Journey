from logging.handlers import RotatingFileHandler
import logging
from time import time
import torch
import string
import random
import sys
import flask
import io
import os
from os import path
from PIL import Image
import torchvision
import math
import numpy as np

dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__, '../../'))
sys.path.append(path.join(dirname__, '../../nova'))

APP_NAME = 'CTSR'
APP_PORT = 5000

app = flask.Flask(APP_NAME)

weight_file = r'../../nova/lu_mwcnn/mainline/continual_ckpt/best_covid/best_covid_ct_loss_epoch_100.pth'
input_directory = r'./input'
output_directory = r'./output'

sr_model = None

# ===================== 日志配置 =====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('CTSR')
handler = RotatingFileHandler(
    'ctsr_service.log',
    maxBytes=10 * 1024 * 1024,      # 10 MB
    backupCount=5,
    encoding='utf-8',
)
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(funcName)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


# ===================== 分块处理器 =====================
class ImageTiler:
    """图像分块处理器"""

    def __init__(self, tile_size=256, overlap=32, scale=4):
        self.tile_size = tile_size
        self.overlap = overlap
        self.scale = scale

    def split_image(self, image_pil):
        """将图像分割成多个块"""
        width, height = image_pil.size
        tiles = []
        positions = []

        num_cols = math.ceil(width / (self.tile_size - self.overlap))
        num_rows = math.ceil(height / (self.tile_size - self.overlap))

        print(f"图像尺寸: {width}x{height}, 分块: {num_cols}x{num_rows}")

        for row in range(num_rows):
            for col in range(num_cols):
                left = col * (self.tile_size - self.overlap)
                top = row * (self.tile_size - self.overlap)
                right = min(left + self.tile_size, width)
                bottom = min(top + self.tile_size, height)

                if right - left < self.tile_size:
                    left = max(0, right - self.tile_size)
                if bottom - top < self.tile_size:
                    top = max(0, bottom - self.tile_size)

                tile = image_pil.crop((left, top, right, bottom))

                if tile.size != (self.tile_size, self.tile_size):
                    tile = tile.resize(
                        (self.tile_size, self.tile_size), Image.LANCZOS)

                tiles.append(tile)
                positions.append((left, top, right, bottom))

        return tiles, positions, (width, height)

    def merge_tiles(self, tiles, positions, original_size):
        """将处理后的块合并成完整图像"""
        width, height = original_size
        result = Image.new(
            'L', (width * self.scale, height * self.scale), 0)

        for tile, (left, top, right, bottom) in zip(tiles, positions):
            left_sr = left * self.scale
            top_sr = top * self.scale

            crop_size = max(0, self.overlap * self.scale // 2)
            crop_left = crop_size
            crop_top = crop_size
            crop_right = max(crop_left + 1, tile.size[0] - crop_size)
            crop_bottom = max(crop_top + 1, tile.size[1] - crop_size)

            if crop_right > tile.size[0]:
                crop_right = tile.size[0]
            if crop_bottom > tile.size[1]:
                crop_bottom = tile.size[1]

            cropped_tile = tile.crop(
                (crop_left, crop_top, crop_right, crop_bottom))

            paste_left = left_sr + crop_size
            paste_top = top_sr + crop_size
            result.paste(cropped_tile, (paste_left, paste_top))

        return result


# ===================== 工具函数 =====================
def gen_temp_name():
    def gen_random_string(length=8):
        return ''.join(random.choices(
            string.ascii_letters + string.digits, k=length))

    return f'{str(int(time()))}_{os.getpid()}_{gen_random_string()}'


def load_model():
    from nova.lu_mwcnn.mainline.model_cpu import LUMWCNN_CPU
    model = LUMWCNN_CPU()

    try:
        checkpoint = torch.load(weight_file, map_location='cpu')
        if 'model_state_dict' in checkpoint:
            model.load_state_dict(checkpoint['model_state_dict'])
            print("从完整检查点加载模型权重")
        else:
            model.load_state_dict(checkpoint)
            print("加载纯模型权重")
    except Exception as e:
        logger.error(f"加载失败：{str(e)}", exc_info=True)
        print("使用随机初始化的模型（功能受限）")

    return model


# ===================== 路由 =====================
@app.route('/get_output', methods=['GET'])
def get_output():
    try:
        filename = flask.request.args.get('filename', type=str)

        if not filename:
            return flask.jsonify(
                {'success': False, 'error': '需要filename参数'}), 400

        filename_with_ext = filename + '.bmp'

        filepath = os.path.join(output_directory, filename_with_ext)
        if not os.path.exists(filepath):
            logger.warning(
                f"文件 {filepath} 不存在，输出目录文件列表：{os.listdir(output_directory)}")
            if os.path.exists(output_directory):
                print(f"输出目录中的文件: {os.listdir(output_directory)}")

            return flask.jsonify({
                'success': False,
                'error': f'文件 {filename_with_ext} 不存在'
            }), 404

        return flask.send_from_directory(
            output_directory, filename_with_ext, as_attachment=True)

    except Exception as e:
        print(f"get_output 错误: {e}")
        return flask.jsonify({'success': False, 'error': str(e)}), 500


@app.route('/ping', methods=['GET'])
def ping():
    print(f"收到ping请求，来源: {flask.request.remote_addr}")
    return flask.jsonify({'success': True})


@app.route('/predict_tiled', methods=['POST'])
def predict_tiled(image_pil=None):
    """分块超分处理接口"""
    try:
        if image_pil is None:
            if 'image' not in flask.request.files:
                return flask.jsonify(
                    {'success': False, 'error': '没有上传图片'}), 400
            file = flask.request.files['image']
            if file.filename == '':
                return flask.jsonify(
                    {'success': False, 'error': '没有选择文件'}), 400
            image_pil = Image.open(file.stream).convert('L')

        original_size = image_pil.size
        print(f"原图尺寸: {original_size}")

        if max(original_size) <= 256:
            print("图像较小，使用普通处理")
            return predict_single(image_pil)

        tiler = ImageTiler(tile_size=256, overlap=32)
        tiles, positions, original_size = tiler.split_image(image_pil)

        logger.debug(f"图像尺寸：{original_size}，分块数量：{len(tiles)}")

        max_tiles = 100
        if len(tiles) > max_tiles:
            raise Exception(
                f"图像分块过多（{len(tiles)}块），超过最大限制（{max_tiles}块）")

        processed_tiles = []
        print(f"分块数量: {len(tiles)}")

        for i, tile in enumerate(tiles):
            print(f"处理块 {i+1}/{len(tiles)}")

            tile_tensor = torchvision.transforms.ToTensor()(tile).unsqueeze(0)

            with torch.no_grad():
                output_tensor = sr_model(tile_tensor).clamp(
                    0, 1).detach().cpu().squeeze()

            output_pil = torchvision.transforms.ToPILImage()(output_tensor)
            processed_tiles.append(output_pil)

        result_image = tiler.merge_tiles(
            processed_tiles, positions, original_size)

        temp_basename = gen_temp_name()
        temp_filename = temp_basename + '.bmp'
        output_path = os.path.join(output_directory, temp_filename)

        os.makedirs(output_directory, exist_ok=True)
        result_image.save(output_path)

        print(f"分块处理完成，结果保存到: {output_path}")
        print(f"结果尺寸: {result_image.size}")

        return flask.jsonify({
            'success': True,
            'filename': temp_basename,
            'original_size': original_size,
            'result_size': result_image.size,
            'tiles_processed': len(tiles),
            'method': 'tiled'
        })

    except Exception as e:
        print(f"分块处理错误: {e}")
        import traceback
        traceback.print_exc()
        return flask.jsonify({'success': False, 'error': str(e)}), 500


def predict_single(image_pil=None):
    """单块处理函数"""
    try:
        is_from_request = False
        if image_pil is None:
            is_from_request = True
            if 'image' not in flask.request.files:
                return flask.jsonify(
                    {'success': False, 'error': '没有上传图片'}), 400
            file = flask.request.files['image']
            if file.filename == '':
                return flask.jsonify(
                    {'success': False, 'error': '没有选择文件'}), 400
            image_pil = Image.open(file.stream).convert('L')

        temp_basename = gen_temp_name()
        temp_filename = temp_basename + '.bmp'

        if is_from_request:
            temp_filepath = os.path.join(input_directory, temp_filename)
            os.makedirs(input_directory, exist_ok=True)
            image_pil.save(temp_filepath)

        image_tensor = torchvision.transforms.ToTensor()(image_pil).unsqueeze(0)

        global sr_model
        if sr_model is None:
            raise Exception("超分模型未加载，请重启服务")

        with torch.no_grad():
            image_out_tensor = sr_model(image_tensor).clamp(
                0, 1).detach().cpu().squeeze()

        image_out_pil = torchvision.transforms.ToPILImage()(image_out_tensor)

        output_path = os.path.join(output_directory, temp_filename)
        os.makedirs(output_directory, exist_ok=True)
        image_out_pil.save(output_path)

        print(f"单块处理完成: {output_path}")
        print(f"输入尺寸: {image_pil.size}, 输出尺寸: {image_out_pil.size}")

        return flask.jsonify({
            'success': True,
            'filename': temp_basename,
            'original_size': image_pil.size,
            'result_size': image_out_pil.size,
            'method': 'single'
        })

    except Exception as e:
        import traceback
        logger.error(f"单块处理失败：{str(e)}", exc_info=True)
        traceback.print_exc()
        return flask.jsonify({'success': False, 'error': str(e)}), 500


@app.route('/predict', methods=['POST'])
def predict():
    """智能处理接口：自动选择单块或分块处理"""
    try:
        if 'image' not in flask.request.files:
            return flask.jsonify(
                {'success': False, 'error': '没有上传图片'}), 400
        file = flask.request.files['image']
        if file.filename == '':
            return flask.jsonify(
                {'success': False, 'error': '没有选择文件'}), 400

        image_pil = Image.open(file.stream).convert('L')
        original_size = image_pil.size

        print(f"智能处理 - 原图尺寸: {original_size}")

        if max(original_size) > 256:
            print("选择分块处理")
            return predict_tiled(image_pil=image_pil)
        else:
            print("选择单块处理")
            return predict_single(image_pil=image_pil)

    except Exception as e:
        import traceback
        logger.error(f"超分处理失败：{str(e)}", exc_info=True)
        traceback.print_exc()
        return flask.jsonify({'success': False, 'error': str(e)}), 500


@app.route('/')
def index():
    return flask.jsonify({
        'app': APP_NAME,
        'status': 'running',
        'endpoints': {
            'ping': '/ping (GET)',
            'predict': '/predict (POST) - 自动选择单块/分块',
            'predict_tiled': '/predict_tiled (POST) - 强制分块处理',
            'get_output': '/get_output (GET)'
        }
    })


@app.after_request
def after_request(response):
    """添加CORS头"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers',
                         'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods',
                         'GET,PUT,POST,DELETE,OPTIONS')
    return response


if __name__ == '__main__':
    print("加载超分模型...")
    sr_model = load_model()
    sr_model.eval()

    os.makedirs(input_directory, exist_ok=True)
    os.makedirs(output_directory, exist_ok=True)

    logger.info(f"服务{APP_NAME}启动，端口：{APP_PORT}")
    app.run(host='0.0.0.0', port=APP_PORT, debug=False)
