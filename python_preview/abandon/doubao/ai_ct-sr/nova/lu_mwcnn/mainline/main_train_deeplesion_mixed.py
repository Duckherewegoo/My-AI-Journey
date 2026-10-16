'''
    LU-MWCNN 训练代码 @ DeepLesion。
    整合多数据集配置 + 修复后的LUMWCNN网络
    模块化重构：降低主函数复杂度，修复参数传递/逻辑硬伤
'''

 准备引入
from base.utils.wavelet import DWT_Haar, IWT_Haar
import os
from tqdm import tqdm
import torch
import torch.nn as nn
import numpy as np
from skimage.metrics import structural_similarity
from PIL import Image
import importlib
from base.utils.metrics import 
from base.utils.meters import AverageMeter
import torch.optim as optim
from torch.optim import lr_scheduler
from torch.utils.data import DataLoader, ConcatDataset
import sys
import os.path as path
import torch.nn.functional as F   补充wavelet_pad需要的F

 路径处理
dirname__ = path.dirname(path.abspath(__file__))
sys.path.append(path.join(dirname__))   current directory first
sys.path.append(path.join(dirname__, '../../baselines'))

 ======================== 配置类定义 ========================


class Config:
     核心数据集（主体）：DeepLesion_Key_slices
    key_train_root = "/datasets/DeepLesion_Key_slices/train/HR/"
    key_val_root = r"../datasets/DeepLesion_Key_slices/val/HR/"
    key_test_root = r"../datasets/DeepLesion_Key_slices/test/HR/"

     补充数据集：DeepLesion/lung（划分后路径）
    lung_train_root = r"../datasets/DeepLesion/deeplesion_category_split/lung/train/"
    lung_val_root = r"../datasets/DeepLesion/deeplesion_category_split/lung/val/"
    lung_test_root = r"../datasets/DeepLesion/deeplesion_category_split/lung/test/"

     补充数据集：LUNA
    luna_train_root = r"../datasets/LUNA/sr_slice_dataset/train/"
    luna_val_root = r"../datasets/LUNA/sr_slice_dataset/val/"
    luna_test_root = r"../datasets/LUNA/sr_slice_dataset/test/"

     补充数据集: COVID（仅训练集，无验证/测试划分）
    covid_train_root = r"../datasets/COVID-CT/COVID-CT-Images/positive"
    covid_val_root = None
    covid_test_root = None

     训练参数
    batch_size = 
    epochs = 
    resume_ckpt = None
    lr = e-
    weight_decay = e-
    patience =    早停耐心值
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

     数据增强参数（适配灰度图）
    max_rotation = 
    max_scale = .
    min_scale = .
    crop_size = 

     保存路径
    save_dir = "./output_deeplesion/deeplesion_multi_train_ckpt"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)


 初始化配置
cfg = Config()
VAL_EVERY = 
NOISE_STD = .   保持原噪声标准差

 创建ckp和val_inference目录
ckp_dir = os.path.join(cfg.save_dir, 'ckp')
val_inf_dir = os.path.join(cfg.save_dir, 'val_inference')
os.makedirs(ckp_dir, exist_ok=True)
os.makedirs(val_inf_dir, exist_ok=True)

 TensorBoard初始化（修复：避免未定义）
try:
    from torch.utils.tensorboard.writer import SummaryWriter
    tb = SummaryWriter(log_dir=os.path.join(cfg.save_dir, "tb_logs"))
except ImportError:
    tb = None
    print("️ 未安装TensorBoard，跳过日志记录")

 ======================== 模型定义 ========================


class Convd(nn.Module):
    """带激活函数+批归一化的卷积模块"""

    def __init__(self, in_ch: int, out_ch: int, kernel_size: int, act: bool = True) -> None:
        super(Convd, self).__init__()
        layers = [
            nn.Convd(in_ch, out_ch, kernel_size=kernel_size,
                      padding=kernel_size // , bias=False),   批归一化不需要bias
            nn.BatchNormd(out_ch),   新增批归一化
        ]
        if act:
            layers.append(nn.ReLU(inplace=True))
        self.layers = nn.Sequential(layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.layers(x)


class LUMWCNN(nn.Module):
    def __init__(self) -> None:
        super(LUMWCNN, self).__init__()

        self.DWT = DWT_Haar()   小波变换
        self.IWT = IWT_Haar()   小波逆变换
        self.pad_info: dict = {}
         左侧卷积块（下采样路径）
        self.l_conv = nn.Sequential([Convd(, , ), Convd(, , )])
        self.l_conv = nn.Sequential(
            [Convd(, , ), Convd(, , )])   =（DWT后通道×）
        self.l_conv = nn.Sequential(
            [Convd(, , ), Convd(, , )])   =

         右侧卷积块（上采样路径）
        self.r_conv = nn.Sequential(
             输出用于IWT（/=）
            [Convd(, , ), Convd(, , )])
        self.r_conv = nn.Sequential(
             输出用于IWT（/=）
            [Convd(, , ), Convd(, , )])
        self.r_conv = nn.Sequential(
            [Convd(, , ), Convd(, , , act=False)])   输出通道与输入x匹配

         上采样模块（总放大倍数x）
        self.upsample = nn.Sequential(
            Convd(, , ),
            Convd(,   , ),   修正：^  目标通道() = 
            nn.PixelShuffle(),   第一次x上采样（通道→，尺寸×）
            Convd(, , ),
            Convd(,   , ),   同上
            nn.PixelShuffle(),   第二次x上采样
            nn.Convd(, , , padding=, bias=False),   最终输出通道，无激活
            nn.Sigmoid()   强制输出值域[,]，避免全黑
        )

        self.validating = False   调试模式标记
        self.pads: list = []   记录填充信息

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        self.print_shape(x, 'Input')

         左侧第一层
        x_l = self.l_conv(x)   ->
        self.print_shape(x_l, 'After l_conv')

         小波变换前填充（确保尺寸为偶数）
        x_l_pad = self.wavelet_pad(x_l, 'l')
        self.print_shape(x_l_pad, 'x_l_pad')

         第一次DWT（通道×）
        _x_l = self.DWT(x_l_pad)
        self.print_shape(_x_l, 'After DWT ')

         左侧第二层
        x_l = self.l_conv(_x_l)   ->
        self.print_shape(x_l, 'After l_conv')

        x_l_pad = self.wavelet_pad(x_l, 'l')
        self.print_shape(x_l_pad, 'x_l_pad')

         第二次DWT
        _x_l = self.DWT(x_l_pad)
        self.print_shape(_x_l, 'After DWT ')

         左侧第三层
        x_l = self.l_conv(_x_l)   ->
        self.print_shape(x_l, 'After l_conv')

         右侧第三层
        _after_r_conv = self.r_conv(x_l)   ->
        self.print_shape(_after_r_conv, 'After r_conv')

         第一次IWT（通道÷）
        lhs = self.IWT(_after_r_conv).to(x.device)   适配输入设备
        self.print_shape(lhs, 'After IWT ')

         移除填充部分
        lhs_shave = self.wavelet_shave(lhs, 'l')
        self.print_shape(lhs_shave, 'lhs_shave')

         残差连接
        x_r = lhs_shave + x_l
        self.print_shape(x_r, 'x_r (residual)')

         右侧第二层
        _after_r_conv = self.r_conv(x_r)   ->
        self.print_shape(_after_r_conv, 'After r_conv')

         第二次IWT
        _x_r = self.IWT(_after_r_conv).to(x.device)
        self.print_shape(_x_r, 'After IWT ')

         残差连接
        x_r = self.wavelet_shave(_x_r, 'l') + x_l
        self.print_shape(x_r, 'x_r (residual)')

         右侧第一层（输出通道与输入匹配）
        x_r = .  self.r_conv(x_r) + x
        self.print_shape(x_r, 'x_r (residual)')

         上采样得到最终结果
        y = self.upsample(x_r)
        y = torch.clamp(y, , )
        self.print_shape(y, 'Output')

        return y

    def print_shape(self, x: torch.Tensor, desc: str) -> None:
        """调试时打印张量形状"""
        if self.validating:
            print(f'[{desc}] Shape: {x.shape}')

    def wavelet_pad(self, x: torch.Tensor, key: str) -> torch.Tensor:
        """小波变换前填充，按key记录填充信息"""
        should_pad_h = x.shape[-] %  != 
        should_pad_w = x.shape[-] %  != 
        padding = ( if should_pad_w else , ,
                    if should_pad_h else , )
        self.pad_info[key] = [should_pad_w, should_pad_h]
        return F.pad(x, padding, 'constant', )

    def wavelet_shave(self, x: torch.Tensor, key: str) -> torch.Tensor:
        """小波逆变换后移除填充，按key读取填充信息"""
        if key not in self.pad_info:
            return x
        should_shave_w, should_shave_h = self.pad_info.pop(key)
        if should_shave_w:
            x = x[:, :, :, :-]   修正：裁最后一列
        if should_shave_h:
            x = x[:, :, :-, :]   修正：裁最后一行
        return x

 ======================== 工具函数 ========================


def custom_collate_fn(batch: list) -> tuple[torch.Tensor, torch.Tensor, list[str]]:
    """
    自定义数据拼接函数，处理None类型的filename
    batch结构：[(y_lr, y_hr, filename), ...]
    """
    lr_list: list[torch.Tensor] = []
    hr_list: list[torch.Tensor] = []
    filename_list: list[str] = []

    for lr, hr, filename in batch:
        lr_list.append(lr)
        hr_list.append(hr)
        filename_list.append(filename if filename is not None else "")

    lr_tensor = torch.stack(lr_list)
    hr_tensor = torch.stack(hr_list)

    return lr_tensor, hr_tensor, filename_list


def step_scheduler(
    scheduler: lr_scheduler._LRScheduler | lr_scheduler.ReduceLROnPlateau,
    optimizer: optim.Optimizer,
    epoch: int,
    metric: float | None = None,
    train_loss: float | None = None
) -> float:
    """
    适配ReduceLROnPlateau的安全调度器函数
    Args:
        scheduler: 学习率调度器
        optimizer: 优化器
        epoch: 当前epoch（代码内开始）
        metric: 验证集指标（如PSNR，优先用）
        train_loss: 训练集损失（metric=None时兜底）
    Returns:
        new_lr: 调整后的学习率
    """
    old_lr = optimizer.param_groups[]['lr']

    if isinstance(scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau):
        if metric is not None:
            scheduler.step(metric)
        elif train_loss is not None:
            adjust_metric = -train_loss if scheduler.mode == 'max' else train_loss
            scheduler.step(adjust_metric)
            print(
                f"️  Epoch {epoch+} | 无验证指标，使用训练损失({train_loss:.f})替代调整学习率")
        else:
            print(f"️  Epoch {epoch+} | 无任何指标，暂不调整学习率")
            return old_lr
    else:
        scheduler.step()

    new_lr = optimizer.param_groups[]['lr']
    if new_lr != old_lr:
        print(
            f" Epoch {epoch+} | CT影像训练 - 学习率调整：{old_lr:.f} → {new_lr:.f}")
    return new_lr


def safe_extract_scalar(val: torch.Tensor | float | int) -> float:
    """安全提取标量值，兼容Tensor/float/int"""
    if isinstance(val, torch.Tensor):
        return val.item()
    elif isinstance(val, (float, int)):
        return float(val)
    else:
        return .

 ======================== 初始化相关函数 ========================


def init_model_optimizer_scheduler(cfg: Config) -> tuple[LUMWCNN, nn.MSELoss, optim.Adam, lr_scheduler.ReduceLROnPlateau]:
    """初始化模型、优化器、学习率调度器"""
    model = LUMWCNN()
    model = model.to(cfg.device)

    criterion = nn.MSELoss()

    optimizer = optim.Adam(
        model.parameters(),
        lr=cfg.lr,
        weight_decay=cfg.weight_decay,
        betas=(., .),
        eps=e-
    )

    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode='max',
        factor=.,
        patience=,
        min_lr=e-,
        threshold=e-,
        threshold_mode='abs'
    )

    return model, criterion, optimizer, scheduler


def load_checkpoint(
    model: LUMWCNN,
    optimizer: optim.Adam,
    scheduler: lr_scheduler.ReduceLROnPlateau,
    cfg: Config,
    ckp_dir: str
) -> tuple[int, float, int]:
    """
    断点续传逻辑（修复文件名解析 + 增强鲁棒性）
    Returns:
        start_epoch: 起始epoch
        best_psnr: 历史最佳PSNR
        patience_counter: 早停计数器
    """
    start_epoch = 
    best_psnr = .
    patience_counter = 
    state_file = os.path.join(ckp_dir, 'train_state.pth')
    latest_ckpt_path: str | None = None

     扫描最新ckpt文件
    if os.path.exists(ckp_dir):
        ckpt_files = [f for f in os.listdir(ckp_dir) if f.startswith(
            'epoch_') and f.endswith('.pth')]
        print(f"\n 扫描到ckpt文件夹中的epoch文件：{ckpt_files}")

        if ckpt_files:
            ckpt_epochs: list[tuple[int, str]] = []
            for f in ckpt_files:
                try:
                    epoch_part = f.split('_')[].replace('.pth', '')
                    epoch_num = int(epoch_part)
                    ckpt_epochs.append((epoch_num, f))
                except (IndexError, ValueError) as e:
                    print(f"️ 跳过无效ckpt文件 {f}，解析失败：{e}")
                    continue

            if ckpt_epochs:
                print(f" 成功解析的ckpt文件：{ckpt_epochs}")
                latest_epoch, latest_ckpt = sorted(
                    ckpt_epochs, key=lambda x: x[], reverse=True)[]
                latest_ckpt_path = os.path.join(ckp_dir, latest_ckpt)
                print(
                    f" 自动找到最新断点文件：{latest_ckpt_path} (epoch {latest_epoch})")
            else:
                print("️ 未找到可解析的epoch_.pth文件")

     确定目标断点路径
    target_ckpt_path: str | None = None
    if cfg.resume_ckpt and os.path.exists(cfg.resume_ckpt):
        target_ckpt_path = cfg.resume_ckpt
        print(f" 检测到手动指定的断点：{target_ckpt_path}")
    elif latest_ckpt_path and os.path.exists(latest_ckpt_path):
        target_ckpt_path = latest_ckpt_path

     加载断点
    if target_ckpt_path:
        print(f"\n===== 从断点恢复：{target_ckpt_path} =====")
        try:
            ckpt = torch.load(target_ckpt_path, map_location=cfg.device)
            if isinstance(ckpt, dict) and 'state_dict' in ckpt:
                model.load_state_dict(ckpt['state_dict'])
            else:
                model.load_state_dict(ckpt)

             提取epoch数
            fname = os.path.basename(target_ckpt_path)
            epoch_part = fname.split('_')[].replace('.pth', '')
            saved_epoch = int(epoch_part)
            start_epoch = saved_epoch

             恢复状态文件
            if os.path.exists(state_file):
                state = torch.load(state_file, map_location=cfg.device)
                best_psnr = state.get('best_psnr', .)
                patience_counter = state.get('patience_counter', )

                if 'optimizer' in state and optimizer is not None:
                    optimizer.load_state_dict(state['optimizer'])
                    for opt_state in optimizer.state.values():
                        for k, v in opt_state.items():
                            if isinstance(v, torch.Tensor):
                                opt_state[k] = v.to(cfg.device)
                if 'scheduler' in state and scheduler is not None:
                    scheduler.load_state_dict(state['scheduler'])

            print(f"===== 断点恢复完成，从Epoch {start_epoch} 开始训练 =====")
            print(f" 恢复的最佳PSNR：{best_psnr:.f} | 早停计数器：{patience_counter}")
        except Exception as e:
            print(f"️  断点文件恢复失败：{e}，尝试从状态文件恢复...")
            target_ckpt_path = None

     从状态文件恢复
    if target_ckpt_path is None and os.path.exists(state_file):
        print("\n===== 从状态文件恢复训练 =====")
        try:
            state = torch.load(state_file, map_location=cfg.device)
            if 'model' in state:
                model.load_state_dict(state['model'])
            if 'optimizer' in state and optimizer is not None:
                optimizer.load_state_dict(state['optimizer'])
                for opt_state in optimizer.state.values():
                    for k, v in opt_state.items():
                        if isinstance(v, torch.Tensor):
                            opt_state[k] = v.to(cfg.device)
            if 'scheduler' in state and scheduler is not None:
                scheduler.load_state_dict(state['scheduler'])

            start_epoch = state.get('epoch', )
            best_psnr = state.get('best_psnr', .)
            patience_counter = state.get('patience_counter', )
            print(f"===== 状态文件恢复完成，从Epoch {start_epoch + } 开始训练 =====")
            print(f" 恢复的最佳PSNR：{best_psnr:.f} | 早停计数器：{patience_counter}")
        except Exception as e:
            print(f"️  状态文件恢复失败：{e}，将从头训练")
            start_epoch = 
            best_psnr = .
            patience_counter = 

     从头训练
    if target_ckpt_path is None and not os.path.exists(state_file):
        print("\n===== 无断点文件，从头开始训练 =====")

    return start_epoch, best_psnr, patience_counter


def load_datasets(cfg: Config) -> tuple[DataLoader | None, DataLoader | None]:
    """
    加载并合并训练/验证数据集
    Returns:
        train_loader: 训练数据加载器
        val_loader: 验证数据加载器
    """
    Dataset_Config = {
        'dataset_interface': 'deeplesions.DeepLesionDataset',
        'crop_size': cfg.crop_size,
        'noise_std': NOISE_STD,
        'num_workers': ,
        'max_rotation': cfg.max_rotation,
        'max_scale': cfg.max_scale,
        'min_scale': cfg.min_scale
    }

     加载数据集类
    print('Current dataset_interface: ', Dataset_Config['dataset_interface'])
    try:
        Dataset_Module = importlib.import_module(
            '.' + Dataset_Config['dataset_interface'].split('.')[], 'base.datasets')
        Dataset_Class = eval('Dataset_Module.{}'.format(
            Dataset_Config['dataset_interface'].split('.')[]))
    except Exception as e:
        print(f" 加载数据集类失败：{e}")
        sys.exit()

     训练集：key + lung + luna + covid
    train_datasets = []
    train_roots = [
        cfg.key_train_root,
        cfg.lung_train_root,
        cfg.luna_train_root
    ]
    if cfg.covid_train_root and os.path.exists(cfg.covid_train_root):
        train_roots.append(cfg.covid_train_root)

    for root in train_roots:
        if os.path.exists(root):
            train_datasets.append(Dataset_Class(
                hr_dir=root,
                crop_size=Dataset_Config['crop_size'],
                noise_std=Dataset_Config['noise_std'],
                phase='train',
                max_rotation=Dataset_Config['max_rotation'],
                max_scale=Dataset_Config['max_scale'],
                min_scale=Dataset_Config['min_scale']
            ))
        else:
            print(f"️ 训练集路径不存在：{root}，跳过")

     验证集：key + lung + luna
    val_datasets = []
    val_roots = [
        cfg.key_val_root,
        cfg.lung_val_root,
        cfg.luna_val_root
    ]
    for root in val_roots:
        if os.path.exists(root):
            val_datasets.append(Dataset_Class(
                hr_dir=root,
                crop_size=Dataset_Config['crop_size'],
                noise_std=Dataset_Config['noise_std'],
                phase='val'
            ))
        else:
            print(f"️ 验证集路径不存在：{root}，跳过")

     数据加载器
    train_set = ConcatDataset(train_datasets) if train_datasets else None
    val_set = ConcatDataset(val_datasets) if val_datasets else None

    train_loader = DataLoader(
        train_set,
        batch_size=cfg.batch_size,
        shuffle=True,
        num_workers=Dataset_Config['num_workers'],
        collate_fn=custom_collate_fn,
        pin_memory=True,
        drop_last=True
    ) if train_set else None

    val_loader = DataLoader(
        val_set,
        batch_size=,
        shuffle=False,
        pin_memory=True,
        drop_last=False
    ) if val_set else None

     打印数据集信息
    print(f"训练集总数：{len(train_set) if train_set else } 样本")
    print(f"验证集总数：{len(val_set) if val_set else } 样本")
    print("整合的训练数据集：key + lung + luna + covid（存在则包含）")
    print("整合的验证数据集：key + lung + luna（存在则包含）")

    return train_loader, val_loader

 ======================== 训练/验证核心函数 ========================


def train_one_epoch(
    model: LUMWCNN,
    train_loader: DataLoader,
    criterion: nn.MSELoss,
    optimizer: optim.Adam,
    epoch: int,
    cfg: Config,
    ckp_dir: str,
    tb: SummaryWriter | None,
    best_psnr: float,
    patience_counter: int
) -> float:
    """
    单轮训练函数
    Returns:
        epoch_loss_avg: 本轮平均损失
    """
    model.train()
    epoch_loss = AverageMeter()
    current_lr = optimizer.param_groups[]['lr']
    print(
        f"\n===== Epoch {epoch+}/{cfg.epochs} | CT影像训练 | 初始LR：{current_lr:.f} =====")

    total_samples = len(train_loader.dataset) - \
        (len(train_loader.dataset) % cfg.batch_size)
    with tqdm(
        total=total_samples,
        ncols=,
        desc=f'Epoch {epoch+}/{cfg.epochs} (CT训练)',
        unit='sample'
    ) as t:
        for data in train_loader:
            lr, hr, _ = data
            lr = lr.to(cfg.device, non_blocking=True)
            hr = hr.to(cfg.device, non_blocking=True)

             前向传播
            predict = model(lr)
            loss = criterion(predict, hr)

             更新损失
            epoch_loss.update(torch.mean(loss).detach(), n=lr.size())

             反向传播
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

             更新进度条
            t.set_postfix(loss='{:.f}'.format(epoch_loss.avg))
            t.update(lr.size())

     记录损失
    if tb:
        tb.add_scalar('Loss', epoch_loss.avg, global_step=epoch)

     保存模型
    torch.save(model.state_dict(), os.path.join(
        ckp_dir, f'epoch_{epoch+}.pth'))
    if (epoch + ) %  == :
        torch.save(model.state_dict(), os.path.join(
            ckp_dir, f'epoch_{epoch+}_key.pth'))

     清理旧模型（保留关键节点）
    if (epoch + ) >  and (epoch + ) %  != :
        old_ckpt = os.path.join(ckp_dir, f'epoch_{epoch}.pth')
        if os.path.exists(old_ckpt):
            os.remove(old_ckpt)

     保存训练状态
    state_file = os.path.join(ckp_dir, 'train_state.pth')
    train_state = {
        'epoch': epoch,
        'epoch_display': epoch + ,
        'model': model.state_dict(),
        'optimizer': optimizer.state_dict(),
        'scheduler': optimizer.state_dict(),
        'best_psnr': best_psnr,
        'patience_counter': patience_counter
    }
    torch.save(train_state, state_file)

    return epoch_loss.avg


def validate(
    model: LUMWCNN,
    val_loader: DataLoader,
    epoch: int,
    cfg: Config,
    ckp_dir: str,
    tb: SummaryWriter | None,
    best_psnr: float,
    patience_counter: int
) -> tuple[float, int]:
    """
    验证函数
    Returns:
        best_psnr: 更新后的最佳PSNR
        patience_counter: 更新后的早停计数器
    """
    if not val_loader:
        print("️ 验证集为空，跳过验证")
        return best_psnr, patience_counter

    model.eval()
    epoch_psnr = AverageMeter()
    epoch_ssim = AverageMeter()
    epoch_inf_dir = os.path.join(cfg.save_dir, val_inf_dir, f"epoch_{epoch+}")
    os.makedirs(epoch_inf_dir, exist_ok=True)

    with tqdm(val_loader, ncols=, desc='Validation', leave=True) as val_pbar:
        for idx, data in enumerate(val_pbar):
             数据解包
            if isinstance(data, (list, tuple)):
                lr, hr, filename = data[:]
            else:
                raise ValueError(f"验证集data格式错误，期望list/tuple，实际：{type(data)}")

             设备迁移
            lr = lr.to(cfg.device, non_blocking=True) if isinstance(
                lr, torch.Tensor) else torch.as_tensor(lr).to(cfg.device)
            hr = hr.to(cfg.device, non_blocking=True) if isinstance(
                hr, torch.Tensor) else torch.as_tensor(hr).to(cfg.device)

             推理（无梯度）
            with torch.no_grad():
                predict = model(lr).detach().cpu()
                hr = hr.detach().cpu()

             数值校准（批量处理）
            for i in range(predict.size()):
                pred = predict[i]
                hr_i = hr[i]

                 归一化到[,]
                pred = (pred + .) / . if pred.min() <  else pred
                hr_i = (hr_i + .) / . if hr_i.min() <  else hr_i
                pred = torch.clamp(pred, ., .)
                hr_i = torch.clamp(hr_i, ., .)

                 维度压缩
                pred = pred.squeeze() if pred.dim() >  else pred
                hr_i = hr_i.squeeze() if hr_i.dim() >  else hr_i

                 转换为范围
                pred_ = (pred  .).round().clamp(, )
                hr_ = (hr_i  .).round().clamp(, )

                 计算PSNR
                mse = torch.mean((pred_ - hr_)  )
                psnr_val = . if mse ==  else   \
                    torch.log(. / torch.sqrt(mse))

                 计算SSIM（动态win_size）
                pred_np = pred_.numpy().astype(np.uint)
                hr_np = hr_.numpy().astype(np.uint)
                min_side = min(pred_np.shape) if pred_np.ndim ==  else min(
                    pred_np.shape[:])
                win_size = min(, min_side)
                win_size = win_size if win_size %  ==  else win_size - 
                win_size = max(, win_size)

                ssim_val = structural_similarity(
                    pred_np, hr_np,
                    data_range=,
                    channel_axis=None,
                    win_size=win_size
                )

                 更新指标
                epoch_psnr.update(psnr_val.item(), n=)
                epoch_ssim.update(ssim_val, n=)

                 保存图像（仅前张，避免过多文件）
                if filename and filename[i] and idx < :
                    base_name = os.path.splitext(filename[i])[]
                     保存LR图
                    lr_cpu = lr[i].detach().cpu().squeeze().numpy()
                    lr_cpu = (lr_cpu + .) / \
                        . if lr_cpu.min() <  else lr_cpu
                    lr_cpu = np.clip(lr_cpu, ., .)  .
                    lr_img = Image.fromarray(lr_cpu.astype(np.uint), mode='L')
                    lr_img.save(os.path.join(
                        epoch_inf_dir, f"{base_name}_lr.png"))
                     保存预测图
                    pred_img = Image.fromarray(pred_np, mode='L')
                    pred_img.save(os.path.join(
                        epoch_inf_dir, f"{base_name}_pred.png"))
                     保存GT图
                    gt_img = Image.fromarray(hr_np, mode='L')
                    gt_img.save(os.path.join(
                        epoch_inf_dir, f"{base_name}_gt.png"))

             更新进度条
            val_pbar.set_postfix({
                'PSNR': f'{epoch_psnr.avg:.f} dB',
                'SSIM': f'{epoch_ssim.avg:.f}'
            })

     打印验证结果
    print("\n" + "="  )
    print(f"Epoch [{epoch+}/{cfg.epochs}] Validation Results (Full Set):")
    print(f"Val PSNR (Avg): {epoch_psnr.avg:.f} dB")
    print(f"Val SSIM (Avg): {epoch_ssim.avg:.f}")
    print("="   + "\n")

     记录TensorBoard
    if tb:
        tb.add_scalar('Val PSNR', epoch_psnr.avg, global_step=epoch)
        tb.add_scalar('Val SSIM', epoch_ssim.avg, global_step=epoch)

     早停逻辑
    if epoch_psnr.avg > best_psnr:
        best_psnr = epoch_psnr.avg
        patience_counter = 
        torch.save(model.state_dict(), os.path.join(ckp_dir, 'best_model.pth'))
        print(f" 更新最佳模型，当前最佳PSNR: {best_psnr:.f} dB")
    else:
        patience_counter += 
        print(f"️  PSNR无提升，早停计数器: {patience_counter}/{cfg.patience}")
        if patience_counter >= cfg.patience:
            print(f" 早停触发，终止训练。最佳PSNR: {best_psnr:.f} dB")
            if tb:
                tb.close()
            sys.exit()

    return best_psnr, patience_counter


def debug_validate(
    model: LUMWCNN,
    val_loader: DataLoader | None,
    cfg: Config,
    ckp_dir: str,
    tb: SummaryWriter | None
) -> tuple[float, int]:
    """
    调试专用验证函数（训练前快速验证）
    Returns:
        avg_psnr: 调试验证平均PSNR
        : 固定返回（兼容返回格式）
    """
    print("\n" + "="  )
    print(f" 开始调试验证 | 快速验证前个批次")
    print("="   + "\n")

    if not val_loader:
        print("️ 验证集为空，跳过调试验证")
        return ., 

    model.eval()
    epoch_psnr = AverageMeter()
    epoch_ssim = AverageMeter()
    debug_dir = os.path.join(cfg.save_dir, val_inf_dir, "debug")
    os.makedirs(debug_dir, exist_ok=True)

    with tqdm(val_loader, ncols=, desc='Debug Validation', leave=True) as val_pbar:
        for idx, data in enumerate(val_pbar):
            if idx >= :   仅跑前个批次
                break

            lr, hr, filename = data[:]
            lr = lr.to(cfg.device)
            hr = hr.to(cfg.device)

            with torch.no_grad():
                predict = model(lr).detach().cpu()
                hr = hr.detach().cpu()

             批量处理样本
            for i in range(predict.size()):
                pred = predict[i].squeeze()
                hr_i = hr[i].squeeze()

                 数值校准
                pred = (pred + .) / . if pred.min() <  else pred
                hr_i = (hr_i + .) / . if hr_i.min() <  else hr_i
                pred = torch.clamp(pred, ., .)
                hr_i = torch.clamp(hr_i, ., .)

                 计算指标
                pred_ = (pred  .).round().clamp(, )
                hr_ = (hr_i  .).round().clamp(, )
                mse = torch.mean((pred_ - hr_)  )
                psnr_val = . if mse ==  else   \
                    torch.log(. / torch.sqrt(mse))

                pred_np = pred_.numpy().astype(np.uint)
                hr_np = hr_.numpy().astype(np.uint)
                min_side = min(pred_np.shape)
                win_size = min(, min_side)
                win_size = win_size if win_size %  ==  else win_size - 
                win_size = max(, win_size)
                ssim_val = structural_similarity(
                    pred_np, hr_np, data_range=, channel_axis=None, win_size=win_size)

                epoch_psnr.update(psnr_val.item())
                epoch_ssim.update(ssim_val)

                 保存调试图像
                if filename and filename[i]:
                    base_name = f"debug_{idx}_{i}_{os.path.splitext(filename[i])[]}"
                    lr_cpu = lr[i].detach().cpu().squeeze().numpy()
                    lr_cpu = (lr_cpu + .) / \
                        . if lr_cpu.min() <  else lr_cpu
                    lr_cpu = np.clip(lr_cpu, ., .)  .
                    Image.fromarray(lr_cpu.astype(np.uint), mode='L').save(
                        os.path.join(debug_dir, f"{base_name}_lr.png"))
                    Image.fromarray(pred_np, mode='L').save(
                        os.path.join(debug_dir, f"{base_name}_pred.png"))
                    Image.fromarray(hr_np, mode='L').save(
                        os.path.join(debug_dir, f"{base_name}_gt.png"))

            val_pbar.set_postfix({
                'PSNR': f'{epoch_psnr.avg:.f} dB',
                'SSIM': f'{epoch_ssim.avg:.f}',
                'Debug': f'批次{idx+}/'
            })

    print("\n" + "="  )
    print(f" 调试验证完成 | 前批次平均指标：")
    print(f"   PSNR: {epoch_psnr.avg:.f} dB | SSIM: {epoch_ssim.avg:.f}")
    print("="   + "\n")

    return epoch_psnr.avg, 


def emergency_save(
    model: LUMWCNN,
    optimizer: optim.Adam,
    scheduler: lr_scheduler.ReduceLROnPlateau,
    epoch: int,
    best_psnr: float,
    patience_counter: int,
    train_loss: float,
    ckp_dir: str
) -> None:
    """紧急保存训练状态（异常中断时）"""
    emergency_ckpt = os.path.join(ckp_dir, 'emergency_model.pth')
    torch.save(model.state_dict(), emergency_ckpt)

    emergency_state = {
        'epoch': epoch,
        'epoch_display': epoch + ,
        'model': model.state_dict(),
        'optimizer': optimizer.state_dict(),
        'scheduler': scheduler.state_dict(),
        'best_psnr': best_psnr,
        'patience_counter': patience_counter,
        'interrupt_loss': train_loss
    }
    torch.save(emergency_state, os.path.join(
        ckp_dir, 'emergency_train_state.pth'))
    print(f" 紧急保存模型：{emergency_ckpt}")

 ======================== 主函数 ========================


def main() -> None:
    """主训练流程（模块化重构）"""
     . 初始化核心组件
    model, criterion, optimizer, scheduler = init_model_optimizer_scheduler(
        cfg)

     . 断点恢复
    start_epoch, best_psnr, patience_counter = load_checkpoint(
        model, optimizer, scheduler, cfg, ckp_dir)

     . 加载数据集
    train_loader, val_loader = load_datasets(cfg)
    if not train_loader:
        print(" 训练集为空，无法开始训练")
        return

     . 训练前调试验证
    debug_validate(model, val_loader, cfg, ckp_dir, tb)
    user_choice = input("\n 调试验证完成，是否继续正式训练？(y/n): ").lower()
    if user_choice != 'y':
        print(" 用户终止训练")
        if tb:
            tb.close()
        return

     . 训练主循环
    emergency = False
    train_loss = .
    try:
        for epoch in range(start_epoch, cfg.epochs):
             单轮训练（修复参数传递错误）
            train_loss = train_one_epoch(
                model=model,
                train_loader=train_loader,
                criterion=criterion,
                optimizer=optimizer,
                epoch=epoch,
                cfg=cfg,
                ckp_dir=ckp_dir,
                tb=tb,
                best_psnr=best_psnr,
                patience_counter=patience_counter
            )

             验证逻辑
            if epoch ==  or (epoch + ) % VAL_EVERY == :
                best_psnr, patience_counter = validate(
                    model=model,
                    val_loader=val_loader,
                    epoch=epoch,
                    cfg=cfg,
                    ckp_dir=ckp_dir,
                    tb=tb,
                    best_psnr=best_psnr,
                    patience_counter=patience_counter
                )
                 调整学习率（验证后）
                step_scheduler(scheduler, optimizer, epoch, metric=best_psnr)
            else:
                 非验证轮次，用训练损失调整
                step_scheduler(scheduler, optimizer, epoch,
                               train_loss=train_loss)

    except (KeyboardInterrupt, Exception) as e:
        print(f"\n 训练异常中断：{e}")
        emergency = True

         紧急保存
        interrupt_loss = safe_extract_scalar(train_loss)
        emergency_save(
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            epoch=epoch,
            best_psnr=best_psnr,
            patience_counter=patience_counter,
            train_loss=interrupt_loss,
            ckp_dir=ckp_dir
        )
        raise e
    finally:
         收尾工作
        if tb:
            tb.close()
        final_best_psnr = best_psnr if 'best_psnr' in locals() else .
        print(f"\n训练结束，最佳PSNR：{final_best_psnr:.f} dB")
        if emergency:
            print("️  本次训练为异常中断，可通过resume_ckpt='emergency_model.pth'续训")


if __name__ == '__main__':
    main()
