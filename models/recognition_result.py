"""
识别结果数据模型

定义OCR识别结果的数据结构
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List


@dataclass
class RecognitionResult:
    """识别结果数据模型"""
    
    # 识别状态
    status: str  # "PASS" 或 "FAIL"
    
    # 识别字段
    fields: Dict[str, str]  # 字段名 -> 识别内容
    # 例如: {"card_number": "1234567890", "name": "张三", "date": "2026/01/30"}
    
    # 置信度分数
    confidence_scores: Dict[str, float]  # 字段名 -> 置信度
    
    # 平均置信度
    average_confidence: float
    
    # 检测时间（毫秒）
    detection_time_ms: float
    
    # 时间戳
    timestamp: datetime
    
    # 检测信息列表（用于显示）
    detection_info: List[str] = field(default_factory=list)
    # 例如: ["问题", "数字", "用户名称", "解决方案图片计数: ID 0", "组织", "暂时（通过）"]
    
    def __post_init__(self):
        """验证数据有效性"""
        if self.status not in ["PASS", "FAIL"]:
            raise ValueError(f"Invalid status: {self.status}. Must be 'PASS' or 'FAIL'")
        
        if not 0.0 <= self.average_confidence <= 1.0:
            raise ValueError(f"Invalid average_confidence: {self.average_confidence}. Must be between 0.0 and 1.0")
        
        if self.detection_time_ms < 0:
            raise ValueError(f"Invalid detection_time_ms: {self.detection_time_ms}. Must be non-negative")
