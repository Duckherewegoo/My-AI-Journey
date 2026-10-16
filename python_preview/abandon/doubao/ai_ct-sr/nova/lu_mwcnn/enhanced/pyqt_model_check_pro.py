import sys
import os
import torch
from pathlib import Path
from PyQt.QtWidgets import 
from PyQt.QtCore import 
from PyQt.QtGui import 

 ==============================================
 全局配置：文泉驿正黑字体 + 【护眼浅黑主题】背景不深+清晰
 ==============================================
APP_FONT = QFont("WenquanYi Zen Hei", )


LIGHT_DARK_STYLE = """
/ 主窗口：中等灰色背景 + 纯白文字 /
QMainWindow { background-color: ; color: FFFFFF; }
QToolBar { background-color: AAA; border: none; }

/ 文件列表：清晰背景 + 纯白文字 /
QListWidget { background-color: AAA; color: FFFFFF; border: px solid ; }
QListWidget::item:selected { background-color: FF; color: FFFFFF; }

/ 标签页面板 /
QTabWidget::pane { background-color: AAA; border: px solid ; }
QTabBar::tab { background-color: ; color: FFFFFF; padding: px px; }
QTabBar::tab:selected { background-color: FF; color: FFFFFF; }

/ 表格/数据展示 /
QTableWidget { background-color: AAA; color: FFFFFF; gridline-color: ; }
QHeaderView { background-color: ; color: FFFFFF; }

/ 按钮 /
QPushButton { background-color: FF; color: FFFFFF; padding: px px; border: none; border-radius: px; }
QPushButton:hover { background-color: AAFF; }

/ 文字/标签 强制纯白 /
QLabel { color: FFFFFF; }
QTextEdit { background-color: AAA; color: FFFFFF; border: px solid ; }

/ 修复弹窗！浅灰背景+黑字，绝对清晰 /
QMessageBox {
    background-color: FFF;
    color: ;
}
QMessageBox QLabel {
    color: ;
    font-size: pt;
}
QMessageBox QPushButton {
    background-color: FF;
    color: white;
    padding: px px;
}
"""




class PthViewerPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(' PTH权重全能查看器 [适配你的训练指标]')
        self.setGeometry(, , , )
        self.setFont(APP_FONT)
        self.setStyleSheet(LIGHT_DARK_STYLE)

        self.weight_files = []
        self.current_ckpt = None
        self.current_model_sd = None
        self.init_ui()

    def init_ui(self):
         顶部工具栏
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        scan_btn = QAction(' 选择根文件夹（递归扫描子文件夹）', self)
        scan_btn.triggered.connect(self.scan_all_pth)
        toolbar.addAction(scan_btn)

         主布局
        main_splitter = QSplitter(Qt.Horizontal)

         左侧：文件列表
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel(' 权重文件列表'))
        self.file_list = QListWidget()
        self.file_list.setFont(APP_FONT)
        self.file_list.itemClicked.connect(self.load_weight_file)
        left_layout.addWidget(self.file_list)
        main_splitter.addWidget(left_panel)
        main_splitter.setSizes([, ])

         右侧：大标签页（新增【训练指标】专属页）
        self.tab_widget = QTabWidget()
        self.tab_widget.setFont(APP_FONT)

        self.init_overview()     模型总览
        self.init_layers_table()   层结构
        self.init_metrics()       新增：你的训练指标面板
        self.init_raw_tensor()   原始数据
        self.init_full_ckpt()    完整信息

        main_splitter.addWidget(self.tab_widget)
        self.setCentralWidget(main_splitter)

     . 模型总览
    def init_overview(self):
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing()
        self.info_file = QLabel()
        self.info_layers = QLabel()
        self.info_params = QLabel()
        self.info_params_m = QLabel()
        layout.addRow(' 文件名称：', self.info_file)
        layout.addRow(' 模型有效层：', self.info_layers)
        layout.addRow(' 总参数量：', self.info_params)
        layout.addRow(' 参数量(百万)：', self.info_params_m)
        self.tab_widget.addTab(widget, ' 模型总览')

     . 层结构表格
    def init_layers_table(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel(' 模型层结构（名称/形状/参数/类型）'))
        self.layer_table = QTableWidget()
        self.layer_table.setColumnCount()
        self.layer_table.setHorizontalHeaderLabels(['层名称', '张量形状', '参数量', '数据类型'])
        self.layer_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.layer_table)
        self.tab_widget.addTab(widget, ' 层结构')

     ==============================================
      . 【专属适配】你的训练指标面板（Loss/PSNR/SSIM/LPIPS）
     ==============================================
    def init_metrics(self):
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing()

         基础训练信息
        self.m_epoch = QLabel()
        self.m_lr = QLabel()
         最佳指标
        self.m_best_loss = QLabel()
        self.m_best_psnr = QLabel()
        self.m_best_ssim = QLabel()
        self.m_best_lpips = QLabel()
         当前轮指标
        self.m_cur_loss = QLabel()
        self.m_cur_psnr = QLabel()
        self.m_cur_ssim = QLabel()
        self.m_cur_lpips = QLabel()

         布局
        layout.addRow(' 训练轮次 Epoch：', self.m_epoch)
        layout.addRow(' 当前 Loss：', self.m_cur_loss)
        layout.addRow(' 当前 PSNR：', self.m_cur_psnr)
        layout.addRow(' 当前 SSIM：', self.m_cur_ssim)
        layout.addRow(' 当前 LPIPS：', self.m_cur_lpips)
        layout.addRow(' 最佳 Loss：', self.m_best_loss)
        layout.addRow(' 最佳 PSNR：', self.m_best_psnr)
        layout.addRow(' 最佳 SSIM：', self.m_best_ssim)
        layout.addRow(' 最佳 LPIPS：', self.m_best_lpips)

        self.tab_widget.addTab(widget, ' 训练指标')

     . 原始张量数据
    def init_raw_tensor(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel(' 原始张量数据（前个数值）'))
        self.raw_text = QTextEdit()
        self.raw_text.setFont(QFont("WenquanYi Zen Hei", ))
        self.raw_text.setReadOnly(True)
        layout.addWidget(self.raw_text)
        self.tab_widget.addTab(widget, ' 原始数据')

     . 完整Checkpoint信息
    def init_full_ckpt(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel(' 完整文件所有原始信息'))
        self.ckpt_text = QTextEdit()
        self.ckpt_text.setReadOnly(True)
        layout.addWidget(self.ckpt_text)
        self.tab_widget.addTab(widget, ' 完整信息')

     递归扫描所有子文件夹 .pth/.pt
    def scan_all_pth(self):
        root_dir = QFileDialog.getExistingDirectory(self, '选择权重根目录')
        if not root_dir:
            return
        self.file_list.clear()
        self.weight_files.clear()

        for path, _, files in os.walk(root_dir):
            for file in files:
                if file.endswith(('.pth', '.pt')):
                    full_path = os.path.join(path, file)
                    self.weight_files.append(full_path)
                    show_path = full_path.replace(root_dir, '').lstrip('/\\')
                    self.file_list.addItem(show_path)

        QMessageBox.information(self, '扫描完成', f' 共找到 {len(self.weight_files)} 个权重文件')

     ==============================================
      核心：完美适配你的权重格式（model_state_dict）
     ==============================================
    def load_weight_file(self, item):
        idx = self.file_list.currentRow()
        file_path = self.weight_files[idx]
        self.clear_all_info()

        try:
             CPU安全加载
            ckpt = torch.load(file_path, map_location='cpu', weights_only=False)
            self.current_ckpt = ckpt

             强制读取你的模型权重键：model_state_dict
            if isinstance(ckpt, dict):
                if 'model_state_dict' in ckpt:
                    self.current_model_sd = ckpt['model_state_dict']
                elif 'model' in ckpt:
                    self.current_model_sd = ckpt['model']
                elif 'state_dict' in ckpt:
                    self.current_model_sd = ckpt['state_dict']
                else:
                    self.current_model_sd = ckpt
            else:
                self.current_model_sd = {}

             加载所有展示
            self.show_overview(file_path)
            self.show_layers()
            self.show_metrics()   展示训练指标
            self.show_raw_data()
            self.show_full_ckpt()

        except Exception as e:
            QMessageBox.critical(self, '解析失败', f'错误：{str(e)}')

     展示模型总览
    def show_overview(self, path):
        valid_layers = [k for k, v in self.current_model_sd.items() if torch.is_tensor(v)]
        total_params = sum(v.numel() for v in self.current_model_sd.values() if torch.is_tensor(v))

        self.info_file.setText(Path(path).name)
        self.info_layers.setText(str(len(valid_layers)))
        self.info_params.setText(f'{total_params:,}')
        self.info_params_m.setText(f'{total_params / e:.f} M')

     展示层结构
    def show_layers(self):
        layers = [(n, t) for n, t in self.current_model_sd.items() if torch.is_tensor(t)]
        self.layer_table.setRowCount(len(layers))
        for i, (name, tensor) in enumerate(layers):
            self.layer_table.setItem(i, , QTableWidgetItem(name))
            self.layer_table.setItem(i, , QTableWidgetItem(str(list(tensor.shape))))
            self.layer_table.setItem(i, , QTableWidgetItem(f'{tensor.numel():,}'))
            self.layer_table.setItem(i, , QTableWidgetItem(str(tensor.dtype)))

     ==============================================
      展示你的所有训练指标（完美匹配你的保存代码）
     ==============================================
     ==============================================
  修复版：%匹配你的权重指标读取逻辑
 ==============================================
    def show_metrics(self):
        ckpt = self.current_ckpt
        current = ckpt.get('current_metrics', {})   最佳模型里的当前指标
        ckpt_keys = ckpt.keys()

         ====================== 基础轮次 ======================
        self.m_epoch.setText(str(ckpt.get('epoch', '未记录')))

         ====================== 当前指标（兼容两种保存格式） ======================
         当前Loss：优先取根目录loss，没有取current_metrics里的
        cur_loss = ckpt.get('loss') if 'loss' in ckpt else current.get('loss')
        self.m_cur_loss.setText(f"{cur_loss:.f}" if isinstance(cur_loss, float) else '—')
    
         当前PSNR/SSIM/LPIPS：优先取current_metrics，没有则为空
        cur_psnr = current.get('psnr')
        cur_ssim = current.get('ssim')
        cur_lpips = current.get('lpips')
        self.m_cur_psnr.setText(f"{cur_psnr:.f} dB" if isinstance(cur_psnr, float) else '—')
        self.m_cur_ssim.setText(f"{cur_ssim:.f}" if isinstance(cur_ssim, float) else '—')
        self.m_cur_lpips.setText(f"{cur_lpips:.f}" if isinstance(cur_lpips, float) else '—')

         ====================== 最佳指标（严格按你的加载代码读取） ======================
        best_loss = ckpt.get('best_loss', float('inf'))
        best_psnr = ckpt.get('best_psnr', .)
        best_ssim = ckpt.get('best_ssim', .)
        best_lpips = ckpt.get('best_lpips', float('inf'))
    
         格式化显示，无效值显示—
        self.m_best_loss.setText(f"{best_loss:.f}" if best_loss != float('inf') else '—')
        self.m_best_psnr.setText(f"{best_psnr:.f} dB" if best_psnr >  else '—')
        self.m_best_ssim.setText(f"{best_ssim:.f}" if best_ssim >  else '—')
        self.m_best_lpips.setText(f"{best_lpips:.f}" if best_lpips != float('inf') else '—')

         展示原始张量数据
    def show_raw_data(self):
        text = ""
        layers = [(n, t) for n, t in self.current_model_sd.items() if torch.is_tensor(t)]
        for name, tensor in layers[:]:
            text += f"━━━━━━ {name} ━━━━━━\n"
            text += f"形状：{list(tensor.shape)}\n"
            text += f"数值：{tensor.cpu().detach().numpy().flatten()[:]}\n\n"
        self.raw_text.setText(text)

     展示完整信息
    def show_full_ckpt(self):
        info = []
        for key, value in self.current_ckpt.items():
            if torch.is_tensor(value):
                info.append(f"{key}: 张量 {list(value.shape)}")
            elif isinstance(value, dict):
                info.append(f"{key}: 子字典 (键数: {len(value)})")
            else:
                info.append(f"{key}: {value}")
        self.ckpt_text.setText("\n".join(info))

     清空所有数据
    def clear_all_info(self):
        for label in [self.info_file, self.info_layers, self.info_params, self.info_params_m]:
            label.setText('')
        self.layer_table.setRowCount()
        for label in [self.m_epoch, self.m_cur_loss, self.m_cur_psnr, self.m_cur_ssim, self.m_cur_lpips,
                      self.m_best_loss, self.m_best_psnr, self.m_best_ssim, self.m_best_lpips]:
            label.setText('')
        self.raw_text.clear()
        self.ckpt_text.clear()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setFont(APP_FONT)
    window = PthViewerPro()
    window.show()
    sys.exit(app.exec_())
