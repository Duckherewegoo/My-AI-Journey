"""
图像处理模块
=============
图像理解、分析和处理能力。

功能：
- 图像描述：用文字描述图片内容
- 图像识别：识别图片中的物体、场景、文字
- 图像分析：分析图像属性（颜色、构图、质量等）
- OCR：提取图片中的文字
"""

import base64
from typing import Dict, List, Optional, Any
from pathlib import Path


class ImageProcessor:
    """
    图像处理类
    
    提供图像理解和分析能力，支持多种后端。
    
    使用方式：
    1. 直接传入图片路径或URL
    2. 调用各种分析方法
    3. 获取结构化结果
    """
    
    def __init__(self, llm_vision=None):
        """
        Args:
            llm_vision: 支持视觉的LLM模型（可选）
        """
        self.vision_model = llm_vision
        self._cache = {}
    
    # ===== 核心方法 =====
    
    def describe(self, image_path: str, detail: str = "auto") -> str:
        """
        描述图片内容
        
        Args:
            image_path: 图片路径或URL
            detail: 详细程度 (low/auto/high)
        
        Returns:
            图片描述文本
        """
        if not self.vision_model:
            return self._fallback_describe(image_path)
        
        try:
            # 使用视觉模型描述图片
            image_data = self._load_image(image_path)
            
            # 这里调用视觉模型
            # 实际使用时替换为真实的视觉模型调用
            prompt = "请详细描述这张图片的内容，包括主体、背景、颜色、构图等。"
            
            result = self._call_vision_model(image_data, prompt)
            return result
            
        except Exception as e:
            return f"图片描述失败: {str(e)}"
    
    def extract_text(self, image_path: str) -> str:
        """
        OCR - 提取图片中的文字
        
        Args:
            image_path: 图片路径或URL
        
        Returns:
            提取的文字内容
        """
        try:
            # 尝试使用pytesseract
            import pytesseract
            from PIL import Image
            
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img, lang='chi_sim+eng')
            return text.strip()
        except ImportError:
            return "[OCR不可用] 请安装 pytesseract 和 PIL 库"
        except Exception as e:
            return f"OCR失败: {str(e)}"
    
    def analyze(self, image_path: str) -> Dict[str, Any]:
        """
        综合分析图片
        
        返回结构化的分析结果，包括：
        - 主要内容描述
        - 颜色分析
        - 构图分析
        - 质量评估
        - 检测到的物体
        """
        result = {
            "description": "",
            "colors": [],
            "objects": [],
            "quality": {},
            "text_detected": "",
        }
        
        # 描述
        result["description"] = self.describe(image_path)
        
        # 文字提取
        result["text_detected"] = self.extract_text(image_path)
        
        # 基础图像分析（使用PIL）
        try:
            from PIL import Image
            img = Image.open(image_path)
            
            result["quality"] = {
                "width": img.width,
                "height": img.height,
                "mode": img.mode,
                "format": img.format,
            }
            
            # 简单颜色分析
            result["colors"] = self._analyze_colors(img)
            
        except Exception:
            pass
        
        return result
    
    # ===== 工具方法 =====
    
    def _load_image(self, image_path: str) -> str:
        """加载图片，返回base64编码"""
        if image_path.startswith(('http://', 'https://')):
            # URL图片
            import requests
            response = requests.get(image_path)
            image_data = base64.b64encode(response.content).decode('utf-8')
        else:
            # 本地文件
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
        
        return image_data
    
    def _call_vision_model(self, image_data: str, prompt: str) -> str:
        """调用视觉模型"""
        if self.vision_model:
            # 实际使用时调用真实的视觉模型
            # 这里是占位实现
            return f"[视觉模型输出] {prompt}"
        return self._fallback_describe("image")
    
    def _fallback_describe(self, image_path: str) -> str:
        """降级方案 - 没有视觉模型时"""
        import os
        
        if os.path.exists(image_path):
            size = os.path.getsize(image_path)
            filename = os.path.basename(image_path)
            return f"图片文件: {filename}，大小: {size} 字节\n[提示] 配置视觉模型后可获得详细描述"
        else:
            return f"图片路径: {image_path}\n[提示] 配置视觉模型后可获得详细描述"
    
    def _analyze_colors(self, img) -> List[str]:
        """简单颜色分析"""
        try:
            # 缩放到小尺寸加速分析
            small_img = img.resize((50, 50))
            pixels = list(small_img.getdata())
            
            # 统计主要颜色
            color_counts = {}
            for pixel in pixels[:1000]:  # 采样
                if isinstance(pixel, tuple):
                    # 简化颜色
                    r, g, b = pixel[0] // 32 * 32, pixel[1] // 32 * 32, pixel[2] // 32 * 32
                    color = f"rgb({r},{g},{b})"
                    color_counts[color] = color_counts.get(color, 0) + 1
            
            # 返回前5个主要颜色
            sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)
            return [c[0] for c in sorted_colors[:5]]
        except Exception:
            return []
    
    # ===== 批量处理 =====
    
    def batch_describe(self, image_paths: List[str]) -> List[str]:
        """批量描述图片"""
        results = []
        for path in image_paths:
            results.append(self.describe(path))
        return results
    
    def get_image_info(self, image_path: str) -> Dict:
        """获取图片基本信息"""
        try:
            from PIL import Image
            img = Image.open(image_path)
            return {
                "path": image_path,
                "width": img.width,
                "height": img.height,
                "mode": img.mode,
                "format": img.format,
                "size_bytes": Path(image_path).stat().st_size if Path(image_path).exists() else 0,
            }
        except Exception as e:
            return {"path": image_path, "error": str(e)}
