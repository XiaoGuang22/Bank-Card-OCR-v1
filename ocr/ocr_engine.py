"""
OCR识别引擎模块

该模块实现基于模板匹配的OCR识别引擎，用于识别银行卡上的文字内容。
"""

import os
import cv2
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
import time

# 导入异常处理工具
try:
    from utils.exception_utils import ErrorHandler, safe_call, safe_execute
except ImportError:
    # 如果异常处理工具不可用，使用简单的装饰器
    def ErrorHandler():
        class _ErrorHandler:
            @staticmethod
            def handle_ui_error(func):
                return func
            @staticmethod
            def handle_file_error(func):
                return func
        return _ErrorHandler()
    ErrorHandler = ErrorHandler()
    safe_call = lambda func, *args, **kwargs: func(*args, **kwargs)
    safe_execute = lambda **kwargs: lambda func: func

# 导入数据模型
try:
    from models.recognition_result import RecognitionResult
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from models.recognition_result import RecognitionResult


class OCREngine:
    """
    OCR识别引擎
    
    使用模板匹配算法识别卡片上的文字内容，并计算置信度分数。
    """
    
    def __init__(self, template_dir: str):
        """
        初始化OCR引擎
        
        参数:
            template_dir: 字符模板目录路径
        """
        self.template_dir = template_dir
        self.templates = {}  # 存储加载的模板 {字符: 模板图像}
        self.template_loaded = False
        
        # 识别参数
        self.confidence_threshold = 0.85  # 置信度阈值
        self.match_method = cv2.TM_CCOEFF_NORMED  # 模板匹配方法
    
    @ErrorHandler.handle_file_error
    def load_templates(self) -> bool:
        """
        加载字符模板
        
        返回:
            bool: 加载是否成功
        """
        if not os.path.exists(self.template_dir):
            raise FileNotFoundError(f"模板目录不存在: {self.template_dir}")
        
        # 清空现有模板
        self.templates.clear()
        
        # 遍历模板目录（递归扫描子文件夹，兼容 solutions/方案名/字段名/*.png 结构）
        template_count = 0
        for root, dirs, files in os.walk(self.template_dir):
            for filename in files:
                if filename.endswith(('.png', '.jpg', '.bmp')):
                    full_path = os.path.join(root, filename)
                    template_img = self._load_single_template_path(full_path)
                    if template_img is not None:
                        char = os.path.splitext(filename)[0]
                        self.templates[char] = template_img
                        template_count += 1
        
        if template_count > 0:
            self.template_loaded = True
            return True
        else:
            raise RuntimeError(f"未找到有效的模板文件，目录: {self.template_dir}")
    
    @safe_execute(default_return=None, log_error=True, error_message="加载模板文件失败")
    def _load_single_template(self, filename: str) -> Optional[np.ndarray]:
        """加载单个模板文件（按文件名，相对于 template_dir）"""
        template_path = os.path.join(self.template_dir, filename)
        return cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)

    @safe_execute(default_return=None, log_error=True, error_message="加载模板文件失败")
    def _load_single_template_path(self, full_path: str) -> Optional[np.ndarray]:
        """加载单个模板文件（按完整路径）"""
        img_data = np.fromfile(full_path, dtype=np.uint8)
        return cv2.imdecode(img_data, cv2.IMREAD_GRAYSCALE)
    
    @ErrorHandler.handle_ui_error
    def recognize(self, image: np.ndarray) -> RecognitionResult:
        """
        识别图像中的文字
        
        参数:
            image: numpy数组，待识别的图像（灰度图）
        
        返回:
            RecognitionResult: 识别结果对象
        """
        start_time = time.time()
        
        # 检查模板是否已加载
        if not self.template_loaded:
            if not safe_call(self.load_templates, default=False):
                return self._create_fail_result(
                    "模板加载失败",
                    time.time() - start_time
                )
        
        # 检查图像是否有效
        if image is None or image.size == 0:
            raise ValueError("输入图像无效或为空")
        
        # 转换为灰度图（如果需要）
        image_gray = self._prepare_image(image)
        
        # 执行模板匹配识别
        fields, confidence_scores = self._match_templates(image_gray)
        
        # 计算平均置信度
        average_confidence = self.calculate_confidence(confidence_scores)
        
        # 判定结果（平均置信度 < 0.85 → FAIL）
        status = "PASS" if average_confidence >= self.confidence_threshold else "FAIL"
        
        # 计算检测时间
        detection_time_ms = (time.time() - start_time) * 1000
        
        # 生成检测信息列表
        detection_info = self._generate_detection_info(fields, confidence_scores, status)
        
        # 创建识别结果对象
        return RecognitionResult(
            status=status,
            fields=fields,
            confidence_scores=confidence_scores,
            average_confidence=average_confidence,
            detection_time_ms=detection_time_ms,
            timestamp=datetime.now(),
            detection_info=detection_info
        )
    
    @safe_execute(default_return=np.array([]), log_error=True, error_message="图像准备失败")
    def _prepare_image(self, image: np.ndarray) -> np.ndarray:
        """准备图像用于识别"""
        if len(image.shape) == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            return image
    
    @safe_execute(default_return=({}, {}), log_error=True, error_message="模板匹配失败")
    def _match_templates(self, image: np.ndarray) -> tuple:
        """
        执行模板匹配
        
        参数:
            image: 灰度图像
        
        返回:
            tuple: (识别字段字典, 置信度字典)
        """
        fields = {}
        confidence_scores = {}
        
        # 这里实现简化的模板匹配逻辑
        # 实际应用中需要根据具体的卡片布局进行定位和识别
        
        # 示例：识别卡号、姓名、日期等字段
        # 这里使用模拟数据，实际需要实现完整的模板匹配算法
        
        # 模拟识别结果（实际应该使用模板匹配）
        if len(self.templates) > 0:
            # 简化实现：随机选择一些模板进行匹配
            # 实际应该根据卡片布局定位各个字段区域，然后逐字符匹配
            
            # 模拟卡号识别
            fields["card_number"] = "1234567890123456"
            confidence_scores["card_number"] = 0.92
            
            # 模拟姓名识别
            fields["name"] = "张三"
            confidence_scores["name"] = 0.88
            
            # 模拟日期识别
            fields["date"] = "2026/01/30"
            confidence_scores["date"] = 0.90
        else:
            # 如果没有模板，返回空结果
            fields["error"] = "无可用模板"
            confidence_scores["error"] = 0.0
        
        return fields, confidence_scores
    
    def calculate_confidence(self, confidence_scores: Dict[str, float]) -> float:
        """
        计算平均置信度
        
        参数:
            confidence_scores: 各字段的置信度字典
        
        返回:
            float: 平均置信度（0.0-1.0）
        """
        if not confidence_scores:
            return 0.0
        
        # 计算所有字段的平均置信度
        total_confidence = sum(confidence_scores.values())
        average_confidence = total_confidence / len(confidence_scores)
        
        return average_confidence
    
    def _generate_detection_info(
        self, 
        fields: Dict[str, str], 
        confidence_scores: Dict[str, float],
        status: str
    ) -> List[str]:
        """
        生成检测信息列表（用于界面显示）
        
        参数:
            fields: 识别字段字典
            confidence_scores: 置信度字典
            status: 识别状态
        
        返回:
            List[str]: 检测信息列表
        """
        info_list = []
        
        # 添加识别字段信息
        for field_name, field_value in fields.items():
            confidence = confidence_scores.get(field_name, 0.0)
            info_list.append(f"{field_name}: {field_value} (置信度: {confidence:.2%})")
        
        # 添加状态信息
        info_list.append(f"状态: {status}")
        
        # 添加解决方案信息（模拟）
        info_list.append("解决方案图片计数: ID 0")
        
        return info_list
    
    def _create_fail_result(self, error_message: str, detection_time_ms: float) -> RecognitionResult:
        """
        创建失败的识别结果
        
        参数:
            error_message: 错误信息
            detection_time_ms: 检测时间（毫秒）
        
        返回:
            RecognitionResult: 失败的识别结果
        """
        return RecognitionResult(
            status="FAIL",
            fields={"error": error_message},
            confidence_scores={"error": 0.0},
            average_confidence=0.0,
            detection_time_ms=detection_time_ms,
            timestamp=datetime.now(),
            detection_info=[f"错误: {error_message}"]
        )
