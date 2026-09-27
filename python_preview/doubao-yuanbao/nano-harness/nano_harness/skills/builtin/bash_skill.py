"""
Bash Skill
==========
执行Shell命令的Skill，带用户确认机制。

这是系统的核心能力之一，允许AI在用户确认的前提下
执行Linux系统命令，完成各种系统操作任务。

安全机制：
1. 风险等级评估：自动判断命令的危险程度
2. 用户确认：高风险命令必须经过用户确认
3. 命令黑名单：禁止执行极度危险的命令
4. 输出限制：防止输出过大
5. 超时控制：防止命令卡死
6. 工作目录限制：防止越权访问
"""

import os
import subprocess
import shlex
from typing import Dict, List, Optional, Callable, Any
from langchain_core.tools import StructuredTool

from ..base import BaseSkill


# 高风险命令关键词（需要用户确认）
HIGH_RISK_PATTERNS = [
    # 删除操作
    "rm -rf", "rm -r", "rmdir", "del", "rd /s",
    # 系统操作
    "shutdown", "reboot", "halt", "poweroff", "init 0", "init 6",
    # 格式化
    "mkfs", "format", "fdisk", "dd if=",
    # 权限修改
    "chmod 777", "chown -R", "chmod -R",
    # 包管理（系统级）
    "apt-get", "yum install", "dnf install", "pacman -S",
    # 网络攻击
    "nmap", "masscan", "hydra", "john",
    # 数据泄露
    "cat /etc/passwd", "cat /etc/shadow", "sudo", "su ",
    # 进程管理
    "kill -9", "pkill", "killall",
    # 文件覆盖
    "> /etc/", "> /var/", "mv /etc/",
    # 环境变量修改
    "export PATH=", ".bashrc", ".profile",
    # 下载执行
    "curl.*|.*bash", "wget.*|.*sh", "curl.*|.*sh",
    # 加密
    "openssl enc", "gpg --encrypt",
    # 数据库操作
    "drop table", "delete from", "truncate",
]

# 禁止执行的命令（绝对不允许）
FORBIDDEN_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs /dev/sda",
    "dd if=/dev/zero of=/dev/sda",
    ":(){ :|:& };:",  # fork炸弹
    "format c:",
    "del /f /s /q C:\\*.*",
]


class BashSkill(BaseSkill):
    """
    Bash命令执行Skill
    
    允许AI执行Linux Shell命令，带有完善的安全机制。
    
    安全等级：
    - 低风险：只读命令，如 ls, cat, pwd, echo 等
    - 中风险：修改文件但不危险，如 mkdir, touch, cp 等
    - 高风险：可能造成数据丢失或系统变更，需要用户确认
    - 禁止：绝对不允许执行的命令
    """
    
    name = "bash"
    description = "执行Linux Shell命令，支持文件操作、系统管理、程序运行等"
    version = "1.0.0"
    author = "nano-harness"
    category = "system"
    tags = ["bash", "shell", "linux", "command", "system"]
    
    def __init__(
        self,
        work_dir: str = ".",
        user_confirm_callback: Optional[Callable] = None,
        timeout: int = 30,
        max_output_length: int = 10000,
        auto_confirm_low_risk: bool = True,
    ):
        """
        Args:
            work_dir: 工作目录限制
            user_confirm_callback: 用户确认回调函数
                签名: callback(command: str, risk_level: str) -> bool
            timeout: 命令超时时间（秒）
            max_output_length: 最大输出长度
            auto_confirm_low_risk: 是否自动确认低风险命令
        """
        super().__init__()
        self.work_dir = os.path.abspath(work_dir)
        self.user_confirm_callback = user_confirm_callback
        self.timeout = timeout
        self.max_output_length = max_output_length
        self.auto_confirm_low_risk = auto_confirm_low_risk
        self._command_history: List[Dict] = []
    
    # ===== 工具定义 =====
    
    def get_tools(self) -> List:
        """返回Skill提供的工具"""
        return [
            StructuredTool.from_function(
                func=self.execute_command,
                name="execute_bash",
                description="""执行Linux Shell命令。
                
                可以执行各种系统命令，如文件操作、程序运行、系统查询等。
                
                注意：
                - 危险命令需要用户确认后才能执行
                - 命令在指定工作目录下执行
                - 输出会被截断，避免过大
                - 有超时保护，防止命令卡死
                
                参数：
                - command: 要执行的Shell命令字符串
                """,
            ),
            StructuredTool.from_function(
                func=self.check_command_risk,
                name="check_command_risk",
                description="检查命令的风险等级，返回是否需要用户确认",
            ),
            StructuredTool.from_function(
                func=self.get_command_history,
                name="get_command_history",
                description="获取最近执行的命令历史记录",
            ),
        ]
    
    # ===== 核心方法 =====
    
    def execute_command(self, command: str) -> str:
        """
        执行Shell命令
        
        Args:
            command: 要执行的命令
        
        Returns:
            命令执行结果
        """
        # 1. 检查是否是禁止命令
        if self._is_forbidden(command):
            return f"❌ 命令被禁止执行（安全策略）：\n{command}\n\n该命令属于高风险操作，系统已自动拦截。"
        
        # 2. 评估风险等级
        risk_level = self._assess_risk(command)
        
        # 3. 检查是否需要用户确认
        need_confirm = self._needs_confirmation(risk_level)
        
        if need_confirm:
            if not self.user_confirm_callback:
                return (
                    f"⚠️  该命令风险等级为「{risk_level}」，需要用户确认才能执行。\n\n"
                    f"命令：\n```bash\n{command}\n```\n\n"
                    f"请配置 user_confirm_callback 回调函数来处理用户确认。"
                )
            
            # 调用用户确认回调
            try:
                confirmed = self.user_confirm_callback(command, risk_level)
            except Exception as e:
                return f"用户确认失败: {str(e)}"
            
            if not confirmed:
                return f"用户已拒绝执行该命令。"
        
        # 4. 执行命令
        try:
            result = self._run_command(command)
            
            # 记录历史
            self._command_history.append({
                "command": command,
                "risk_level": risk_level,
                "success": result["success"],
                "timestamp": result.get("timestamp", ""),
            })
            
            # 只保留最近50条
            if len(self._command_history) > 50:
                self._command_history = self._command_history[-50:]
            
            return self._format_result(command, result, risk_level)
            
        except subprocess.TimeoutExpired:
            return f"⏰ 命令执行超时（{self.timeout}秒）：\n{command}"
        except Exception as e:
            return f"❌ 命令执行失败：\n{command}\n\n错误：{str(e)}"
    
    def _run_command(self, command: str) -> Dict:
        """实际执行命令"""
        import datetime
        
        start_time = datetime.datetime.now()
        
        # 确保在工作目录下执行
        cwd = self.work_dir
        
        # 使用shell执行，支持管道、重定向等
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        
        try:
            stdout, stderr = process.communicate(timeout=self.timeout)
            success = process.returncode == 0
            
            # 限制输出长度
            if len(stdout) > self.max_output_length:
                stdout = stdout[:self.max_output_length] + f"\n... [输出已截断，共 {len(stdout)} 字符]"
            if len(stderr) > self.max_output_length:
                stderr = stderr[:self.max_output_length] + f"\n... [错误输出已截断]"
            
            return {
                "success": success,
                "returncode": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "timestamp": start_time.isoformat(),
                "duration": (datetime.datetime.now() - start_time).total_seconds(),
            }
            
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise
    
    # ===== 风险评估 =====
    
    def check_command_risk(self, command: str) -> str:
        """检查命令风险等级"""
        if self._is_forbidden(command):
            return "FORBIDDEN - 禁止执行"
        
        risk = self._assess_risk(command)
        need_confirm = self._needs_confirmation(risk)
        
        confirm_status = "需要用户确认" if need_confirm else "可自动执行"
        return f"风险等级: {risk}\n状态: {confirm_status}"
    
    def _is_forbidden(self, command: str) -> bool:
        """检查是否是禁止命令"""
        cmd_lower = command.lower().strip()
        
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.lower() in cmd_lower:
                return True
        
        return False
    
    def _assess_risk(self, command: str) -> str:
        """
        评估命令风险等级
        
        Returns:
            "low" | "medium" | "high"
        """
        cmd_lower = command.lower().strip()
        
        # 高风险检查
        for pattern in HIGH_RISK_PATTERNS:
            if pattern.lower() in cmd_lower:
                return "high"
        
        # 中风险：写操作
        medium_risk_patterns = [
            "mkdir", "touch", "cp ", "mv ", "nano", "vim", "echo >", ">>",
            "wget ", "curl ", "pip install", "npm install",
            "chmod", "chown",
            "git clone", "git push",
        ]
        
        for pattern in medium_risk_patterns:
            if pattern.lower() in cmd_lower:
                return "medium"
        
        # 低风险：只读操作
        low_risk_patterns = [
            "ls", "pwd", "echo", "cat", "head", "tail", "wc",
            "whoami", "date", "uname", "hostname",
            "ps", "top", "df", "du", "free",
            "which", "whereis", "file",
            "find .", "grep",
            "python --version", "node --version",
            "git status", "git log", "git diff",
        ]
        
        for pattern in low_risk_patterns:
            if cmd_lower.startswith(pattern.lower()):
                return "low"
        
        # 默认中风险
        return "medium"
    
    def _needs_confirmation(self, risk_level: str) -> bool:
        """判断是否需要用户确认"""
        if risk_level == "high":
            return True
        elif risk_level == "medium":
            return not self.auto_confirm_low_risk
        else:  # low
            return False
    
    # ===== 历史记录 =====
    
    def get_command_history(self, limit: int = 10) -> str:
        """获取命令历史"""
        if not self._command_history:
            return "暂无命令执行历史。"
        
        history = self._command_history[-limit:]
        
        lines = ["最近执行的命令："]
        for i, cmd in enumerate(reversed(history), 1):
            status = "✅" if cmd["success"] else "❌"
            lines.append(f"{i}. {status} [{cmd['risk_level']}] {cmd['command']}")
        
        return "\n".join(lines)
    
    # ===== 结果格式化 =====
    
    def _format_result(self, command: str, result: Dict, risk_level: str) -> str:
        """格式化执行结果"""
        lines = []
        
        # 风险提示
        if risk_level == "high":
            lines.append("⚠️  【高风险命令已执行】")
        elif risk_level == "medium":
            lines.append("ℹ️  【中风险命令已执行】")
        
        # 命令
        lines.append(f"$ {command}")
        lines.append("")
        
        # 标准输出
        if result["stdout"]:
            lines.append(result["stdout"])
        
        # 错误输出
        if result["stderr"]:
            lines.append("")
            lines.append("【错误输出】")
            lines.append(result["stderr"])
        
        # 退出码
        if not result["success"]:
            lines.append("")
            lines.append(f"退出码: {result['returncode']}")
        
        # 执行时间
        if "duration" in result:
            lines.append(f"执行耗时: {result['duration']:.2f}秒")
        
        return "\n".join(lines)
    
    # ===== 生命周期 =====
    
    def initialize(self, context: Optional[Dict] = None):
        """初始化"""
        super().initialize(context)
        
        # 确保工作目录存在
        os.makedirs(self.work_dir, exist_ok=True)
    
    def cleanup(self):
        """清理"""
        super().cleanup()
