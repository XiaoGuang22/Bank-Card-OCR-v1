import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import cv2
import numpy as np
import os
import time
import json
import shutil

# 导入异常处理工具
try:
    from utils.exception_utils import ErrorHandler, safe_call, safe_execute, suppress_errors
except ImportError:
    # 如果异常处理工具不可用，使用简单的装饰器
    def safe_execute(default_return=None, log_error=True, error_message="操作失败"):
        def decorator(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if log_error:
                        print(f"{error_message}: {e}")
                    return default_return
            return wrapper
        return decorator
    
    def safe_call(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"安全调用错误: {e}")
            return None

class BankCardRecognizer:
    def __init__(self):
        self.templates = {}
        self.norm_size = (64, 96) 
        self.loaded_fields = []
        self.layout_config = {}
        # ★★★ 新增：记录训练图像的标准尺寸 ★★★
        self.standard_image_size = None  # (width, height) 
        
    @safe_execute(default_return=None, log_error=True, error_message="中文路径图像读取失败")
    def cv2_imread_chinese(self, file_path, flags=cv2.IMREAD_COLOR):
        try:
            img_data = np.fromfile(file_path, dtype=np.uint8)
            img = cv2.imdecode(img_data, flags)
            return img
        except Exception as e:
            print(f"读取失败: {file_path} - {e}")
            return None

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

    @safe_execute(default_return=0, log_error=True, error_message="模板加载失败")
    def load_templates(self, solution_path):
        self.templates = {}
        self.loaded_fields = []
        self.layout_config = {} 
        self.standard_image_size = None  # 重置标准尺寸
        
        if not os.path.exists(solution_path): return 0
        total_count = 0
        
        layout_path = os.path.join(solution_path, "layout_config.json")
        if os.path.exists(layout_path):
            try:
                with open(layout_path, "r", encoding="utf-8") as f:
                    self.layout_config = json.load(f)
                    
                    # ★★★ 关键改进：读取训练图像的标准尺寸 ★★★
                    if "image_size" in self.layout_config:
                        img_size = self.layout_config["image_size"]
                        self.standard_image_size = (img_size["width"], img_size["height"])
                    else:
                        # 警告：配置文件中没有图像尺寸信息
                        pass
                        
            except Exception as e:
                print(f"Error loading layout: {e}")

        sub_folders = [d for d in os.listdir(solution_path) if os.path.isdir(os.path.join(solution_path, d))]
        for sub in sub_folders:
            self.templates[sub] = {}
            self.loaded_fields.append(sub)
            folder_path = os.path.join(solution_path, sub)
            for filename in os.listdir(folder_path):
                if filename.endswith(".png"):
                    file_stem = os.path.splitext(filename)[0]
                    if '_' in file_stem:
                        prefix, sep, suffix = file_stem.rpartition('_')
                        if suffix.isdigit(): file_stem = prefix
                    label_name = file_stem
                    
                    if label_name == "slash": label = "/"
                    elif label_name == "char_slash": label = "/"
                    elif label_name == "backslash": label = "\\"
                    elif label_name == "char_dot": label = "."
                    else: label = label_name
                    
                    path = os.path.join(folder_path, filename)
                    img = self.cv2_imread_chinese(path, cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        img = cv2.resize(img, self.norm_size)
                        _, img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
                        if label not in self.templates[sub]: self.templates[sub][label] = []
                        self.templates[sub][label].append(img)
                        total_count += 1
        return total_count

    @safe_execute(default_return=(None, None), log_error=True, error_message="图像预处理失败")
    def preprocess_image(self, roi_img):
        if roi_img is None: return None, None
        if len(roi_img.shape) == 3: gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
        else: gray = roi_img
        
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        _, binary_detect = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        binary_detect = cv2.morphologyEx(binary_detect, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 3)))
        binary_detect = cv2.dilate(binary_detect, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)), iterations=1)
        
        img_inverted = 255 - gray
        img_template_gray = clahe.apply(img_inverted)
        _, binary_template = cv2.threshold(img_template_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        return binary_detect, binary_template

    @safe_execute(default_return=("?", 0.0, None), log_error=True, error_message="字符匹配失败")
    def match_char(self, char_img, field_type="Auto", idx=0):
        best_score = -1.0
        best_label = "?"
        char_resized = self.resize_with_padding(char_img, self.norm_size)
        _, char_thresh = cv2.threshold(char_resized, 127, 255, cv2.THRESH_BINARY)
        
        padding = 2
        char_padded = cv2.copyMakeBorder(char_thresh, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=255)
        
        target_dicts = []
        if field_type == "Auto": 
            for field in self.templates: target_dicts.append(self.templates[field])
        elif field_type in self.templates: 
            target_dicts = [self.templates[field_type]]
        else: 
            for field in self.templates: target_dicts.append(self.templates[field])

        for tmpl_dict in target_dicts:
            for label, template_list in tmpl_dict.items():
                current_label_max_score = -1.0
                for template in template_list:
                    res = cv2.matchTemplate(char_padded, template, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    score = float(max_val)
                    if score > current_label_max_score: current_label_max_score = score
                if current_label_max_score > best_score:
                    best_score = current_label_max_score
                    best_label = label
        return best_label, best_score, char_thresh
    
    def infer_field_type(self, text):
        if "/" in text: return "Date"
        digit = sum(c.isdigit() for c in text)
        alpha = sum(c.isalpha() for c in text)
        if len(text)>=12 and digit/len(text)>0.8: return "CardNumber"
        elif alpha>0 and alpha>=digit: return "Name"
        elif len(text)<=5 and digit>=3: return "Date"
        return "Unknown"

    @safe_execute(default_return=(0, 0), log_error=True, error_message="锚点定位失败")
    def locate_anchor_offset(self, full_image):
        if self.layout_config.get("strategy") != "anchor_based": return 0, 0 
        
        # ★★★ 关键改进：检查并标准化图像尺寸 ★★★
        if self.standard_image_size is not None:
            current_h, current_w = full_image.shape[:2]
            standard_w, standard_h = self.standard_image_size
            
            if (current_w, current_h) != (standard_w, standard_h):
                # Resize到标准尺寸
                full_image = cv2.resize(full_image, (standard_w, standard_h), interpolation=cv2.INTER_LINEAR)
            
        train_roi = self.layout_config["anchor_rect"] 
        train_x, train_y, train_w, train_h = train_roi
        
        search_rect = self.layout_config.get("anchor_search_area", train_roi)
        sx, sy, sw, sh = search_rect
        
        h_img, w_img = full_image.shape[:2]
        
        sx = max(0, sx); sy = max(0, sy)
        ex = min(w_img, sx + sw); ey = min(h_img, sy + sh)
        
        roi = full_image[sy:ey, sx:ex]
        if roi.size == 0: 
            print("Search area empty!")
            return 0, 0
        
        if len(roi.shape) == 3: gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        else: gray = roi
            
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 4))
        eroded = cv2.erode(binary, kernel, iterations=1)
        cnts, _ = cv2.findContours(eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        valid_blobs = []
        for c in cnts:
            bx, by, bw, bh = cv2.boundingRect(c)
            if bh < 8: continue 
            if bw * bh < 25: continue
            ratio = bw / float(bh)
            if ratio > 2.5: continue 
            valid_blobs.append((bx, by, bw, bh))
            
        if not valid_blobs:
            print("Anchor not found in the designated search area.")
            return 0, 0
            
        valid_blobs.sort(key=lambda b: b[0])
        ink_x, ink_y, ink_w, ink_h = valid_blobs[0]
        
        current_abs_x = sx + ink_x
        current_abs_y = sy + ink_y
        
        offset_x = current_abs_x - train_x
        offset_y = current_abs_y - train_y
        
        print(f"定位: 搜索范围({sx},{sy}) -> 找到墨迹({current_abs_x},{current_abs_y}) | 偏移: ({offset_x}, {offset_y})")
        return offset_x, offset_y

class OCRApp:
    def __init__(self, root):
        self.root = root
        self.root.title("银行卡色带OCR识别系统")
        self.root.geometry("1400x900")
        
        self.solutions_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "solutions")
        self.recognizer = BankCardRecognizer()
        
        self.image_path = None
        self.original_image = None
        self.working_image = None  # ★★★ 新增：标准化后的工作图像 ★★★
        self.tk_image = None
        self.zoom_scale = 1.0
        
        self.roi_start = None
        self.roi_end = None
        
        self.batch_tasks = []
        self.last_total_time = 0.0 
        
        self.ribbon_id = f"RB-{int(time.time())}"
        self.all_results = [] 
        
        self.corrected_tasks_visual = []
        
        # 轮播相关变量
        self.slideshow_files = []
        self.slideshow_index = 0
        self.is_slideshow_running = False

        self._setup_ui()
        self._load_solutions()

    def _setup_ui(self):
        control_frame = tk.Frame(self.root, bd=1, relief=tk.RAISED, bg="#f0f0f0")
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        tk.Label(control_frame, text="1. 方案:", bg="#f0f0f0").pack(side=tk.LEFT, padx=5)
        self.cmb_solutions = ttk.Combobox(control_frame, state="readonly", width=18)
        self.cmb_solutions.pack(side=tk.LEFT, padx=5)
        self.cmb_solutions.bind("<<ComboboxSelected>>", self.on_solution_change)
        
        tk.Button(control_frame, text="2. 打开图片", command=self.load_image, bg="#e1f5fe").pack(side=tk.LEFT, padx=10)
        
        tk.Label(control_frame, text="3. 字段类型:", bg="#f0f0f0").pack(side=tk.LEFT, padx=10)
        self.var_field_type = tk.StringVar(value="Auto")
        self.cmb_type = ttk.Combobox(control_frame, textvariable=self.var_field_type, state="readonly", width=15)
        self.cmb_type['values'] = ("Auto",) 
        self.cmb_type.pack(side=tk.LEFT, padx=5)
        
        self.btn_add_roi = tk.Button(control_frame, text="4. 添加区域", command=self.add_roi_task, state=tk.DISABLED, bg="#fff9c4", font=("bold", 10))
        self.btn_add_roi.pack(side=tk.LEFT, padx=10)
        
        self.btn_batch_run = tk.Button(control_frame, text="5. 批量识别(0)", command=self.run_batch_recognition, state=tk.DISABLED, bg="#c8e6c9", font=("bold", 10))
        self.btn_batch_run.pack(side=tk.LEFT, padx=10)
        
        self.btn_auto_layout = tk.Button(control_frame, text="6. 全卡自动识别", command=self.run_auto_recognize, state=tk.DISABLED, bg="#b3e5fc", font=("bold", 10))
        self.btn_auto_layout.pack(side=tk.LEFT, padx=10)
        
        # [修改] 轮播按钮
        self.btn_slideshow = tk.Button(control_frame, text="▶ 轮播测试", command=self.start_slideshow, bg="#e0f7fa", font=("bold", 10))
        self.btn_slideshow.pack(side=tk.LEFT, padx=10)
        
        tk.Button(control_frame, text="清空任务", command=self.clear_tasks, bg="#ffecb3").pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="清除结果", command=self.clear_results, bg="#ffcdd2").pack(side=tk.LEFT, padx=5)
        
        tk.Label(control_frame, text="( Ctrl+滚轮缩放 | 中键拖拽 )", fg="#666", bg="#f0f0f0").pack(side=tk.LEFT, padx=10)

        main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)
        
        self.canvas_frame = tk.Frame(main_pane, bg="#333")
        main_pane.add(self.canvas_frame, minsize=800)
        
        self.v_bar = tk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL)
        self.h_bar = tk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL)
        self.canvas = tk.Canvas(self.canvas_frame, bg="#333", cursor="cross", xscrollcommand=self.h_bar.set, yscrollcommand=self.v_bar.set)
        
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
        
        self.result_frame = tk.Frame(main_pane, bg="white", padx=10, pady=10)
        main_pane.add(self.result_frame, minsize=450)
        tk.Label(self.result_frame, text="详细排查信息 (已开启自动保存图片)", font=("bold", 14), bg="white").pack(anchor="w", pady=10)
        
        self.info_text = tk.Text(self.result_frame, height=20, font=("Consolas", 10), bg="#f8f9fa", relief=tk.FLAT)
        self.info_text.pack(fill=tk.X, pady=5)
        self.json_text = tk.Text(self.result_frame, height=10, bg="#e8eaf6", fg="#333", font=("Consolas", 9))
        self.json_text.pack(fill=tk.BOTH, expand=True, pady=5)

    def _load_solutions(self):
        if not os.path.exists(self.solutions_root):
            try: os.makedirs(self.solutions_root)
            except: return
        solutions = [d for d in os.listdir(self.solutions_root) if os.path.isdir(os.path.join(self.solutions_root, d))]
        self.cmb_solutions['values'] = solutions
        if solutions:
            self.cmb_solutions.current(0)
            self.on_solution_change(None)

    def on_solution_change(self, event):
        sol_name = self.cmb_solutions.get()
        if not sol_name: return
        path = os.path.join(self.solutions_root, sol_name)
        count = self.recognizer.load_templates(path)
        new_values = ["Auto"] + sorted(self.recognizer.loaded_fields)
        self.cmb_type['values'] = new_values
        self.cmb_type.current(0)
        
        strategy = self.recognizer.layout_config.get("strategy", "absolute")
        msg = "含锚点校正" if strategy == "anchor_based" else "绝对坐标"
        print(f"Loaded {count} templates. Fields: {self.recognizer.loaded_fields}. [{msg}]")

    def _get_fit_scale(self):
        if self.original_image is None: return 1.0
        h, w = self.original_image.shape[:2]
        canvas_w = self.canvas.winfo_width() or 800
        canvas_h = self.canvas.winfo_height() or 600
        return min(canvas_w/w, canvas_h/h, 1.0)

    @safe_execute(default_return=None, log_error=True, error_message="图像加载失败")
    def load_image(self, file_path=None):
        if not file_path:
            file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.png *.bmp")])
        if not file_path: return
        
        self.image_path = file_path
        self.original_image = self.recognizer.cv2_imread_chinese(file_path, cv2.IMREAD_COLOR)
        if self.original_image is not None:
            self.all_results = [] 
            self.batch_tasks = []
            self.corrected_tasks_visual = []
            self.last_total_time = 0.0
            self.zoom_scale = self._get_fit_scale()
            self._redraw_canvas() 
            self.roi_start = None; self.roi_end = None
            self.btn_add_roi.config(state=tk.DISABLED)
            self.btn_batch_run.config(state=tk.DISABLED, text="5. 批量识别(0)")
            self.btn_auto_layout.config(state=tk.NORMAL)
            
            # 如果不是轮播模式，就更新标题
            if not self.is_slideshow_running:
                 self.root.title(f"银行卡色带OCR识别系统 - {os.path.basename(file_path)}")

    # [核心修改] 轮播功能：选择文件夹并启动
    def start_slideshow(self):
        # 1. 选择文件夹
        folder_path = filedialog.askdirectory()
        if not folder_path: return
        
        # 2. 扫描文件夹下的图片
        valid_extensions = {'.jpg', '.jpeg', '.png', '.bmp'}
        self.slideshow_files = []
        
        try:
            for filename in os.listdir(folder_path):
                ext = os.path.splitext(filename)[1].lower()
                if ext in valid_extensions:
                    self.slideshow_files.append(os.path.join(folder_path, filename))
        except Exception as e:
            messagebox.showerror("错误", f"读取文件夹失败: {e}")
            return

        if not self.slideshow_files:
            messagebox.showinfo("提示", "选定的文件夹内没有图片文件。")
            return

        # 排序，保证播放顺序
        self.slideshow_files.sort()

        self.slideshow_index = 0
        self.is_slideshow_running = True
        self.btn_slideshow.config(state=tk.DISABLED, text="轮播中...")
        
        # 启动轮播
        self._process_next_slide()

    def _process_next_slide(self):
        if not self.is_slideshow_running or self.slideshow_index >= len(self.slideshow_files):
            self.is_slideshow_running = False
            self.btn_slideshow.config(state=tk.NORMAL, text="▶ 轮播测试")
            if self.slideshow_index >= len(self.slideshow_files):
                messagebox.showinfo("完成", "轮播测试已完成")
            return
            
        file_path = self.slideshow_files[self.slideshow_index]
        self.load_image(file_path)
        
        # 自动执行识别
        self.root.title(f"轮播 [{self.slideshow_index+1}/{len(self.slideshow_files)}] - {os.path.basename(file_path)}")
        self.run_auto_recognize()
        
        self.slideshow_index += 1
        
        # 1秒后处理下一张
        self.root.after(1000, self._process_next_slide)

    def on_zoom(self, event):
        if self.original_image is None: return
        factor = 1.1 if event.delta > 0 else 0.9
        new_scale = self.zoom_scale * factor
        if 0.1 < new_scale < 10.0:
            self.zoom_scale = new_scale
            self._redraw_canvas()

    def on_pan_start(self, event): self.canvas.scan_mark(event.x, event.y)
    def on_pan_drag(self, event): self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _redraw_canvas(self):
        if self.original_image is None: return
        h, w = self.original_image.shape[:2]
        new_w = int(w * self.zoom_scale)
        new_h = int(h * self.zoom_scale)
        
        img_resized = cv2.resize(self.original_image, (new_w, new_h))
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        self.tk_image = ImageTk.PhotoImage(Image.fromarray(img_rgb))
        
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image)
        self.canvas.config(scrollregion=(0, 0, new_w, new_h))
        
        if self.corrected_tasks_visual:
            for coords in self.corrected_tasks_visual:
                x1, y1, x2, y2 = coords
                self.canvas.create_rectangle(x1, y1, x2, y2, outline="yellow", width=1, dash=(3,3))

        for task in self.batch_tasks:
            x1, y1, x2, y2 = task['coords']
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="cyan", width=2, tags="batch_roi")
            self.canvas.create_text(x1, y1-15, text=task['type'], anchor="sw", fill="cyan", font=("Arial", 10, "bold"), tags="batch_roi")

        for res in self.all_results:
            rx, ry, rw, rh = res['box']
            sx, sy = rx * self.zoom_scale, ry * self.zoom_scale
            sw, sh = rw * self.zoom_scale, rh * self.zoom_scale
            self.canvas.create_rectangle(sx, sy, sx+sw, sy+sh, outline="#00ff00", width=2)
            self.canvas.create_text(sx, sy-15, text=f"{res['result']}", anchor="sw", fill="#00ff00", font=("Arial", 11, "bold"))
            
            for char_detail in res['char_details']:
                c_score = char_detail['score']
                cx, cy, cw, ch = char_detail['box']
                scx, scy = cx * self.zoom_scale, cy * self.zoom_scale
                scw, sch = cw * self.zoom_scale, ch * self.zoom_scale
                char_color = "red" if c_score < 0.8 else "cyan"
                self.canvas.create_rectangle(scx, scy, scx+scw, scy+sch, outline=char_color, width=1, dash=(2,2))

    def clear_tasks(self):
        self.batch_tasks = []
        self.corrected_tasks_visual = []
        self.btn_batch_run.config(state=tk.DISABLED, text="5. 批量识别(0)")
        self._redraw_canvas()

    def clear_results(self):
        self.all_results = []
        self.last_total_time = 0.0
        self._redraw_canvas()
        self.info_text.delete(1.0, tk.END)
        self.json_text.delete(1.0, tk.END)

    def on_mouse_down(self, event):
        self.roi_start = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        self.canvas.delete("temp_roi") 

    def on_mouse_drag(self, event):
        if not self.roi_start: return
        self.canvas.delete("temp_roi")
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        self.canvas.create_rectangle(self.roi_start[0], self.roi_start[1], cur_x, cur_y, outline="red", width=2, tags="temp_roi", dash=(4, 4))

    def on_mouse_up(self, event):
        self.roi_end = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if self.roi_start and self.roi_end: 
            self.btn_add_roi.config(state=tk.NORMAL)

    def sort_multiline_chars(self, chars_data):
        if not chars_data: return []
        chars_data.sort(key=lambda b: b[1])
        lines = []
        current_line = [chars_data[0]]
        ref_h = chars_data[0][3]
        for i in range(1, len(chars_data)):
            curr = chars_data[i]
            prev = current_line[-1]
            if abs(curr[1] - prev[1]) < ref_h * 0.6: current_line.append(curr)
            else:
                current_line.sort(key=lambda b: b[0])
                lines.append(current_line)
                current_line = [curr]
                ref_h = curr[3]
        current_line.sort(key=lambda b: b[0])
        lines.append(current_line)
        return [item for sublist in lines for item in sublist]

    def add_roi_task(self):
        if not self.roi_start or not self.roi_end: return
        task = {
            'coords': (self.roi_start[0], self.roi_start[1], self.roi_end[0], self.roi_end[1]),
            'type': self.var_field_type.get()
        }
        self.batch_tasks.append(task)
        self._redraw_canvas()
        self.canvas.delete("temp_roi")
        self.roi_start = None
        self.roi_end = None
        self.btn_add_roi.config(state=tk.DISABLED)
        self.btn_batch_run.config(state=tk.NORMAL, text=f"5. 批量识别({len(self.batch_tasks)})")

    @safe_execute(default_return=None, log_error=True, error_message="自动识别失败")
    def run_auto_recognize(self):
        if not self.original_image is not None: 
            if not self.is_slideshow_running: messagebox.showwarning("提示", "请先打开一张图片")
            return
        
        # ★★★ 关键改进：识别前标准化图像尺寸 ★★★
        self.working_image = self.original_image.copy()
        
        if self.recognizer.standard_image_size is not None:
            current_h, current_w = self.working_image.shape[:2]
            standard_w, standard_h = self.recognizer.standard_image_size
            
            if (current_w, current_h) != (standard_w, standard_h):
                self.working_image = cv2.resize(self.working_image, (standard_w, standard_h), interpolation=cv2.INTER_LINEAR)
        
        t0 = time.perf_counter()
        off_x, off_y = self.recognizer.locate_anchor_offset(self.working_image)
        t_detect = (time.perf_counter() - t0) * 1000
        
        self.batch_tasks = []
        self.corrected_tasks_visual = [] 
        
        layout = self.recognizer.layout_config
        
        if layout.get("strategy") == "anchor_based":
            for field, train_roi in layout["fields"].items():
                train_x, train_y, w, h = train_roi
                current_x = train_x + off_x
                current_y = train_y + off_y
                orig_x1 = train_x * self.zoom_scale
                orig_y1 = train_y * self.zoom_scale
                orig_x2 = (train_x + w) * self.zoom_scale
                orig_y2 = (train_y + h) * self.zoom_scale
                self.corrected_tasks_visual.append((orig_x1, orig_y1, orig_x2, orig_y2))
                s = self.zoom_scale
                self.batch_tasks.append({
                    'coords': (current_x*s, current_y*s, (current_x+w)*s, (current_y+h)*s),
                    'type': field
                })
        else:
            for field, config in self.recognizer.layout_config.items():
                if field in ["anchor_strategy", "strategy", "fields", "anchor_search_area", "anchor_rect"]: continue 
                if isinstance(config, dict) and "roi" in config: coords = config["roi"]
                elif isinstance(config, list): coords = config
                else: continue
                x, y, w, h = coords
                s = self.zoom_scale
                self.batch_tasks.append({
                    'coords': (x*s, y*s, (x+w)*s, (y+h)*s),
                    'type': field
                })

        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, f"=== 自动定位完成 ===\n")
        self.info_text.insert(tk.END, f"模式: {layout.get('strategy', 'absolute')}\n")
        self.info_text.insert(tk.END, f"偏移量: X={off_x}, Y={off_y}\n")
        self.info_text.insert(tk.END, f"定位耗时: {t_detect:.2f} ms\n")
        self.info_text.insert(tk.END, f"----------------------\n")
        
        self.btn_batch_run.config(state=tk.NORMAL, text=f"5. 批量识别({len(self.batch_tasks)})")
        self.run_batch_recognition()

    def _process_single_roi(self, ui_coords, field_type, debug_folder):
        x1, y1, x2, y2 = ui_coords
        real_x1 = int(min(x1, x2) / self.zoom_scale)
        real_y1 = int(min(y1, y2) / self.zoom_scale)
        real_x2 = int(max(x1, x2) / self.zoom_scale)
        real_y2 = int(max(y1, y2) / self.zoom_scale)
        
        # ★★★ 关键改进：使用标准化后的工作图像 ★★★
        # 如果有working_image（标准化后的），使用它；否则使用original_image
        source_image = getattr(self, 'working_image', self.original_image)
        
        h, w = source_image.shape[:2]
        real_x1 = max(0, real_x1); real_y1 = max(0, real_y1)
        real_x2 = min(w, real_x2); real_y2 = min(h, real_y2)
        
        roi = source_image[real_y1:real_y2, real_x1:real_x2]
        if roi.size == 0: return None, None

        t_start = time.perf_counter()
        
        padding = 10
        roi_padded = cv2.copyMakeBorder(roi, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=(0,0,0))
        binary_detect, binary_template = self.recognizer.preprocess_image(roi_padded)
        cnts, _ = cv2.findContours(binary_detect, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        heights = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if h < 8 or w < 3: continue 
            if w / h > 4.0: continue
            candidates.append((x, y, w, h))
            heights.append(h)
            
        if not candidates: return None, None

        if len(candidates) > 2:
            median_h = np.median(heights)
            valid_chars = []
            for (x, y, w, h) in candidates:
                if h < median_h * 0.5: continue
                if h > median_h * 1.8: continue
                valid_chars.append((x, y, w, h))
        else:
            valid_chars = candidates
        
        valid_chars = self.sort_multiline_chars(valid_chars)
        
        result_str = ""
        total_conf = 0
        char_details = []
        debug_imgs = []
        
        for idx, (x, y, w, h) in enumerate(valid_chars):
            char_roi = binary_template[y:y+h, x:x+w]
            label, score, processed_img = self.recognizer.match_char(char_roi, field_type=field_type, idx=idx)
            result_str += label
            total_conf += score
            
            global_char_x = real_x1 + x - padding
            global_char_y = real_y1 + y - padding
            char_details.append({
                "char": label,
                "score": score,
                "box": (global_char_x, global_char_y, w, h)
            })
            
            safe_label = "slash" if label == "/" else label
            fname = f"{field_type}_{idx}_{safe_label}_score{score:.2f}.png"
            debug_imgs.append((fname, processed_img))
            
        t_end = time.perf_counter()
        field_time_ms = (t_end - t_start) * 1000

        avg_conf = total_conf / len(valid_chars) if valid_chars else 0
        final_type = field_type
        if field_type == "Auto": final_type = self.recognizer.infer_field_type(result_str)
        
        is_abnormal = False
        notes = []
        if avg_conf < 0.85: is_abnormal = True; notes.append("整体置信度低")
        if final_type == "Card Number" and not result_str.isdigit(): is_abnormal = True; notes.append("含非数字")
        
        record = {
            "result": result_str,
            "field_type": final_type,
            "confidence": float(round(avg_conf, 4)),
            "time_ms": float(round(field_time_ms, 2)),
            "box": (real_x1, real_y1, real_x2 - real_x1, real_y2 - real_y1), 
            "char_details": char_details,
            "is_abnormal": is_abnormal,
            "notes": notes
        }
        
        return record, debug_imgs

    @safe_execute(default_return=None, log_error=True, error_message="批量识别失败")
    def run_batch_recognition(self):
        if not self.batch_tasks: return
        
        debug_root = "debug_output"
        if not os.path.exists(debug_root): os.makedirs(debug_root)
        timestamp_folder = time.strftime("%H%M%S")
        current_debug_dir = os.path.join(debug_root, timestamp_folder)
        os.makedirs(current_debug_dir, exist_ok=True)
        
        self.all_results = []
        all_debug_images = []
        
        total_algo_start = time.perf_counter()
        
        for task in self.batch_tasks:
            record, debug_imgs = self._process_single_roi(task['coords'], task['type'], current_debug_dir)
            if record:
                self.all_results.append(record)
                if debug_imgs: all_debug_images.extend(debug_imgs)
        
        total_algo_end = time.perf_counter()
        self.last_total_time = (total_algo_end - total_algo_start) * 1000
        
        for fname, img in all_debug_images:
            cv2.imencode(".png", img)[1].tofile(os.path.join(current_debug_dir, fname))
            
        self.batch_tasks = []
        self.btn_batch_run.config(state=tk.DISABLED, text="5. 批量识别(0)")
        self._update_display()
        print(f"Batch processed. Debug images in: {current_debug_dir}")

    def _update_display(self):
        self._redraw_canvas()
        # 注意：这里不再清空 text，因为 run_auto_recognize 已经写入了定位信息
        
        for i, res in enumerate(self.all_results):
            status = "异常" if res['is_abnormal'] else "正常"
            char_scores_str = ", ".join([f"{c['char']}:{c['score']:.2f}" for c in res['char_details']])
            
            self.info_text.insert(tk.END, f"[{i+1}] {res['field_type']}: {res['result']}\n")
            self.info_text.insert(tk.END, f"    单字段耗时: {res['time_ms']} ms\n")
            self.info_text.insert(tk.END, f"    平均置信度: {res['confidence']}\n")
            self.info_text.insert(tk.END, f"    单字得分: {char_scores_str}\n")
            self.info_text.insert(tk.END, f"    状态: {status} {res['notes']}\n\n")
        
        if self.last_total_time > 0:
            self.info_text.insert(tk.END, "-"*40 + "\n")
            self.info_text.insert(tk.END, f"★ 整图识别总耗时(纯算法): {self.last_total_time:.2f} ms\n")
            self.info_text.insert(tk.END, "-"*40 + "\n")
            
        full_json = {
            "ribbon_id": self.ribbon_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_time_ms": float(round(self.last_total_time, 2)),
            "items": self.all_results
        }
        self.json_text.delete(1.0, tk.END)
        self.json_text.insert(tk.END, json.dumps(full_json, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    root = tk.Tk()
    app = OCRApp(root)
    root.mainloop() 