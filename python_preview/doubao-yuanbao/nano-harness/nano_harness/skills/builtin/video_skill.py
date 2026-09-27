"""
视频处理 Skill
==============
将视频处理能力封装为Skill。
"""

from typing import List
from langchain_core.tools import StructuredTool

from ..base import BaseSkill
from ...multimodal.video import VideoProcessor


class VideoSkill(BaseSkill):
    """
    视频处理Skill
    
    提供视频信息查询、帧提取、视频摘要等能力。
    """
    
    name = "video"
    description = "视频处理和分析能力，包括视频信息查询、帧提取、视频摘要等"
    version = "1.0.0"
    author = "nano-harness"
    category = "multimodal"
    tags = ["video", "multimedia", "frames", "summary"]
    
    def __init__(self, video_processor: VideoProcessor = None):
        super().__init__()
        self.processor = video_processor or VideoProcessor()
    
    def get_tools(self) -> List:
        return [
            StructuredTool.from_function(
                func=self.get_video_info,
                name="get_video_info",
                description="""获取视频基本信息。
                
                返回视频的时长、分辨率、帧率、编码格式等信息。
                
                参数：
                - video_path: 视频文件路径
                """,
            ),
            StructuredTool.from_function(
                func=self.extract_video_frames,
                name="extract_video_frames",
                description="""提取视频帧。
                
                按指定间隔提取视频帧，保存为图片文件。
                
                参数：
                - video_path: 视频文件路径
                - output_dir: 输出目录
                - frame_interval: 帧间隔（秒），默认1秒
                - max_frames: 最大提取帧数，默认100
                """,
            ),
            StructuredTool.from_function(
                func=self.summarize_video,
                name="summarize_video",
                description="""视频摘要。
                
                提取视频关键帧并生成内容摘要。
                
                参数：
                - video_path: 视频文件路径
                - max_frames: 分析的关键帧数，默认10
                """,
            ),
            StructuredTool.from_function(
                func=self.extract_audio_from_video,
                name="extract_audio_from_video",
                description="""从视频中提取音频。
                
                将视频中的音频轨道提取为独立的音频文件。
                
                参数：
                - video_path: 视频文件路径
                - output_path: 输出音频文件路径
                """,
            ),
        ]
    
    # ===== 工具实现 =====
    
    def get_video_info(self, video_path: str) -> str:
        """获取视频信息"""
        info = self.processor.get_info(video_path)
        
        if not info.get("exists"):
            return f"❌ 视频文件不存在：{video_path}"
        
        lines = ["【视频信息】"]
        lines.append(f"文件：{info.get('path', 'N/A')}")
        
        if info.get("file_size"):
            size_mb = info["file_size"] / (1024 * 1024)
            lines.append(f"大小：{size_mb:.2f} MB")
        
        if info.get("duration"):
            duration = info["duration"]
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            lines.append(f"时长：{minutes}分{seconds}秒 ({duration:.1f}秒)")
        
        if info.get("width") and info.get("height"):
            lines.append(f"分辨率：{info['width']} x {info['height']}")
        
        if info.get("fps"):
            lines.append(f"帧率：{info['fps']:.2f} fps")
        
        if info.get("video_codec"):
            lines.append(f"视频编码：{info['video_codec']}")
        
        if info.get("audio_codec"):
            lines.append(f"音频编码：{info['audio_codec']}")
            if info.get("sample_rate"):
                lines.append(f"采样率：{info['sample_rate']} Hz")
            if info.get("channels"):
                lines.append(f"声道数：{info['channels']}")
        
        return "\n".join(lines)
    
    def extract_video_frames(
        self,
        video_path: str,
        output_dir: str,
        frame_interval: float = 1.0,
        max_frames: int = 100,
    ) -> str:
        """提取视频帧"""
        frames = self.processor.extract_frames(
            video_path, output_dir,
            frame_interval=frame_interval,
            max_frames=max_frames,
        )
        
        if not frames:
            return f"❌ 提取帧失败，请检查视频文件和ffmpeg/opencv是否可用"
        
        lines = [f"✅ 成功提取 {len(frames)} 帧"]
        lines.append(f"输出目录：{output_dir}")
        lines.append("")
        lines.append("前5帧：")
        for i, frame in enumerate(frames[:5]):
            lines.append(f"  {i+1}. {frame}")
        
        if len(frames) > 5:
            lines.append(f"  ... 还有 {len(frames) - 5} 帧")
        
        return "\n".join(lines)
    
    def summarize_video(self, video_path: str, max_frames: int = 10) -> str:
        """视频摘要"""
        result = self.processor.summarize(video_path, max_frames=max_frames)
        
        lines = ["【视频摘要】"]
        
        info = result.get("video_info", {})
        if info.get("duration"):
            duration = info["duration"]
            lines.append(f"视频时长：{duration:.1f} 秒")
        if info.get("width") and info.get("height"):
            lines.append(f"分辨率：{info['width']} x {info['height']}")
        
        lines.append(f"提取关键帧：{len(result.get('key_frames', []))} 帧")
        
        if result.get("summary"):
            lines.append("")
            lines.append("内容摘要：")
            lines.append(result["summary"])
        
        return "\n".join(lines)
    
    def extract_audio_from_video(self, video_path: str, output_path: str) -> str:
        """提取音频"""
        success = self.processor.extract_audio(video_path, output_path)
        
        if success:
            return f"✅ 音频提取成功，保存到：{output_path}"
        else:
            return f"❌ 音频提取失败，请检查ffmpeg是否可用"
