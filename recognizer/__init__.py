"""
识别器模块

包含 OCR 识别相关的功能：
- BankCardRecognizer: 银行卡识别器
- OCRApp: OCR 应用主界面
"""

from .main_recognizer import BankCardRecognizer, OCRApp

__all__ = ['BankCardRecognizer', 'OCRApp']
