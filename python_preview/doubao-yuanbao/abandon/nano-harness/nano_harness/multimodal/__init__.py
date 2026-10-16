"""
多模态处理包
=============
处理图片、视频、音频等多媒体内容。

包含：
- 图像处理：描述、识别、编辑
- 视频处理：摘要、帧提取、分析
- 音频处理：转录、分析、生成

设计原则：
- 统一接口：不同模态有相似的API
- 可扩展：轻松添加新的处理能力
- 容错：处理失败时有降级方案
"""

from .image import ImageProcessor
from .video import VideoProcessor
from .audio import AudioProcessor

__all__ = ["ImageProcessor", "VideoProcessor", "AudioProcessor"]
