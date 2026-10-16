"""
音频处理模块
=============
音频理解、分析和处理能力。

功能：
- 语音转文字（STT）：将音频转录为文字
- 音频分析：分析音频属性（时长、格式、音量等）
- 说话人识别：识别不同说话人（可选）
- 情感分析：分析语音情感（可选）
"""

import os
from typing import Dict, List, Optional, Any
from pathlib import Path


class AudioProcessor:
    """
    音频处理类
    
    提供音频理解和分析能力。
    
    依赖：
    - whisper / speech_recognition: 语音识别
    - pydub / librosa: 音频处理
    - ffmpeg: 音频转码
    """
    
    def __init__(self, stt_model=None):
        """
        Args:
            stt_model: 语音识别模型（可选）
        """
        self.stt_model = stt_model
    
    # ===== 核心方法 =====
    
    def get_info(self, audio_path: str) -> Dict[str, Any]:
        """
        获取音频基本信息
        
        返回：
        - 时长、采样率、声道数、编码格式
        - 文件大小、比特率
        """
        info = {
            "path": audio_path,
            "exists": os.path.exists(audio_path),
        }
        
        if not os.path.exists(audio_path):
            return info
        
        info["file_size"] = os.path.getsize(audio_path)
        
        # 尝试用ffprobe获取详细信息
        try:
            import subprocess
            import json
            
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", audio_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                
                fmt = data.get("format", {})
                info["duration"] = float(fmt.get("duration", 0))
                info["format"] = fmt.get("format_name", "")
                info["bit_rate"] = int(fmt.get("bit_rate", 0))
                
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "audio":
                        info["codec"] = stream.get("codec_name", "")
                        info["sample_rate"] = int(stream.get("sample_rate", 0))
                        info["channels"] = stream.get("channels", 0)
                        info["channel_layout"] = stream.get("channel_layout", "")
                        break
        
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            # ffprobe不可用，尝试pydub
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(audio_path)
                info["duration"] = len(audio) / 1000.0
                info["sample_rate"] = audio.frame_rate
                info["channels"] = audio.channels
                info["sample_width"] = audio.sample_width
            except ImportError:
                pass
        
        return info
    
    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
    ) -> Dict[str, Any]:
        """
        语音转文字（STT）
        
        Args:
            audio_path: 音频路径
            language: 语言 (auto/zh/en/...)
        
        Returns:
            转录结果，包含文字、时间戳等
        """
        result = {
            "text": "",
            "language": language,
            "segments": [],
            "success": False,
        }
        
        # 优先使用whisper
        if self.stt_model:
            try:
                # 使用配置的STT模型
                transcription = self.stt_model.transcribe(audio_path)
                result["text"] = transcription.get("text", "")
                result["segments"] = transcription.get("segments", [])
                result["language"] = transcription.get("language", language)
                result["success"] = True
                return result
            except Exception as e:
                result["error"] = str(e)
        
        # 尝试openai-whisper
        try:
            import whisper
            
            model = whisper.load_model("base")
            transcription = model.transcribe(audio_path, language=None if language == "auto" else language)
            
            result["text"] = transcription["text"].strip()
            result["language"] = transcription.get("language", language)
            result["segments"] = [
                {
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": seg["text"].strip(),
                }
                for seg in transcription.get("segments", [])
            ]
            result["success"] = True
            
        except ImportError:
            # 尝试speech_recognition
            try:
                import speech_recognition as sr
                
                r = sr.Recognizer()
                with sr.AudioFile(audio_path) as source:
                    audio = r.record(source)
                
                try:
                    if language == "zh" or language == "auto":
                        result["text"] = r.recognize_google(audio, language="zh-CN")
                    else:
                        result["text"] = r.recognize_google(audio, language=language)
                    result["success"] = True
                except sr.UnknownValueError:
                    result["error"] = "无法识别语音"
                except sr.RequestError as e:
                    result["error"] = f"识别服务错误: {e}"
                    
            except ImportError:
                result["error"] = "没有可用的语音识别库，请安装 whisper 或 SpeechRecognition"
        
        return result
    
    def analyze(self, audio_path: str) -> Dict[str, Any]:
        """
        综合分析音频
        
        返回：
        - 基本信息
        - 语音转录（如果可用）
        - 音频特征分析
        """
        result = {
            "info": self.get_info(audio_path),
            "transcription": None,
            "features": {},
        }
        
        # 尝试转录
        transcription = self.transcribe(audio_path)
        if transcription["success"]:
            result["transcription"] = transcription
        
        # 音频特征分析
        try:
            import numpy as np
            
            # 尝试用librosa分析
            try:
                import librosa
                
                y, sr = librosa.load(audio_path, sr=None)
                
                result["features"] = {
                    "duration": librosa.get_duration(y=y, sr=sr),
                    "sample_rate": sr,
                    "rms_energy": float(np.sqrt(np.mean(y**2))),
                    "zero_crossing_rate": float(np.mean(librosa.feature.zero_crossing_rate(y))),
                    "spectral_centroid": float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))),
                    "spectral_bandwidth": float(np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr))),
                }
                
            except ImportError:
                # 用pydub做简单分析
                try:
                    from pydub import AudioSegment
                    audio = AudioSegment.from_file(audio_path)
                    
                    result["features"] = {
                        "duration_seconds": len(audio) / 1000.0,
                        "sample_rate": audio.frame_rate,
                        "channels": audio.channels,
                        "max_dBFS": audio.max_dBFS,
                        "avg_dBFS": audio.dBFS,
                    }
                except ImportError:
                    pass
                    
        except Exception:
            pass
        
        return result
    
    # ===== 音频处理 =====
    
    def convert_format(
        self,
        input_path: str,
        output_path: str,
        format: str = "mp3",
    ) -> bool:
        """
        转换音频格式
        
        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            format: 目标格式 (mp3/wav/flac/ogg等)
        
        Returns:
            是否成功
        """
        try:
            import subprocess
            
            cmd = ["ffmpeg", "-i", input_path, "-y", output_path]
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            return result.returncode == 0
            
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # 尝试pydub
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(input_path)
                audio.export(output_path, format=format)
                return True
            except ImportError:
                return False
    
    def split_audio(
        self,
        input_path: str,
        output_dir: str,
        segment_duration: float = 60.0,
    ) -> List[str]:
        """
        分割音频为多个片段
        
        Args:
            input_path: 输入文件路径
            output_dir: 输出目录
            segment_duration: 每段时长（秒）
        
        Returns:
            分割后的文件路径列表
        """
        os.makedirs(output_dir, exist_ok=True)
        segments = []
        
        try:
            from pydub import AudioSegment
            
            audio = AudioSegment.from_file(input_path)
            total_duration = len(audio) / 1000.0
            
            num_segments = int(total_duration // segment_duration) + 1
            
            for i in range(num_segments):
                start = i * segment_duration * 1000
                end = min((i + 1) * segment_duration * 1000, len(audio))
                
                segment = audio[start:end]
                output_path = os.path.join(output_dir, f"segment_{i:03d}.mp3")
                segment.export(output_path, format="mp3")
                segments.append(output_path)
                
        except ImportError:
            # 用ffmpeg
            try:
                import subprocess
                
                info = self.get_info(input_path)
                duration = info.get("duration", 0)
                
                num_segments = int(duration // segment_duration) + 1
                
                for i in range(num_segments):
                    start = i * segment_duration
                    output_path = os.path.join(output_dir, f"segment_{i:03d}.mp3")
                    
                    cmd = [
                        "ffmpeg", "-i", input_path,
                        "-ss", str(start),
                        "-t", str(segment_duration),
                        "-y", output_path,
                    ]
                    
                    subprocess.run(cmd, capture_output=True, timeout=30)
                    segments.append(output_path)
                    
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        return segments
    
    # ===== 高级功能 =====
    
    def detect_silence(
        self,
        audio_path: str,
        min_silence_len: int = 1000,
        silence_thresh: float = -40.0,
    ) -> List[Dict]:
        """
        检测静音片段
        
        Args:
            audio_path: 音频路径
            min_silence_len: 最静静音时长（毫秒）
            silence_thresh: 静音阈值（dBFS）
        
        Returns:
            静音片段列表
        """
        silences = []
        
        try:
            from pydub import AudioSegment
            from pydub.silence import detect_silence
            
            audio = AudioSegment.from_file(audio_path)
            silence_ranges = detect_silence(
                audio,
                min_silence_len=min_silence_len,
                silence_thresh=silence_thresh,
            )
            
            for start, end in silence_ranges:
                silences.append({
                    "start_ms": start,
                    "end_ms": end,
                    "duration_ms": end - start,
                    "start_seconds": start / 1000.0,
                    "end_seconds": end / 1000.0,
                })
                
        except ImportError:
            pass
        
        return silences
