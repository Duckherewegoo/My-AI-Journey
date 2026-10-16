"""
图片处理 Skill
==============
将图像处理能力封装为Skill，供Agent调用。
"""

from typing import List
from langchain_core.tools import StructuredTool

from ..base import BaseSkill
from ...multimodal.image import ImageProcessor


class ImageSkill(BaseSkill):
    """
    图片处理Skill
    
    提供图片理解、分析、OCR等能力。
    """
    
    name = "image"
    description = "图片理解和分析能力，包括图片描述、文字识别、图像分析等"
    version = "1.0.0"
    author = "nano-harness"
    category = "multimodal"
    tags = ["image", "vision", "ocr", "multimodal"]
    
    def __init__(self, image_processor: ImageProcessor = None):
        super().__init__()
        self.processor = image_processor or ImageProcessor()
    
    def get_tools(self) -> List:
        return [
            StructuredTool.from_function(
                func=self.describe_image,
                name="describe_image",
                description="""描述图片内容。
                
                输入图片路径或URL，返回图片的文字描述。
                可以识别图片中的物体、场景、人物、文字等内容。
                
                参数：
                - image_path: 图片文件路径或URL
                """,
            ),
            StructuredTool.from_function(
                func=self.extract_text_from_image,
                name="extract_text_from_image",
                description="""从图片中提取文字（OCR）。
                
                识别图片中的文字内容，支持中英文。
                
                参数：
                - image_path: 图片文件路径或URL
                """,
            ),
            StructuredTool.from_function(
                func=self.analyze_image,
                name="analyze_image",
                description="""综合分析图片。
                
                返回图片的详细分析结果，包括：
                - 内容描述
                - 文字提取
                - 颜色分析
                - 尺寸信息
                - 质量评估
                
                参数：
                - image_path: 图片文件路径或URL
                """,
            ),
            StructuredTool.from_function(
                func=self.get_image_info,
                name="get_image_info",
                description="""获取图片基本信息。
                
                返回图片的尺寸、格式、大小等元数据。
                
                参数：
                - image_path: 图片文件路径
                """,
            ),
        ]
    
    # ===== 工具实现 =====
    
    def describe_image(self, image_path: str) -> str:
        """描述图片"""
        return self.processor.describe(image_path)
    
    def extract_text_from_image(self, image_path: str) -> str:
        """提取图片文字"""
        return self.processor.extract_text(image_path)
    
    def analyze_image(self, image_path: str) -> str:
        """综合分析图片"""
        result = self.processor.analyze(image_path)
        
        lines = ["【图片分析结果】"]
        lines.append(f"\n📝 内容描述：\n{result['description']}")
        
        if result.get("text_detected"):
            lines.append(f"\n📄 检测到的文字：\n{result['text_detected']}")
        
        if result.get("colors"):
            lines.append(f"\n🎨 主要颜色：{', '.join(result['colors'][:5])}")
        
        if result.get("quality"):
            q = result["quality"]
            lines.append(f"\n📐 图片信息：")
            if "width" in q:
                lines.append(f"   - 尺寸：{q['width']} x {q['height']}")
            if "format" in q:
                lines.append(f"   - 格式：{q['format']}")
            if "mode" in q:
                lines.append(f"   - 模式：{q['mode']}")
        
        return "\n".join(lines)
    
    def get_image_info(self, image_path: str) -> str:
        """获取图片信息"""
        info = self.processor.get_image_info(image_path)
        
        if "error" in info:
            return f"获取图片信息失败：{info['error']}"
        
        lines = ["【图片信息】"]
        lines.append(f"路径：{info.get('path', 'N/A')}")
        lines.append(f"尺寸：{info.get('width', '?')} x {info.get('height', '?')}")
        lines.append(f"格式：{info.get('format', 'N/A')}")
        lines.append(f"模式：{info.get('mode', 'N/A')}")
        
        if info.get("size_bytes"):
            size_kb = info["size_bytes"] / 1024
            if size_kb > 1024:
                lines.append(f"大小：{size_kb / 1024:.2f} MB")
            else:
                lines.append(f"大小：{size_kb:.2f} KB")
        
        return "\n".join(lines)
