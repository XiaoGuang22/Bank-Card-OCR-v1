"""
树形结构面板

显示系统变量和状态信息
"""

import tkinter as tk
from tkinter import ttk
import logging

# 导入异常处理工具
try:
    from utils.exception_utils import ErrorHandler, safe_execute
except ImportError:
    # 如果异常处理工具不可用，使用简单的装饰器
    def ErrorHandler():
        class _ErrorHandler:
            @staticmethod
            def handle_ui_error(func):
                return func
        return _ErrorHandler()
    ErrorHandler = ErrorHandler()
    safe_execute = lambda **kwargs: lambda func: func

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TreeViewPanel(tk.Frame):
    """树形结构面板类
    
    使用ttk.Treeview显示系统变量和状态信息，包括AppVar节点、Result变量、
    TCP连接状态和OCR识别结果变量。
    
    验证需求: 4.2, 4.3, 4.4, 4.5, 4.6
    """
    
    def __init__(self, parent):
        """初始化树形结构面板
        
        参数:
            parent: 父窗口
        """
        super().__init__(parent, bg="white")
        
        # 节点路径到TreeView ID的映射
        self._node_map = {}
        
        self._init_ui()
        self._init_default_nodes()
    
    @ErrorHandler.handle_ui_error
    def _init_ui(self):
        """初始化UI布局"""
        # 创建TreeView容器（移除标题以节省空间）
        tree_container = tk.Frame(self, bg="white")
        tree_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        
        # 创建TreeView（减小高度）
        self._tree = ttk.Treeview(
            tree_container,
            columns=("value",),
            show="tree headings",
            height=6  # 从10减小到6
        )
        
        # 配置列
        self._tree.heading("#0", text="变量名")
        self._tree.heading("value", text="值")
        self._tree.column("#0", width=150, minwidth=100)
        self._tree.column("value", width=150, minwidth=100)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(
            tree_container,
            orient=tk.VERTICAL,
            command=self._tree.yview
        )
        self._tree.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    @ErrorHandler.handle_ui_error
    def _init_default_nodes(self):
        """初始化默认节点
        
        创建默认的节点结构：
        - AppVar
          - Result
        - OCR
        """
        # AppVar 节点
        self.add_node("", "AppVar", "")
        self.add_node("AppVar", "Result", "")
        
        # OCR 节点
        self.add_node("", "OCR", "")
    
    @safe_execute(default_return="", log_error=True, error_message="添加节点失败")
    def add_node(self, parent_path, node_name, value=""):
        """添加新节点
        
        参数:
            parent_path: 父节点路径（空字符串表示根节点）
            node_name: 节点名称
            value: 节点值（默认为空字符串）
        
        返回:
            str: 新节点的完整路径
        """
        # 构建完整路径
        if parent_path:
            full_path = f"{parent_path}.{node_name}"
        else:
            full_path = node_name
        
        # 检查节点是否已存在
        if full_path in self._node_map:
            return full_path
        
        # 获取父节点ID
        parent_id = ""
        if parent_path:
            parent_id = self._node_map.get(parent_path, "")
        
        # 插入节点
        node_id = self._tree.insert(
            parent_id,
            tk.END,
            text=node_name,
            values=(value,)
        )
        
        # 保存节点映射
        self._node_map[full_path] = node_id
        
        logger.debug(f"节点添加成功: {full_path}")
        return full_path
    
    @ErrorHandler.handle_ui_error
    def update_variable(self, path, value):
        """更新变量值
        
        参数:
            path: 变量路径（如 "AppVar.Result"）
            value: 变量值
        """
        # 检查节点是否存在
        if path not in self._node_map:
            # 如果节点不存在，尝试创建它
            parts = path.split(".")
            parent_path = ""
            for i, part in enumerate(parts):
                if i > 0:
                    parent_path = ".".join(parts[:i])
                else:
                    parent_path = ""
                
                current_path = ".".join(parts[:i+1])
                if current_path not in self._node_map:
                    self.add_node(parent_path, part, "")
        
        # 更新节点值
        node_id = self._node_map[path]
        self._tree.item(node_id, values=(str(value),))
        
        logger.debug(f"变量更新成功: {path} = {value}")
    
    @safe_execute(default_return=None, log_error=True, error_message="获取变量失败")
    def get_variable(self, path):
        """获取变量值
        
        参数:
            path: 变量路径
        
        返回:
            str: 变量值，如果节点不存在则返回None
        """
        if path not in self._node_map:
            return None
        
        node_id = self._node_map[path]
        values = self._tree.item(node_id, "values")
        
        if values:
            return values[0]
        return ""
    
    @ErrorHandler.handle_ui_error
    def clear_all(self):
        """清空所有节点"""
        self._tree.delete(*self._tree.get_children())
        self._node_map.clear()
        self._init_default_nodes()
        logger.info("树形面板清空成功")
    
    @ErrorHandler.handle_ui_error
    def expand_all(self):
        """展开所有节点"""
        def expand_recursive(item):
            self._tree.item(item, open=True)
            for child in self._tree.get_children(item):
                expand_recursive(child)
        
        for item in self._tree.get_children():
            expand_recursive(item)
            
        logger.debug("展开所有节点成功")
    
    @ErrorHandler.handle_ui_error
    def collapse_all(self):
        """折叠所有节点"""
        def collapse_recursive(item):
            self._tree.item(item, open=False)
            for child in self._tree.get_children(item):
                collapse_recursive(child)
        
        for item in self._tree.get_children():
            collapse_recursive(item)
            
        logger.debug("折叠所有节点成功")


# 测试代码
if __name__ == "__main__":
    root = tk.Tk()
    root.title("树形结构面板测试")
    root.geometry("400x500")
    
    panel = TreeViewPanel(root)
    panel.pack(fill=tk.BOTH, expand=True)
    
    # 测试按钮
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=10)
    
    def test_update():
        panel.update_variable("AppVar.Result", "PASS")
        panel.update_variable("TcpP5024", "Connected")
        panel.update_variable("OCR", "Ready")
        panel.add_node("OCR", "Confidence", "0.95")
    
    def test_expand():
        panel.expand_all()
    
    def test_collapse():
        panel.collapse_all()
    
    tk.Button(btn_frame, text="更新变量", command=test_update).pack(side=tk.LEFT, padx=5)
    tk.Button(btn_frame, text="展开全部", command=test_expand).pack(side=tk.LEFT, padx=5)
    tk.Button(btn_frame, text="折叠全部", command=test_collapse).pack(side=tk.LEFT, padx=5)
    
    root.mainloop()
