import numpy as np
import cv2
from typing import Union, Tuple, List
import matplotlib.pyplot as plt

def find_wave_height_range(img: np.ndarray) -> Tuple[int, int]:
    """
    找到波形的高度范围
    
    参数:
        img: 灰度图像
    
    返回:
        起始和结束的y坐标
    """
    # 计算每行的标准差，波形部分的标准差会比较大
    row_std = np.std(img, axis=1)
    
    # 使用自适应阈值找到波形区域
    threshold = np.mean(row_std) * 0.3  # 降低阈值以包含更多区域
    wave_rows = row_std > threshold
    
    # 找到第一个和最后一个超过阈值的位置
    wave_indices = np.where(wave_rows)[0]
    if len(wave_indices) == 0:
        return 0, img.shape[0]
        
    start_y = max(0, wave_indices[0] - 10)  # 向上扩展一点
    end_y = min(img.shape[0], wave_indices[-1] + 10)  # 向下扩展一点
    
    return start_y, end_y

def image_to_sequence(img: Union[str, np.ndarray], 
                     mode: str = 'dark-foreground',
                     method: str = 'combined_all_neighbors',
                     window_len: int = 3,
                     plot_result: bool = False) -> np.ndarray:
    """
    从图像中提取时间序列数据（ECG波形）。

    参数:
        img: 输入图像路径或numpy数组
        mode: 前景类型 - 'dark-foreground' 或 'bright-foreground'
        method: 滤波方法 - 'max_finder', 'moving_average', 'hor_smoothing', 
               'all_left_right_neighbors', 'combined_all_neighbors'
        window_len: 移动平均窗口长度
        plot_result: 是否绘制结果

    返回:
        提取的序列数据（numpy数组）
    """
    # 加载图像
    if isinstance(img, str):
        img = cv2.imread(img, cv2.IMREAD_GRAYSCALE)
    elif len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 找到波形的高度范围
    start_y, end_y = find_wave_height_range(img)
    img = img[start_y:end_y, :]
    
    # 根据模式反转图像
    if mode == 'dark-foreground':
        img = 255 - img
    
    height, width = img.shape
    
    # 根据不同方法处理图像
    if method == 'max_finder':
        img_filtered = img
    
    elif method == 'moving_average':
        kernel = np.ones((window_len, window_len)) / (window_len * window_len)
        img_filtered = cv2.filter2D(img, -1, kernel)
    
    elif method == 'hor_smoothing':
        kernel = np.ones((1, window_len)) / window_len
        img_filtered = cv2.filter2D(img, -1, kernel)
    
    elif method == 'all_left_right_neighbors':
        kernel = np.array([[1, 0, 1],
                          [1, 1, 1],
                          [1, 0, 1]]) / 6
        img_filtered = cv2.filter2D(img, -1, kernel)
    
    elif method == 'combined_all_neighbors':
        # 水平方向
        h1 = np.array([[1, 1, 1]]) / 3
        z1 = cv2.filter2D(img, -1, h1)
        
        # 右下到左上
        h2 = np.array([[1, 0, 0],
                       [0, 1, 0],
                       [0, 0, 1]]) / 3
        z2 = cv2.filter2D(img, -1, h2)
        
        # 左下到右上
        h3 = np.array([[0, 0, 1],
                       [0, 1, 0],
                       [1, 0, 0]]) / 3
        z3 = cv2.filter2D(img, -1, h3)
        
        img_filtered = np.minimum(np.minimum(z1, z2), z3)
    
    # 找每列的最大值点（波形位置）
    data = np.argmax(img_filtered, axis=0)
    
    # 转换为波形振幅（反转Y轴）
    data = height - data
    
    # 归一化数据到0-1范围
    data = (data - np.min(data)) / (np.max(data) - np.min(data))
    
    # 绘制结果
    if plot_result:
        plt.figure(figsize=(15, 5))
        plt.imshow(cv2.cvtColor(img, cv2.COLOR_GRAY2RGB))
        plt.plot(np.arange(width), height - data * height, 'g', linewidth=2)
        plt.title('Extracted ECG Waveform')
        plt.xlabel('Sample')
        plt.ylabel('Amplitude')
        plt.grid(True)
        plt.show()
    
    return data

def extract_lead_waveform(image: np.ndarray, 
                         bbox: List[int],
                         lead_id: int = None,
                         **kwargs) -> np.ndarray:
    """
    从检测到的导联区域提取波形数据。

    参数:
        image: 原始图像
        bbox: 边界框坐标 [x1, y1, x2, y2]
        lead_id: 导联ID，用于位置验证
            - 0-2: I, II, III (左侧)
            - 3-5: aVR, aVL, aVF (中间)
            - 6-11: V1-V6 (右侧)
        **kwargs: 传递给image_to_sequence的参数

    返回:
        波形数据（numpy array）
    """
    x1, y1, x2, y2 = bbox
    width = image.shape[1]
    
    # 根据导联ID验证位置
    if lead_id is not None:
        x_center = (x1 + x2) / 2
        x_ratio = x_center / width
        
        # 检查位置是否合理
        if lead_id <= 2:  # I, II, III 应该在左侧
            if x_ratio > 0.4:
                print(f"警告：导联 {lead_id} (I/II/III) 位置偏右 (x_ratio={x_ratio:.2f})")
                # 调整到合适的位置
                shift = int(width * (x_ratio - 0.2))  # 向左移动到20%位置
                x1 = max(0, x1 - shift)
                x2 = min(width, x2 - shift)
                
        elif lead_id <= 5:  # aVR, aVL, aVF 应该在中间
            if x_ratio < 0.3 or x_ratio > 0.7:
                print(f"警告：导联 {lead_id} (aVR/aVL/aVF) 位置不在中间 (x_ratio={x_ratio:.2f})")
                # 调整到合适的位置
                target_x = width * 0.5  # 目标位置在中间
                current_x = (x1 + x2) / 2
                shift = int(target_x - current_x)
                x1 = max(0, x1 + shift)
                x2 = min(width, x2 + shift)
                
        else:  # V1-V6 应该在右侧
            if x_ratio < 0.6:
                print(f"警告：导联 {lead_id} (V1-V6) 位置偏左 (x_ratio={x_ratio:.2f})")
                # 调整到合适的位置
                shift = int(width * (0.8 - x_ratio))  # 向右移动到80%位置
                x1 = max(0, x1 + shift)
                x2 = min(width, x2 + shift)
    
    # 提取区域
    lead_image = image[y1:y2, x1:x2]
    if lead_image.size == 0:
        raise ValueError(f"无效的导联区域: bbox={bbox}")
        
    # 转换为波形
    sequence = image_to_sequence(lead_image, **kwargs)
    return sequence
