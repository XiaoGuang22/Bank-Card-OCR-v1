#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bank Card OCR System - 主程序入口
银行卡识别系统 - 主程序入口

这是系统的统一启动入口，会启动主界面 InspectMainWindow。

使用方法:
    python main.py

作者: XiaoGuang
最后更新: 2026-01-23
"""

import sys
import os

# 添加当前目录到 Python 路径，确保可以导入模块
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 导入主窗口
from InspectMainWindow import InspectMainWindow
import tkinter as tk


def launch_main_window(username, role):
    """登录成功后启动主窗口"""
    root = tk.Tk()
    app = InspectMainWindow(root, username, role)
    # InspectMainWindow.__init__ 已通过 root.protocol("WM_DELETE_WINDOW", self._on_main_window_close)
    # 绑定了关闭事件（含保存提示），此处不再覆盖
    root.mainloop()


def main():
    """主函数：先显示登录窗口，登录成功后启动主界面"""
    print("="*60)
    print("Bank Card OCR System - 银行卡识别系统")
    print("="*60)
    print("正在启动登录界面...")
    print()

    from ui.LoginWindow import LoginWindow

    root = tk.Tk()
    LoginWindow(root, launch_main_window)
    root.mainloop()


if __name__ == "__main__":
    try:
        import traceback

        # 捕获 tkinter 回调中的异常（否则会静默崩溃）
        def _tk_exception_handler(exc_type, exc_value, exc_tb):
            msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            print(msg)
            try:
                with open("crash.log", "a", encoding="utf-8") as f:
                    import datetime
                    f.write(f"\n[{datetime.datetime.now()}]\n{msg}\n")
            except Exception:
                pass
            # 弹出错误对话框，不崩溃
            try:
                import tkinter.messagebox as mb
                mb.showerror("程序错误", f"{exc_type.__name__}: {exc_value}\n\n详情已写入 crash.log")
            except Exception:
                pass

        tk.Tk.report_callback_exception = lambda self, *args: _tk_exception_handler(*args)

        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
