import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
from PIL import Image, ImageTk
import cv2
import numpy as np
import os
import shutil
import platform
import random
import time
import json
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__) 

class ResponsiveScrollableFrame(ttk.Frame):
    """ [UI组件] 响应式滚动容器 (保持不变) """
    def __init__(self, container, resize_callback=None, bg_color="#f0f0f2", *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=bg_color)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=bg_color)

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.resize_callback = resize_callback
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.scrollable_frame.bind('<Enter>', self._bound_to_mousewheel)
        self.scrollable_frame.bind('<Leave>', self._unbound_to_mousewheel)
        self.canvas.bind('<Enter>', self._bound_to_mousewheel)
        self.canvas.bind('<Leave>', self._unbound_to_mousewheel)

    def _on_canvas_configure(self, event):
        """Canvas配置变化处理 - 添加异常保护"""
        try:
            self.canvas.itemconfig(self.canvas_window, width=event.width)
            if self.resize_callback: 
                self.resize_callback(event.width)
        except Exception as e:
            logger.warning(f"Canvas配置更新失败: {e}")

    def _bound_to_mousewheel(self, event):
        """绑定鼠标滚轮事件 - 添加异常保护"""
        try:
            self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
            self.canvas.bind_all("<Button-4>", self._on_mousewheel)
            self.canvas.bind_all("<Button-5>", self._on_mousewheel)
        except Exception as e:
            logger.warning(f"鼠标滚轮绑定失败: {e}")

    def _unbound_to_mousewheel(self, event):
        """解绑鼠标滚轮事件 - 添加异常保护"""
        try:
            self.canvas.unbind_all("<MouseWheel>")
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")
        except Exception as e:
            logger.warning(f"鼠标滚轮解绑失败: {e}")

    def _on_mousewheel(self, event):
        """鼠标滚轮处理 - 添加异常保护"""
        try:
            if platform.system() == 'Windows':
                self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            elif platform.system() == 'Darwin':
                self.canvas.yview_scroll(int(-1*event.delta), "units")
            else:
                if event.num == 4: self.canvas.yview_scroll(-1, "units")
                elif event.num == 5: self.canvas.yview_scroll(1, "units")
        except Exception as e:
            logger.warning(f"鼠标滚轮处理失败: {e}")

class BankCardTrainerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("银行卡OCR模板标定工具")
        self.root.geometry("1400x950")

        # === 核心变量 ===
        self.image_path = None
        self.original_image = None
        self.tk_image = None
        self.zoom_scale = 1.0
        self.rect_start = None; self.rect_end = None
        self.current_rect_id = None
        
        self.roi_layout_config = {}
        
        # [修改] 增加 FirstDigitAnchor 类型
        self.field_types = ["CardNumber", "Name", "Date", "FirstDigitAnchor"]
        self.char_widgets = {}
        self.section_frames = {}
        
        self.color_map = {
            "CardNumber": "#ff0000",
            "Name": "#0000ff",
            "Date": "#008000",
            "FirstDigitAnchor": "#ff00ff" # 紫色显示锚点
        }
        
        self.solutions_root = "solutions" 
        self.current_solution_name = None 
        if not os.path.exists(self.solutions_root): os.makedirs(self.solutions_root)
        
        self.norm_width = 32
        self.norm_height = 48
        self.card_width = 60 

        self._setup_ui()
        
        for field in self.field_types:
            self._register_field(field, create_ui=True)
            
        self.refresh_solution_list()

    def _register_field(self, field_name, create_ui=False):
        if field_name not in self.field_types:
            self.field_types.append(field_name)
            
        if field_name not in self.char_widgets:
            self.char_widgets[field_name] = {'existing': [], 'new': []}
            
        if field_name not in self.color_map:
            r = lambda: random.randint(0, 200)
            self.color_map[field_name] = '#%02x%02x%02x' % (r(), r(), r())

        if create_ui and field_name not in self.section_frames:
            color = self.color_map[field_name]
            
            main_lf = tk.LabelFrame(self.scroll_container.scrollable_frame, text=f" {field_name} ", 
                                    bg="white", font=("微软雅黑", 11, "bold"), fg=color, padx=5, pady=5)
            
            lf_existing = tk.LabelFrame(main_lf, text="📂 已归档模板", bg="#f9f9f9", fg="#666", padx=5, pady=5)
            lf_existing.pack(fill=tk.X, expand=True, pady=(0, 5))
            
            lf_new = tk.LabelFrame(main_lf, text="🆕 本次提取结果", bg="#e8f5e9", fg="#2e7d32", padx=5, pady=5)
            
            self.section_frames[field_name] = {
                'main': main_lf,
                'existing': lf_existing,
                'new': lf_new
            }
            
            if hasattr(self, 'cmb_field_type'):
                self.cmb_field_type['values'] = self.field_types

    def add_custom_field(self):
        """添加自定义字段 - 添加输入验证和异常处理"""
        try:
            name = simpledialog.askstring("添加字段", "请输入新字段名称 (英文/数字):")
            if not name: 
                return
            
            name = name.strip()
            if not name.isalnum():
                messagebox.showerror("错误", "字段名只能包含字母和数字")
                return
            if name in self.field_types:
                messagebox.showerror("提示", "该字段已存在")
                return
                
            self._register_field(name, create_ui=True)
            
            if self.current_solution_name:
                path = os.path.join(self.solutions_root, self.current_solution_name, name)
                if not os.path.exists(path):
                    os.makedirs(path)
                    
            self.var_field_type.set(name)
            self._reflow_grid()
            messagebox.showinfo("成功", f"已添加字段: {name}")
            
        except Exception as e:
            logger.error(f"添加自定义字段失败: {e}")
            messagebox.showerror("错误", f"添加字段失败: {str(e)}")

    def cv2_imread_chinese(self, file_path, flags=cv2.IMREAD_COLOR):
        """支持中文路径的图像读取 - 添加异常处理"""
        try:
            img_data = np.fromfile(file_path, dtype=np.uint8)
            img = cv2.imdecode(img_data, flags)
            if img is None:
                logger.warning(f"图像解码失败: {file_path}")
            return img
        except Exception as e:
            logger.error(f"读取图片失败: {file_path} - {e}")
            return None

    def _setup_ui(self):
        # 1. 顶部栏
        solution_frame = tk.Frame(self.root, bd=0, bg="#fafafa")
        solution_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        tk.Label(solution_frame, text="当前方案:", font=("微软雅黑", 10), bg="#fafafa", fg="#555").pack(side=tk.LEFT, padx=5)
        self.cmb_solutions = ttk.Combobox(solution_frame, state="readonly", width=20)
        self.cmb_solutions.pack(side=tk.LEFT, padx=5)
        self.cmb_solutions.bind("<<ComboboxSelected>>", self.on_solution_selected) # 这里绑定了事件
        
        tk.Button(solution_frame, text="+ 方案", command=self.create_solution, relief=tk.FLAT, bg="#e3f2fd", fg="#1565c0").pack(side=tk.LEFT, padx=2)
        tk.Button(solution_frame, text="x 删除", command=self.delete_solution, relief=tk.FLAT, bg="#ffebee", fg="#c62828").pack(side=tk.LEFT, padx=2)
        
        tk.Label(solution_frame, text="| 标注字段:", font=("微软雅黑", 10, "bold"), bg="#fafafa", fg="#333").pack(side=tk.LEFT, padx=15)
        self.var_field_type = tk.StringVar(value="CardNumber")
        self.cmb_field_type = ttk.Combobox(solution_frame, textvariable=self.var_field_type, state="readonly", width=15)
        self.cmb_field_type['values'] = self.field_types
        self.cmb_field_type.pack(side=tk.LEFT, padx=5)
        self.cmb_field_type.bind("<<ComboboxSelected>>", self._on_field_selected) 
        
        # 锚点复选框
        self.var_is_anchor = tk.BooleanVar(value=False)
        self.chk_anchor = tk.Checkbutton(solution_frame, text="设为主锚点", variable=self.var_is_anchor, 
                                         command=self._on_anchor_toggled, bg="#fafafa", font=("微软雅黑", 9))
        self.chk_anchor.pack(side=tk.LEFT, padx=5)
        
        tk.Button(solution_frame, text="+ 字段", command=self.add_custom_field, relief=tk.FLAT, bg="#f3e5f5", fg="#7b1fa2").pack(side=tk.LEFT, padx=2)
        
        self.lbl_status = tk.Label(solution_frame, text="未选择方案", fg="#999", bg="#fafafa")
        self.lbl_status.pack(side=tk.LEFT, padx=20)

        # 2. 工具栏
        toolbar = tk.Frame(self.root, bd=0, bg="white")
        toolbar.pack(side=tk.TOP, fill=tk.X)
        
        def create_tool_btn(parent, text, cmd, bg_color):
            return tk.Button(parent, text=text, command=cmd, relief=tk.FLAT, bg=bg_color, fg="#333", padx=15, pady=5, font=("微软雅黑", 9))

        create_tool_btn(toolbar, "1. 打开图片", self.load_image, "#e1f5fe").pack(side=tk.LEFT, padx=2, pady=5)
        self.btn_process = create_tool_btn(toolbar, "2. 执行提取", self.process_selection, "#fff9c4")
        self.btn_process.pack(side=tk.LEFT, padx=2, pady=5)
        self.btn_clear = create_tool_btn(toolbar, "3. 还原列表", self.reset_list, "#ffab91")
        self.btn_clear.pack(side=tk.LEFT, padx=2, pady=5)
        self.btn_save = create_tool_btn(toolbar, "4. 保存全部", self.save_templates, "#c8e6c9")
        self.btn_save.pack(side=tk.LEFT, padx=2, pady=5)

        tk.Label(toolbar, text="工作模式:", font=("微软雅黑", 9, "bold"), bg="white", fg="#555").pack(side=tk.LEFT, padx=(15, 2))
        self.var_work_mode = tk.StringVar(value="Full Mode")
        self.cmb_mode = ttk.Combobox(toolbar, textvariable=self.var_work_mode, state="readonly", width=12)
        self.cmb_mode['values'] = ("Full Mode", "Layout Only", "Template Only")
        self.cmb_mode.pack(side=tk.LEFT, padx=2)
        self.cmb_mode.bind("<<ComboboxSelected>>", self._on_mode_change)

        self.var_show_debug = tk.BooleanVar(value=False)
        cb_debug = tk.Checkbutton(toolbar, text="过程图", variable=self.var_show_debug, bg="white", font=("微软雅黑", 9), activebackground="white")
        cb_debug.pack(side=tk.LEFT, padx=10)

        tk.Label(toolbar, text="提示: 请框选 FirstDigitAnchor (框住首字及其抖动范围)", bg="white", fg="#f57c00").pack(side=tk.LEFT, padx=(10, 5))

        tk.Frame(self.root, height=1, bg="#e0e0e0").pack(side=tk.TOP, fill=tk.X)

        # 3. 主界面
        main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#f0f0f2")
        main_pane.pack(fill=tk.BOTH, expand=True)

        self.canvas_frame = tk.Frame(main_pane, bg="#333")
        main_pane.add(self.canvas_frame, minsize=600)
        
        self.v_bar = tk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL)
        self.h_bar = tk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL)
        self.canvas = tk.Canvas(self.canvas_frame, bg="#2b2b2b", cursor="cross", xscrollcommand=self.h_bar.set, yscrollcommand=self.v_bar.set, highlightthickness=0)
        self.v_bar.config(command=self.canvas.yview)
        self.h_bar.config(command=self.canvas.xview)
        self.v_bar.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Control-MouseWheel>", self.on_zoom)
        self.canvas.bind("<ButtonPress-2>", self.on_pan_start)
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)

        self.editor_frame = tk.Frame(main_pane, bg="#f0f0f2")
        main_pane.add(self.editor_frame, minsize=450)
        
        self.scroll_container = ResponsiveScrollableFrame(self.editor_frame, resize_callback=self.on_right_panel_resize, bg_color="#f0f0f2")
        self.scroll_container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

    # [修复] 之前遗漏的方法：下拉框选择事件
    def on_solution_selected(self, event):
        self.current_solution_name = self.cmb_solutions.get()
        if not self.current_solution_name: return
        self.lbl_status.config(text=f"正在加载方案: {self.current_solution_name} ...", fg="black")
        self.root.update()
        self.load_solution_data()

    def _on_field_selected(self, event):
        self.canvas.focus_set()
        current_field = self.var_field_type.get()
        
        is_anchor = False
        if current_field in self.roi_layout_config:
            data = self.roi_layout_config[current_field]
            if isinstance(data, dict) and data.get("is_anchor", False):
                is_anchor = True
        
        self.var_is_anchor.set(is_anchor)

    def _on_anchor_toggled(self):
        current_field = self.var_field_type.get()
        is_anchor = self.var_is_anchor.get()
        
        if is_anchor:
            # 互斥逻辑：取消其他字段的锚点
            for field, data in self.roi_layout_config.items():
                if isinstance(data, dict):
                    data["is_anchor"] = False
        
        if current_field in self.roi_layout_config:
             self.roi_layout_config[current_field]["is_anchor"] = is_anchor
             
        self._refresh_canvas_image()

    def _on_mode_change(self, event):
        mode = self.var_work_mode.get()
        print(f"Mode changed to: {mode}")

    def on_right_panel_resize(self, width):
        self._reflow_grid(container_width=width)

    def _reflow_grid(self, container_width=None):
        if container_width is None:
            container_width = self.scroll_container.canvas.winfo_width()
            if container_width <= 1: container_width = 400

        available_width = container_width - 60 
        cols = max(1, available_width // (self.card_width + 10))
        
        for section in self.field_types:
            if section not in self.section_frames: continue

            widgets_e = self.char_widgets[section]['existing']
            frame_e = self.section_frames[section]['existing']
            main_lf = self.section_frames[section]['main']
            
            has_content = False

            if widgets_e:
                has_content = True
                frame_e.pack(fill=tk.X, expand=True, pady=(0, 5))
                for index, item in enumerate(widgets_e):
                    row = index // cols
                    col = index % cols
                    item['frame'].grid(in_=frame_e, row=row, column=col, padx=5, pady=5, sticky="n")
            else:
                frame_e.pack_forget() 
                
            widgets_n = self.char_widgets[section]['new']
            frame_n = self.section_frames[section]['new']
            
            if widgets_n:
                has_content = True
                frame_n.pack(fill=tk.X, expand=True) 
                for index, item in enumerate(widgets_n):
                    row = index // cols
                    col = index % cols
                    item['frame'].grid(in_=frame_n, row=row, column=col, padx=5, pady=5, sticky="n")
            else:
                frame_n.pack_forget()

            if has_content:
                main_lf.pack(fill=tk.X, expand=True, padx=10, pady=5)
            else:
                main_lf.pack_forget()

    def _add_char_grid_item(self, cv2_img, section_type, label_text="", is_new=False):
        target_key = 'new' if is_new else 'existing'
        target_list = self.char_widgets[section_type][target_key]
        parent_frame = self.section_frames[section_type][target_key]
        
        bg_color = "white"
        item_data = {'image': cv2_img, 'type': section_type, 'is_new': is_new}
        
        frame = tk.Frame(parent_frame, bd=0, bg=bg_color, highlightthickness=1, highlightbackground="#d0d0d0")
        item_data['frame'] = frame

        btn_del = tk.Button(frame, text="×", bg=bg_color, fg="#999", activebackground="#ffcdd2", activeforeground="#ff1744", 
                            font=("Arial", 10), bd=0, relief=tk.FLAT, cursor="hand2", 
                            command=lambda: self.delete_single_char(item_data))
        btn_del.place(relx=1.0, x=0, y=0, anchor="ne", width=20, height=20)

        img_pil = Image.fromarray(cv2_img)
        img_tk = ImageTk.PhotoImage(img_pil)
        lbl_img = tk.Label(frame, bg=bg_color, image=img_tk)
        lbl_img.image = img_tk
        lbl_img.pack(side=tk.TOP, pady=(15, 2), padx=5)

        entry = tk.Entry(frame, font=("Arial", 14, "bold"), width=3, justify="center", bd=1, relief=tk.SOLID, highlightthickness=0)
        entry.pack(side=tk.BOTTOM, pady=(0, 10))
        entry.bind("<Return>", lambda e: self._focus_next(entry, section_type, target_key))
        
        entry.insert(0, label_text)
        item_data['entry'] = entry

        target_list.append(item_data)
        self._reflow_grid()

    def delete_single_char(self, item_to_delete):
        section = item_to_delete['type']
        is_new = item_to_delete['is_new']
        target_key = 'new' if is_new else 'existing'
        target_list = self.char_widgets[section][target_key]
        
        target_index = -1
        for i, item in enumerate(target_list):
            if item is item_to_delete:
                target_index = i
                break
        if target_index != -1:
            item_to_delete['frame'].destroy()
            target_list.pop(target_index)
            self._reflow_grid()
            self._check_save_state()

    def reset_list(self):
        total_new = 0
        for s in self.char_widgets:
            total_new += len(self.char_widgets[s]['new'])
            
        if total_new == 0: 
            messagebox.showinfo("提示", "当前没有新提取的内容，无需还原。")
            return
        
        if not messagebox.askyesno("还原列表", "确定要放弃本次新提取的所有字符？"): return
        self.load_solution_data()

    def _focus_next(self, current_entry, section, target_key):
        widgets = self.char_widgets[section][target_key]
        found = False
        for item in widgets:
            if found: item['entry'].focus_set(); return
            if item['entry'] == current_entry: found = True

    def _clear_editor(self):
        for section in self.char_widgets:
            for item in self.char_widgets[section]['existing']:
                item['frame'].destroy()
            self.char_widgets[section]['existing'] = []
            
            for item in self.char_widgets[section]['new']:
                item['frame'].destroy()
            self.char_widgets[section]['new'] = []
            
        self.btn_save.config(state=tk.DISABLED)
        self.btn_clear.config(state=tk.DISABLED)
        self._reflow_grid()

    def load_image(self):
        """加载图片 - 添加文件验证和异常处理"""
        try:
            file_path = filedialog.askopenfilename(
                filetypes=[("Image files", "*.bmp *.jpg *.png")]
            )
            if not file_path: 
                return
                
            # 验证文件存在性
            if not os.path.exists(file_path):
                messagebox.showerror("错误", "选择的文件不存在")
                return
                
            self.image_path = file_path
            self.original_image = self.cv2_imread_chinese(file_path)
            
            if self.original_image is not None:
                self.zoom_scale = self._get_fit_scale()
                self._refresh_canvas_image()
                self.btn_process.config(state=tk.NORMAL)
                logger.info(f"成功加载图片: {file_path}")
            else:
                messagebox.showerror("错误", "无法读取图片，请检查文件格式")
                
        except Exception as e:
            logger.error(f"加载图片失败: {e}")
            messagebox.showerror("错误", f"加载图片时发生错误: {str(e)}")

    def _get_fit_scale(self):
        h, w = self.original_image.shape[:2]
        canvas_w = self.canvas.winfo_width() or 800
        canvas_h = self.canvas.winfo_height() or 600
        return min(canvas_w/w, canvas_h/h, 1.0)

    def _refresh_canvas_image(self):
        """刷新Canvas图像 - 添加图像处理异常保护"""
        try:
            if self.original_image is None:
                return
                
            h, w = self.original_image.shape[:2]
            new_w = int(w * self.zoom_scale)
            new_h = int(h * self.zoom_scale)
            
            img_resized = cv2.resize(self.original_image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
            self.tk_image = ImageTk.PhotoImage(Image.fromarray(img_rgb))
            
            self.canvas.delete("img")
            self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image, tags="img")
            self.canvas.config(scrollregion=(0, 0, new_w, new_h))
            
            self._draw_saved_rois()
            
        except Exception as e:
            logger.error(f"刷新Canvas图像失败: {e}")
            messagebox.showerror("错误", "图像显示失败")

    def _draw_saved_rois(self):
        self.canvas.delete("saved_roi_visual")
        if not self.roi_layout_config: return
        
        for field, data in self.roi_layout_config.items():
            # 兼容：如果数据是字典，取 roi
            if isinstance(data, dict): 
                coords = data.get("search_area", data["roi"]) # 优先显示用户的大框
                is_anchor = data.get("is_anchor", False)
            else: 
                coords = data
                is_anchor = False
                
            if not coords or len(coords) != 4: continue
            
            x, y, w, h = coords
            color = self.color_map.get(field, "#000000")
            sx = x * self.zoom_scale
            sy = y * self.zoom_scale
            sw = w * self.zoom_scale
            sh = h * self.zoom_scale
            
            # 特殊显示 FirstDigitAnchor
            line_width = 3 if is_anchor or field == "FirstDigitAnchor" else 2
            dash = None if is_anchor or field == "FirstDigitAnchor" else (4, 4)
            tag_text = f"★ {field}" if is_anchor else f"[布局] {field}"
            
            self.canvas.create_rectangle(sx, sy, sx+sw, sy+sh, 
                                         outline=color, width=line_width, dash=dash, 
                                         tags="saved_roi_visual")
            self.canvas.create_text(sx, sy-15, text=tag_text, 
                                    fill=color, anchor="sw", font=("Arial", 9, "bold"), 
                                    tags="saved_roi_visual")

    def on_zoom(self, event):
        if self.original_image is None: return
        factor = 1.1 if event.delta > 0 else 0.9
        new_scale = self.zoom_scale * factor
        if 0.1 < new_scale < 10.0:
            self.zoom_scale = new_scale
            self._refresh_canvas_image()

    def on_pan_start(self, event): self.canvas.scan_mark(event.x, event.y)
    def on_pan_drag(self, event): self.canvas.scan_dragto(event.x, event.y, gain=1)
    
    def on_mouse_down(self, event):
        if self.original_image is None: return
        self.rect_start = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if self.current_rect_id: self.canvas.delete(self.current_rect_id)
        self.canvas.delete("roi_label")

    def on_mouse_drag(self, event):
        if not self.rect_start: return
        if self.current_rect_id: self.canvas.delete(self.current_rect_id)
        self.canvas.delete("roi_label")
        current_type = self.var_field_type.get()
        box_color = self.color_map.get(current_type, "#000000") 
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.current_rect_id = self.canvas.create_rectangle(self.rect_start[0], self.rect_start[1], cx, cy, outline=box_color, width=2)
        text_x = min(cx, self.rect_start[0])
        text_y = min(cy, self.rect_start[1]) - 15
        if text_y < 0: text_y = min(cy, self.rect_start[1]) + 5
        self.canvas.create_text(text_x, text_y, text=current_type, fill=box_color, anchor="nw", font=("Arial", 10, "bold"), tags="roi_label")

    def on_mouse_up(self, event):
        if not self.rect_start: return
        self.rect_end = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        self.btn_process.config(state=tk.NORMAL)

    def resize_with_padding(self, image, target_size):
        h, w = image.shape[:2]
        target_w, target_h = target_size
        scale = min(target_w / w, target_h / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        resized = cv2.resize(image, (new_w, new_h))
        canvas = np.full((target_h, target_w), 255, dtype=np.uint8)
        x_offset = (target_w - new_w) // 2
        y_offset = (target_h - new_h) // 2
        canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
        return canvas

    def sort_multiline_chars(self, chars_data):
        if not chars_data: return []
        # 先按 Y 坐标排序
        chars_data.sort(key=lambda b: b[1])
        
        lines = []
        current_line = [chars_data[0]]
        
        # 【修改点在此】显式初始化 ref_h，取第一个字符的高度 (索引3是高度)
        ref_h = chars_data[0][3]
        
        for i in range(1, len(chars_data)):
            curr = chars_data[i]
            prev = current_line[-1]
            
            # 现在的 ref_h 已经被初始化了，不会报错
            if abs(curr[1] - prev[1]) < ref_h * 0.6:
                current_line.append(curr)
            else:
                current_line.sort(key=lambda b: b[0])
                lines.append(current_line)
                current_line = [curr]
                # 更新新一行的参考高度
                ref_h = curr[3]
        
        current_line.sort(key=lambda b: b[0])
        lines.append(current_line)
        
        return [item for sublist in lines for item in sublist]

    def _display_debug_images(self, step_images):
        win = tk.Toplevel(self.root)
        win.title("算法处理步骤可视化 (中间过程)")
        win.geometry("900x600")
        
        canvas = tk.Canvas(win, bg="#f0f0f0")
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#f0f0f0")
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        row = 0
        col = 0
        MAX_COLS = 3
        
        for title, img_array in step_images.items():
            frame = tk.LabelFrame(scrollable_frame, text=title, font=("Arial", 10, "bold"), bg="white", padx=5, pady=5)
            frame.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            
            if len(img_array.shape) == 2:
                img_rgb = cv2.cvtColor(img_array, cv2.COLOR_GRAY2RGB)
            else:
                img_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
            
            h, w = img_rgb.shape[:2]
            if w < 150:
                scale = 3.0
                img_rgb = cv2.resize(img_rgb, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_NEAREST)
            
            pil_img = Image.fromarray(img_rgb)
            tk_img = ImageTk.PhotoImage(pil_img)
            
            lbl = tk.Label(frame, image=tk_img, bg="white")
            lbl.image = tk_img 
            lbl.pack()
            
            col += 1
            if col >= MAX_COLS:
                col = 0
                row += 1

    # [修正版] process_selection
    # 核心逻辑：记录“双重坐标”——用户的搜索大框 + 算法吸附的墨迹小框
    def process_selection(self):
        if not self.rect_start or not self.rect_end: return
        
        # 1. 获取用户画的“搜索范围框” (Search Area)
        x1 = self.rect_start[0] / self.zoom_scale
        y1 = self.rect_start[1] / self.zoom_scale
        x2 = self.rect_end[0] / self.zoom_scale
        y2 = self.rect_end[1] / self.zoom_scale
        x_start, x_end = sorted([int(x1), int(x2)])
        y_start, y_end = sorted([int(y1), int(y2)])
        h_img, w_img = self.original_image.shape[:2]
        x_start = max(0, x_start); y_start = max(0, y_start)
        x_end = min(w_img, x_end); y_end = min(h_img, y_end)
        
        if (x_end - x_start) < 5 or (y_end - y_start) < 5: return
        
        mode = self.var_work_mode.get()
        current_type = self.var_field_type.get()
        is_anchor_field = (current_type == "FirstDigitAnchor")

        # 用户的原始框 (用于识别端的搜索范围)
        user_search_roi = [x_start, y_start, x_end - x_start, y_end - y_start]
        
        # 默认基准点也是这个框 (如果没有找到墨迹)
        final_ref_roi = user_search_roi

        # =========================================================
        # ★ 锚点逻辑：在用户的大框内，精确定位墨迹小框
        # =========================================================
        if is_anchor_field:
            roi_img = self.original_image[y_start:y_end, x_start:x_end]
            
            # 图像处理
            if len(roi_img.shape) == 3: gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
            else: gray = roi_img
                
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 3))
            eroded = cv2.erode(binary, kernel, iterations=1)
            cnts, _ = cv2.findContours(eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            valid_blobs = []
            for c in cnts:
                bx, by, bw, bh = cv2.boundingRect(c)
                if bh < 6: continue 
                if bw * bh < 20: continue
                valid_blobs.append((bx, by, bw, bh))
            
            if valid_blobs:
                # 找到最左边的墨迹
                valid_blobs.sort(key=lambda b: b[0])
                ink_x, ink_y, ink_w, ink_h = valid_blobs[0]
                
                # 计算墨迹的绝对坐标 (作为偏移计算的基准)
                true_abs_x = x_start + ink_x
                true_abs_y = y_start + ink_y
                
                final_ref_roi = [true_abs_x, true_abs_y, ink_w, ink_h]
                
                print(f"✅ 锚点记录: 搜索区{user_search_roi} -> 基准点{final_ref_roi}")
                messagebox.showinfo("锚点锁定", "已记录双重坐标：\n1. 搜索范围 (用户框)\n2. 精准基准 (首字墨迹)")
            else:
                messagebox.showwarning("警告", "框内未检测到清晰字符！\n基准点将默认使用整个搜索框。")

        # =========================================================
        # 存入内存：同时保存两个框的数据
        # =========================================================
        layout_data = {
            "roi": final_ref_roi,          # 精准的墨迹位置 (用于算减法)
            "search_area": user_search_roi, # 宽泛的用户框 (用于去哪里找)
            "is_anchor": True if is_anchor_field else self.var_is_anchor.get()
        }
        self.roi_layout_config[current_type] = layout_data
        
        self._refresh_canvas_image() 

        # 锚点或仅布局模式直接结束
        if is_anchor_field or mode == "Layout Only":
            if mode == "Layout Only": self.btn_save.config(state=tk.NORMAL)
            return

        # =========================================================
        # 3. 常规字段处理 (Full Mode)
        # =========================================================
        if mode in ["Full Mode", "Template Only"]:
            roi = self.original_image[y_start:y_end, x_start:x_end]
            
            t_start = time.perf_counter()

            padding = 10 
            roi_padded = cv2.copyMakeBorder(roi, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=(0, 0, 0))
            gray = cv2.cvtColor(roi_padded, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            
            _, binary_detect_raw = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            binary_detect = cv2.morphologyEx(binary_detect_raw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 3)))
            binary_detect = cv2.dilate(binary_detect, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)), iterations=1)
            
            img_inverted = 255 - gray
            img_template_gray = clahe.apply(img_inverted)
            _, binary_template = cv2.threshold(img_template_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

            t_end = time.perf_counter()
            cost_ms = (t_end - t_start) * 1000
            print(f"⚡ [性能统计] 图像预处理流水线耗时: {cost_ms:.4f} ms")

            if self.var_show_debug.get():
                debug_images = {
                    "1. 原始区域": roi, "2. 灰度化": gray, "4. 定位二值化": binary_detect, "7. 最终模板": binary_template
                }
                self._display_debug_images(debug_images)

            cnts, _ = cv2.findContours(binary_detect, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            candidates = []
            heights = []
            for c in cnts:
                (x, y, w, h) = cv2.boundingRect(c)
                min_h = 4 if current_type == "Name" else 8
                if h < min_h or w < 3: continue
                if w / h > 4.0: continue
                candidates.append((x, y, w, h))
                heights.append(h)

            if not candidates:
                messagebox.showinfo("提示", "未检测到字符")
                return

            if len(candidates) <= 2: valid_chars = candidates
            else:
                median_h = np.median(heights)
                valid_chars = []
                for (x, y, w, h) in candidates:
                    is_dot = (current_type == "Name" and h > 3 and 0.5 < w/float(h) < 2.0)
                    if not is_dot and h < median_h * 0.5: continue
                    if h > median_h * 1.8: continue
                    valid_chars.append((x, y, w, h))

            valid_chars = self.sort_multiline_chars(valid_chars)

            count = 0
            for (x, y, w, h) in valid_chars:
                char_roi = binary_template[y:y+h, x:x+w]
                char_roi_resized = self.resize_with_padding(char_roi, (self.norm_width, self.norm_height))
                self._add_char_grid_item(char_roi_resized, current_type, is_new=True)
                count += 1
            
            if count > 0:
                self._check_save_state()
            else:
                messagebox.showinfo("提示", "未能识别出字符")

    def _check_save_state(self):
        total = 0
        for s in self.char_widgets:
            total += len(self.char_widgets[s]['existing']) + len(self.char_widgets[s]['new'])
        
        if total > 0 or self.roi_layout_config:
            if self.current_solution_name:
                self.btn_save.config(state=tk.NORMAL)
                self.btn_clear.config(state=tk.NORMAL)
        else:
            self.btn_save.config(state=tk.DISABLED)
            self.btn_clear.config(state=tk.DISABLED)

    def refresh_solution_list(self):
        if not os.path.exists(self.solutions_root): os.makedirs(self.solutions_root)
        folders = [f for f in os.listdir(self.solutions_root) if os.path.isdir(os.path.join(self.solutions_root, f))]
        self.cmb_solutions['values'] = folders
        if self.current_solution_name in folders:
            self.cmb_solutions.set(self.current_solution_name)
            self.lbl_status.config(text=f"当前方案: {self.current_solution_name}", fg="green")
            self.load_solution_data()
        else:
            self.cmb_solutions.set(''); self.current_solution_name = None; self.lbl_status.config(text="请选择或新建方案", fg="red")
            self.btn_save.config(state=tk.DISABLED); self.btn_clear.config(state=tk.DISABLED)

    def create_solution(self):
        """创建解决方案 - 添加输入验证和文件操作异常处理"""
        try:
            name = simpledialog.askstring("新建方案", "请输入解决方案名称:")
            if not name: 
                return
                
            # 输入验证
            name = name.strip()
            if not name:
                messagebox.showerror("错误", "方案名称不能为空")
                return
                
            if any(c in '<>:"/\\|?*' for c in name): 
                messagebox.showerror("错误", "方案名称包含非法字符")
                return
                
            path = os.path.join(self.solutions_root, name)
            if os.path.exists(path): 
                messagebox.showwarning("提示", "方案已存在")
                return
                
            # 创建目录结构
            os.makedirs(path)
            for sub in self.field_types:
                os.makedirs(os.path.join(path, sub), exist_ok=True)
                
            self.current_solution_name = name
            self.refresh_solution_list()
            messagebox.showinfo("成功", f"已创建方案 '{name}'")
            logger.info(f"创建解决方案成功: {name}")
            
        except Exception as e:
            logger.error(f"创建解决方案失败: {e}")
            messagebox.showerror("错误", f"创建方案失败: {str(e)}")

    def delete_solution(self):
        """删除解决方案 - 添加文件操作异常处理"""
        try:
            name = self.cmb_solutions.get()
            if not name: 
                return
                
            if not messagebox.askyesno("删除确认", f"确定要删除方案 '{name}' 吗？\n此操作不可恢复！"):
                return
                
            solution_path = os.path.join(self.solutions_root, name)
            if os.path.exists(solution_path):
                shutil.rmtree(solution_path)
                
            self.current_solution_name = None
            self.refresh_solution_list()
            messagebox.showinfo("提示", "删除成功")
            logger.info(f"删除解决方案成功: {name}")
            
        except Exception as e:
            logger.error(f"删除解决方案失败: {e}")
            messagebox.showerror("错误", f"删除方案失败: {str(e)}")

    def load_solution_data(self):
        """加载解决方案数据 - 添加JSON和文件操作异常处理"""
        self._clear_editor() 
        self.roi_layout_config = {} 
        
        if not self.current_solution_name: 
            return
            
        base_dir = os.path.join(self.solutions_root, self.current_solution_name)
        count = 0
        self.btn_save.config(state=tk.DISABLED)
        
        try:
            # 加载布局配置
            layout_path = os.path.join(base_dir, "layout_config.json")
            if os.path.exists(layout_path):
                try:
                    with open(layout_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        
                    # 兼容性处理旧格式
                    if "strategy" in loaded: 
                        if loaded["strategy"] == "anchor_based":
                            self.roi_layout_config["FirstDigitAnchor"] = {
                                "roi": loaded["anchor_rect"], 
                                "is_anchor": True
                            }
                            for field, roi in loaded["fields"].items():
                                self.roi_layout_config[field] = {
                                    "roi": roi, 
                                    "is_anchor": False
                                }
                        else:
                            for field, roi in loaded["fields"].items():
                                self.roi_layout_config[field] = {
                                    "roi": roi, 
                                    "is_anchor": False
                                }
                    else:
                        self.roi_layout_config = loaded
                        
                    logger.info(f"加载布局配置成功: {len(self.roi_layout_config)} 个字段")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"JSON配置文件格式错误: {e}")
                    messagebox.showwarning("警告", "配置文件格式错误，将使用默认配置")
                except Exception as e:
                    logger.error(f"加载配置文件失败: {e}")
            
            # 刷新图像显示
            if self.original_image is not None:
                self._refresh_canvas_image()

            # 发现并注册新字段
            if os.path.exists(base_dir):
                existing_folders = [d for d in os.listdir(base_dir) 
                                 if os.path.isdir(os.path.join(base_dir, d))]
                for folder in existing_folders:
                    if folder not in self.field_types:
                        self._register_field(folder, create_ui=True)

            # 加载字符模板
            for section in self.field_types:
                section_dir = os.path.join(base_dir, section)
                if not os.path.exists(section_dir): 
                    continue
                
                try:
                    files = sorted(os.listdir(section_dir))
                    for f in files:
                        if not f.lower().endswith(('.png', '.jpg', '.bmp')): 
                            continue
                        
                        # 解析文件名获取标签
                        file_stem = os.path.splitext(f)[0]
                        if '_' in file_stem:
                            prefix, sep, suffix = file_stem.rpartition('_')
                            if suffix.isdigit():
                                file_stem = prefix
                        
                        label = file_stem.replace("char_dot", ".").replace("slash", "/").replace("backslash", "\\")
                        
                        # 加载图像
                        path = os.path.join(section_dir, f)
                        img = self.cv2_imread_chinese(path, cv2.IMREAD_GRAYSCALE)
                        if img is not None:
                            self._add_char_grid_item(img, section, label_text=label, is_new=False)
                            count += 1
                            
                except Exception as e:
                    logger.error(f"加载字段 {section} 的模板失败: {e}")
                    
        except Exception as e:
            logger.error(f"加载解决方案数据失败: {e}")
            messagebox.showerror("加载错误", f"加载方案失败: {str(e)}")
            return
        
        # 更新状态
        if count > 0 or self.roi_layout_config:
            self._check_save_state()
            self.lbl_status.config(
                text=f"当前方案: {self.current_solution_name} (已加载 {count} 个模板)", 
                fg="blue"
            )
        else:
            self.lbl_status.config(
                text=f"当前方案: {self.current_solution_name} (暂无模板)", 
                fg="orange"
            )

    def save_templates(self):
        """保存模板 - 添加文件操作和JSON序列化异常处理"""
        total_chars = 0
        for s in self.char_widgets:
            total_chars += len(self.char_widgets[s]['existing']) + len(self.char_widgets[s]['new'])
            
        if total_chars == 0 and not self.roi_layout_config:
            messagebox.showinfo("提示", "没有需要保存的内容")
            return 
            
        if not self.current_solution_name: 
            messagebox.showwarning("警告", "请先选择方案")
            return
        
        if not messagebox.askokcancel("同步保存", 
                                      f"方案 '{self.current_solution_name}'\n"
                                      f"布局字段: {len(self.roi_layout_config)}\n"
                                      f"字符模板: {total_chars}\n\n"
                                      f"确定要保存吗？(旧文件将被覆盖)"):
            return
        
        saved = 0
        try:
            base_dir = os.path.join(self.solutions_root, self.current_solution_name)
            
            # 确保目录存在
            if not os.path.exists(base_dir):
                os.makedirs(base_dir)
            
            # 1. 保存布局配置
            layout_data = {"fields": {}}
            
            if "FirstDigitAnchor" in self.roi_layout_config:
                anchor_data = self.roi_layout_config["FirstDigitAnchor"]
                layout_data["strategy"] = "anchor_based"
                layout_data["anchor_rect"] = anchor_data["roi"] 
                layout_data["anchor_search_area"] = anchor_data.get("search_area", anchor_data["roi"]) 
            else:
                layout_data["strategy"] = "absolute"
                
            # 保存其他字段
            for field, config in self.roi_layout_config.items():
                if field == "FirstDigitAnchor": 
                    continue
                if isinstance(config, dict): 
                    r = config["roi"]
                else: 
                    r = config
                layout_data["fields"][field] = r 

            # 保存JSON配置
            layout_path = os.path.join(base_dir, "layout_config.json")
            try:
                with open(layout_path, "w", encoding="utf-8") as f:
                    json.dump(layout_data, f, indent=4, ensure_ascii=False)
                logger.info(f"保存布局配置成功: {layout_path}")
            except Exception as e:
                logger.error(f"保存布局配置失败: {e}")
                raise Exception(f"保存配置文件失败: {str(e)}")
            
            # 2. 保存字符模板
            for section in self.field_types:
                if section not in self.char_widgets: 
                    continue

                all_widgets = self.char_widgets[section]['existing'] + self.char_widgets[section]['new']
                if not all_widgets: 
                    continue

                target_dir = os.path.join(base_dir, section)
                
                try:
                    # 清理旧文件
                    if os.path.exists(target_dir):
                        shutil.rmtree(target_dir)
                    os.makedirs(target_dir)
                    
                    label_counters = {} 
                    
                    for item in all_widgets:
                        label = item['entry'].get().strip()
                        if not label or label.lower() == 'skip': 
                            continue
                        
                        # 安全文件名处理
                        safe_label = label.replace("\\", "backslash").replace("/", "slash").replace(".", "char_dot")
                        
                        if safe_label not in label_counters:
                            label_counters[safe_label] = 0
                        
                        filename = f"{safe_label}_{label_counters[safe_label]}.png"
                        label_counters[safe_label] += 1
                        
                        path = os.path.join(target_dir, filename)
                        img = item['image']
                        
                        # 保存图像
                        is_success, im_buf = cv2.imencode(".png", img)
                        if is_success: 
                            im_buf.tofile(path)
                            saved += 1
                        else:
                            logger.warning(f"图像编码失败: {filename}")
                            
                except Exception as e:
                    logger.error(f"保存字段 {section} 的模板失败: {e}")
                    raise Exception(f"保存字段 {section} 失败: {str(e)}")
            
            # 重新加载数据
            self.load_solution_data()
            
            messagebox.showinfo("保存成功", 
                              f"方案 '{self.current_solution_name}' 已更新。\n"
                              f"策略: {layout_data.get('strategy')}\n"
                              f"保存了 {saved} 个字符模板")
            logger.info(f"保存解决方案成功: {self.current_solution_name}, 模板数: {saved}")
                        
        except Exception as e:
            logger.error(f"保存模板失败: {e}")
            messagebox.showerror("保存失败", f"保存时发生错误: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = BankCardTrainerApp(root)
    root.mainloop()