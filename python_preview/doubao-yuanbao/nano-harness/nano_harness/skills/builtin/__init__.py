"""
内置 Skill 包
==============
系统内置的常用Skill。

包含：
- BashSkill: 执行Shell命令（带用户确认）
- ImageSkill: 图像处理能力
- VideoSkill: 视频处理能力
- AudioSkill: 音频处理能力
- FileSkill: 文件操作能力
"""

from .bash_skill import BashSkill
from .image_skill import ImageSkill
from .video_skill import VideoSkill
from .audio_skill import AudioSkill
from .file_skill import FileSkill

__all__ = [
    "BashSkill",
    "ImageSkill",
    "VideoSkill",
    "AudioSkill",
    "FileSkill",
]
