"""
视频处理模块
=============
视频理解、分析和处理能力。

功能：
- 视频摘要：生成视频内容摘要
- 帧提取：提取关键帧
- 视频分析：分析视频内容、场景、动作
- 元数据提取：获取视频基本信息
"""

import os
from typing import Dict, List, Optional, Any
from pathlib import Path


class VideoProcessor:
    """
    视频处理类
    
    提供视频理解和分析能力。
    
    依赖：
    - opencv-python: 用于视频帧处理
    - ffmpeg: 用于视频转码和信息提取
    """
    
    def __init__(self, image_processor=None):
        """
        Args:
            image_processor: 图像处理实例（可选，用于分析帧）
        """
        self.image_processor = image_processor
    
    # ===== 核心方法 =====
    
    def get_info(self, video_path: str) -> Dict[str, Any]:
        """
        获取视频基本信息
        
        返回：
        - 时长、分辨率、帧率、编码格式
        - 文件大小、音频信息
        """
        info = {
            "path": video_path,
            "exists": os.path.exists(video_path),
        }
        
        if not os.path.exists(video_path):
            return info
        
        # 文件大小
        info["file_size"] = os.path.getsize(video_path)
        
        # 尝试用ffprobe获取详细信息
        try:
            import subprocess
            import json
            
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", 
                 "-show_format", "-show_streams", video_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                
                # 格式信息
                fmt = data.get("format", {})
                info["duration"] = float(fmt.get("duration", 0))
                info["format"] = fmt.get("format_name", "")
                info["bit_rate"] = int(fmt.get("bit_rate", 0))
                
                # 视频流
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        info["video_codec"] = stream.get("codec_name", "")
                        info["width"] = stream.get("width", 0)
                        info["height"] = stream.get("height", 0)
                        info["fps"] = eval(stream.get("r_frame_rate", "0/1"))
                        info["pix_fmt"] = stream.get("pix_fmt", "")
                    elif stream.get("codec_type") == "audio":
                        info["audio_codec"] = stream.get("codec_name", "")
                        info["sample_rate"] = stream.get("sample_rate", "")
                        info["channels"] = stream.get("channels", 0)
        
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            # ffprobe不可用，尝试用opencv
            try:
                import cv2
                cap = cv2.VideoCapture(video_path)
                info["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                info["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                info["fps"] = cap.get(cv2.CAP_PROP_FPS)
                info["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if info["fps"] > 0:
                    info["duration"] = info["frame_count"] / info["fps"]
                cap.release()
            except ImportError:
                pass
        
        return info
    
    def extract_frames(
        self,
        video_path: str,
        output_dir: str,
        frame_interval: float = 1.0,
        max_frames: int = 100,
    ) -> List[str]:
        """
        提取视频帧
        
        Args:
            video_path: 视频路径
            output_dir: 输出目录
            frame_interval: 帧间隔（秒）
            max_frames: 最大帧数
        
        Returns:
            提取的帧图片路径列表
        """
        os.makedirs(output_dir, exist_ok=True)
        extracted = []
        
        try:
            import cv2
            
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            if fps <= 0:
                fps = 30  # 默认值
            
            # 计算采样间隔
            step = max(1, int(fps * frame_interval))
            
            frame_idx = 0
            count = 0
            
            while count < max_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if not ret:
                    break
                
                # 保存帧
                output_path = os.path.join(output_dir, f"frame_{count:04d}.jpg")
                cv2.imwrite(output_path, frame)
                extracted.append(output_path)
                
                count += 1
                frame_idx += step
                
                if frame_idx >= total_frames:
                    break
            
            cap.release()
            
        except ImportError:
            # opencv不可用，尝试用ffmpeg
            try:
                import subprocess
                
                # 使用ffmpeg提取帧
                cmd = [
                    "ffmpeg", "-i", video_path,
                    "-vf", f"fps=1/{frame_interval}",
                    "-q:v", "2",
                    os.path.join(output_dir, "frame_%04d.jpg"),
                ]
                
                subprocess.run(cmd, capture_output=True, timeout=60)
                
                # 收集生成的文件
                for f in sorted(os.listdir(output_dir)):
                    if f.startswith("frame_") and f.endswith(".jpg"):
                        extracted.append(os.path.join(output_dir, f))
                        if len(extracted) >= max_frames:
                            break
                            
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        return extracted
    
    def summarize(self, video_path: str, max_frames: int = 10) -> Dict[str, Any]:
        """
        视频摘要 - 提取关键帧并生成描述
        
        Args:
            video_path: 视频路径
            max_frames: 分析的关键帧数
        
        Returns:
            视频摘要信息
        """
        result = {
            "video_info": self.get_info(video_path),
            "key_frames": [],
            "summary": "",
        }
        
        # 提取关键帧
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            frames = self.extract_frames(
                video_path, tmpdir,
                frame_interval=max(1, result["video_info"].get("duration", 10) / max_frames),
                max_frames=max_frames,
            )
            
            result["key_frames"] = frames
            
            # 如果有图像处理器，分析帧
            if self.image_processor:
                frame_descriptions = []
                for i, frame in enumerate(frames):
                    desc = self.image_processor.describe(frame)
                    frame_descriptions.append(f"第{i+1}帧: {desc}")
                
                result["frame_descriptions"] = frame_descriptions
                result["summary"] = "\n".join(frame_descriptions)
            else:
                result["summary"] = f"提取了 {len(frames)} 个关键帧\n[提示] 配置ImageProcessor可获得帧描述"
        
        return result
    
    # ===== 高级功能 =====
    
    def detect_scenes(self, video_path: str, threshold: float = 30.0) -> List[Dict]:
        """
        场景检测 - 检测视频中的场景切换
        
        Args:
            video_path: 视频路径
            threshold: 场景切换阈值
        
        Returns:
            场景列表，每个包含开始时间、结束时间、帧号
        """
        scenes = []
        
        try:
            import cv2
            import numpy as np
            
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            prev_frame = None
            scene_start = 0
            frame_idx = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # 转灰度
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.resize(gray, (320, 240))  # 缩小加速
                
                if prev_frame is not None:
                    # 计算帧差
                    diff = np.mean(np.abs(gray.astype(float) - prev_frame.astype(float)))
                    
                    if diff > threshold:
                        # 场景切换
                        scenes.append({
                            "start_frame": scene_start,
                            "end_frame": frame_idx,
                            "start_time": scene_start / fps if fps > 0 else 0,
                            "end_time": frame_idx / fps if fps > 0 else 0,
                            "duration_frames": frame_idx - scene_start,
                        })
                        scene_start = frame_idx
                
                prev_frame = gray
                frame_idx += 1
            
            # 最后一个场景
            if frame_idx > scene_start:
                scenes.append({
                    "start_frame": scene_start,
                    "end_frame": frame_idx,
                    "start_time": scene_start / fps if fps > 0 else 0,
                    "end_time": frame_idx / fps if fps > 0 else 0,
                    "duration_frames": frame_idx - scene_start,
                })
            
            cap.release()
            
        except ImportError:
            pass
        
        return scenes
    
    def extract_audio(self, video_path: str, output_path: str) -> bool:
        """
        从视频中提取音频
        
        Args:
            video_path: 视频路径
            output_path: 输出音频路径
        
        Returns:
            是否成功
        """
        try:
            import subprocess
            
            cmd = [
                "ffmpeg", "-i", video_path,
                "-vn", "-acodec", "copy",
                output_path,
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            return result.returncode == 0
            
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
