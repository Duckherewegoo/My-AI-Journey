"""
音频处理 Skill
==============
将音频处理能力封装为Skill。
"""

from typing import List
from langchain_core.tools import StructuredTool

from ..base import BaseSkill
from ...multimodal.audio import AudioProcessor


class AudioSkill(BaseSkill):
    """
    音频处理Skill
    
    提供音频信息查询、语音转文字、音频分析等能力。
    """
    
    name = "audio"
    description = "音频处理和分析能力，包括语音转文字、音频信息查询、音频分析等"
    version = "1.0.0"
    author = "nano-harness"
    category = "multimodal"
    tags = ["audio", "speech", "stt", "multimedia", "transcription"]
    
    def __init__(self, audio_processor: AudioProcessor = None):
        super().__init__()
        self.processor = audio_processor or AudioProcessor()
    
    def get_tools(self) -> List:
        return [
            StructuredTool.from_function(
                func=self.get_audio_info,
                name="get_audio_info",
                description="""获取音频基本信息。
                
                返回音频的时长、采样率、声道数、编码格式等信息。
                
                参数：
                - audio_path: 音频文件路径
                """,
            ),
            StructuredTool.from_function(
                func=self.transcribe_audio,
                name="transcribe_audio",
                description="""语音转文字（STT）。
                
                将音频中的语音内容转录为文字。
                支持中英文，自动检测语言。
                
                参数：
                - audio_path: 音频文件路径
                - language: 语言代码，默认auto自动检测
                """,
            ),
            StructuredTool.from_function(
                func=self.analyze_audio,
                name="analyze_audio",
                description="""综合分析音频。
                
                返回音频的详细分析结果，包括：
                - 基本信息
                - 语音转录（如果可用）
                - 音频特征分析
                
                参数：
                - audio_path: 音频文件路径
                """,
            ),
            StructuredTool.from_function(
                func=self.convert_audio_format,
                name="convert_audio_format",
                description="""转换音频格式。
                
                将音频文件转换为其他格式（mp3/wav/flac/ogg等）。
                
                参数：
                - input_path: 输入音频文件路径
                - output_path: 输出音频文件路径
                - format: 目标格式，默认mp3
                """,
            ),
        ]
    
    # ===== 工具实现 =====
    
    def get_audio_info(self, audio_path: str) -> str:
        """获取音频信息"""
        info = self.processor.get_info(audio_path)
        
        if not info.get("exists"):
            return f"❌ 音频文件不存在：{audio_path}"
        
        lines = ["【音频信息】"]
        lines.append(f"文件：{info.get('path', 'N/A')}")
        
        if info.get("file_size"):
            size_mb = info["file_size"] / (1024 * 1024)
            lines.append(f"大小：{size_mb:.2f} MB")
        
        if info.get("duration"):
            duration = info["duration"]
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            lines.append(f"时长：{minutes}分{seconds}秒 ({duration:.1f}秒)")
        
        if info.get("sample_rate"):
            lines.append(f"采样率：{info['sample_rate']} Hz")
        
        if info.get("channels"):
            channel_names = {1: "单声道", 2: "立体声"}
            ch_name = channel_names.get(info["channels"], f"{info['channels']}声道")
            lines.append(f"声道：{ch_name}")
        
        if info.get("codec"):
            lines.append(f"编码：{info['codec']}")
        
        if info.get("bit_rate"):
            lines.append(f"比特率：{info['bit_rate'] // 1000} kbps")
        
        return "\n".join(lines)
    
    def transcribe_audio(self, audio_path: str, language: str = "auto") -> str:
        """语音转文字"""
        result = self.processor.transcribe(audio_path, language=language)
        
        if not result.get("success"):
            error = result.get("error", "未知错误")
            return f"❌ 语音转录失败：{error}"
        
        lines = ["【语音转录结果】"]
        
        if result.get("language"):
            lines.append(f"检测语言：{result['language']}")
        
        lines.append("")
        lines.append("转录内容：")
        lines.append(result.get("text", ""))
        
        # 如果有分段信息
        if result.get("segments"):
            lines.append("")
            lines.append(f"共 {len(result['segments']} 个语音片段")
        
        return "\n".join(lines)
    
    def analyze_audio(self, audio_path: str) -> str:
        """综合分析音频"""
        result = self.processor.analyze(audio_path)
        
        lines = ["【音频分析报告】"]
        
        # 基本信息
        info = result.get("info", {})
        if info.get("duration"):
            lines.append(f"时长：{info['duration']:.1f} 秒")
        if info.get("sample_rate"):
            lines.append(f"采样率：{info['sample_rate']} Hz")
        if info.get("channels"):
            lines.append(f"声道数：{info['channels']}")
        
        # 转录结果
        if result.get("transcription"):
            trans = result["transcription"]
            if trans.get("success"):
                lines.append("")
                lines.append("📝 语音内容：")
                lines.append(trans.get("text", "")[:500])
                if len(trans.get("text", "")) > 500:
                    lines.append("... (内容已截断)")
        
        # 音频特征
        features = result.get("features", {})
        if features:
            lines.append("")
            lines.append("📊 音频特征：")
            if "rms_energy" in features:
                lines.append(f"   - 平均能量：{features['rms_energy']:.4f}")
            if "zero_crossing_rate" in features:
                lines.append(f"   - 过零率：{features['zero_crossing_rate']:.4f}")
            if "spectral_centroid" in features:
                lines.append(f"   - 频谱质心：{features['spectral_centroid']:.1f} Hz")
        
        return "\n".join(lines)
    
    def convert_audio_format(
        self,
        input_path: str,
        output_path: str,
        format: str = "mp3",
    ) -> str:
        """转换音频格式"""
        success = self.processor.convert_format(input_path, output_path, format=format)
        
        if success:
            return f"✅ 格式转换成功，保存到：{output_path}"
        else:
            return f"❌ 格式转换失败，请检查ffmpeg或pydub是否可用"
