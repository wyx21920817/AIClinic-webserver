import numpy as np
import cv2
from typing import Union, Tuple, List
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
import logging

# Set up logging
logger = logging.getLogger(__name__)

def find_wave_height_range(img: np.ndarray) -> Tuple[int, int]:
    """
    Find the height range of the waveform
    
    参数:
        img: Grayscale image
    
    返回:
        Start and end y coordinates
    """
    # Calculate standard deviation for each row, waveform areas will have higher std
    row_std = np.std(img, axis=1)
    
    # Use adaptive threshold to find waveform region
    threshold = np.mean(row_std) * 0.3  # Lower threshold to include more area
    wave_rows = row_std > threshold
    
    # Find first and last positions that exceed threshold
    wave_indices = np.where(wave_rows)[0]
    if len(wave_indices) == 0:
        return 0, img.shape[0]
        
    start_y = max(0, wave_indices[0] - 10)  # Extend up a bit
    end_y = min(img.shape[0], wave_indices[-1] + 10)  # Extend down a bit
    
    return start_y, end_y

def image_to_sequence(img: Union[str, np.ndarray], 
                     mode: str = 'dark-foreground',
                     method: str = 'combined_all_neighbors',
                     window_len: int = 3,
                     plot_result: bool = False) -> np.ndarray:
    """
    Extract time series data (ECG waveform) from ECG image.

    Parameters:
        img: Input image path or numpy array
        mode: Foreground type - 'dark-foreground' or 'bright-foreground'
        method: Filter method - 'max_finder', 'moving_average', 'hor_smoothing', 
               'all_left_right_neighbors', 'combined_all_neighbors'
        window_len: Moving average window length
        plot_result: Whether to plot results

    Returns:
        Extracted sequence data (numpy array)
    """
    # Use new waveform extraction method
    x_coords, waveform = extract_waveform_new(img, mode=mode, plot_result=plot_result)
    
    # If new method fails, use original method
    if len(waveform) == 0:
        logger.warning("New method failed to detect waveform, using original method")
        
        # Load image
        if isinstance(img, str):
            img = cv2.imread(img, cv2.IMREAD_GRAYSCALE)
        elif len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Find waveform height range
        start_y, end_y = find_wave_height_range(img)
        img = img[start_y:end_y, :]
        
        # Invert image based on mode
        if mode == 'dark-foreground':
            img = 255 - img
        
        height, width = img.shape
        
        # Standardize image size
        target_height = 1000
        target_width = 3000
        if height != target_height or width != target_width:
            img = cv2.resize(img, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
            height, width = target_height, target_width
            logger.info(f"Adjusting image size to standard dimensions: {width}x{height}")
        
        # Process image based on different methods
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
            # Horizontal direction
            h1 = np.array([[1, 1, 1]]) / 3
            z1 = cv2.filter2D(img, -1, h1)
            
            # Bottom right to top left
            h2 = np.array([[1, 0, 0],
                          [0, 1, 0],
                          [0, 0, 1]]) / 3
            z2 = cv2.filter2D(img, -1, h2)
            
            # Bottom left to top right
            h3 = np.array([[0, 0, 1],
                          [0, 1, 0],
                          [1, 0, 0]]) / 3
            z3 = cv2.filter2D(img, -1, h3)
            
            img_filtered = np.minimum(np.minimum(z1, z2), z3)
        
        # Find maximum point for each column (waveform position)
        waveform = np.argmax(img_filtered, axis=0)
        logger.info(f"Data after argmax: type={waveform.dtype}, min={waveform.min()}, max={waveform.max()}")
        
        # Convert to waveform amplitude (invert Y axis)
        waveform = height - waveform
        logger.info(f"Data after Y axis inversion: type={waveform.dtype}, min={waveform.min()}, max={waveform.max()}")
        
        # Scale data to appropriate range (-5 to 5)
        waveform = ((waveform - np.min(waveform)) / (np.max(waveform) - np.min(waveform)) * 10) - 5
        logger.info(f"Data after scaling: type={waveform.dtype}, min={waveform.min():.3f}, max={waveform.max():.3f}, first 20 points={waveform[:20]}")
        
        # Plot results
        if plot_result:
            plt.figure(figsize=(15, 5))
            plt.imshow(cv2.cvtColor(img, cv2.COLOR_GRAY2RGB))
            plt.plot(np.arange(width), height - waveform * height, 'g', linewidth=2)
            plt.title('Extracted ECG Waveform')
            plt.xlabel('Sample')
            plt.ylabel('Amplitude')
            plt.grid(True)
            plt.show()
    
    return waveform

def extract_lead_waveform(image: np.ndarray, 
                         bbox: List[int],
                         lead_id: int = None,
                         **kwargs) -> np.ndarray:
    """
    Extract waveform data from detected lead area.

    参数:
        image: Original image
        bbox: Bounding box coordinates [x1, y1, x2, y2]
        lead_id: Lead ID for position verification
            - 0-2: I, II, III (left side)
            - 3-5: aVR, aVL, aVF (middle)
            - 6-11: V1-V6 (right side)
        **kwargs: Parameters passed to image_to_sequence

    Returns:
        Waveform data (numpy array)
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

def remove_text_noise(img: np.ndarray) -> Tuple[np.ndarray, Tuple[int, int]]:
    """
    通过分析5段区域的垂直分布来确定波形区间，移除区间外的所有内容

    参数:
        img: 输入图像（灰度图）

    返回:
        处理后的图像和波形区间 (wave_top, wave_bottom)
    """
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()
    
    # 1. 使用Otsu's二值化获取前景
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # 2. 将图像水平分成5段
    height, width = binary.shape
    segment_width = width // 5
    segments_distribution = []
    
    # 分析每段的垂直分布
    for i in range(5):
        start_x = i * segment_width
        end_x = (i + 1) * segment_width if i < 4 else width
        
        # 获取当前段的区域
        segment = binary[:, start_x:end_x]
        
        # 计算该段每行的像素和并平滑
        row_sums = np.sum(segment, axis=1)
        window_size = 10
        smoothed_sums = np.convolve(row_sums, np.ones(window_size)/window_size, mode='same')
        
        # 找到活跃区域（像素和大于平均值的一定比例）
        threshold = np.mean(smoothed_sums) * 0.3
        active_rows = smoothed_sums > threshold
        active_indices = np.where(active_rows)[0]
        
        if len(active_indices) > 0:
            segments_distribution.append((min(active_indices), max(active_indices)))
    
    # 3. 找到所有段共同的活跃区间
    if segments_distribution:
        # 取所有段的上边界的最大值作为波形区域的上边界
        wave_top = max(seg[0] for seg in segments_distribution)
        # 取所有段的下边界的最小值作为波形区域的下边界
        wave_bottom = min(seg[1] for seg in segments_distribution)
        
        # 适当扩展区间
        margin = 20
        wave_top = max(0, wave_top - margin)
        wave_bottom = min(height, wave_bottom + margin)
        
        # 4. 创建结果图像（白色背景）
        result = np.full_like(gray, 255)
        
        # 5. 只保留波形区间内的内容
        result[wave_top:wave_bottom, :] = gray[wave_top:wave_bottom, :]
        
        return result, (wave_top, wave_bottom)
    else:
        return gray, None

def extract_waveform_new(img: Union[str, np.ndarray],
                        mode: str = 'dark-foreground',
                        plot_result: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """
    使用改进的方法从图像中提取波形序列。
    
    参数:
        img: 输入图像路径或numpy数组
        mode: 前景类型 - 'dark-foreground' 或 'bright-foreground'
        plot_result: 是否绘制结果
        
    返回:
        x坐标和y坐标数组的元组 (x_coords, y_coords)
    """
    # 加载图像
    if isinstance(img, str):
        img = cv2.imread(img, cv2.IMREAD_GRAYSCALE)
    elif len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 首先去除文字噪音并获取波形区间
    img, wave_region = remove_text_noise(img)
    
    if wave_region is None:
        return np.array([]), np.array([])
    
    # 直接使用波形区间
    wave_top, wave_bottom = wave_region
    img = img[wave_top:wave_bottom, :]
    
    # 根据模式反转图像
    if mode == 'dark-foreground':
        img = 255 - img
    
    # 标准化图像大小
    target_height = 1000
    target_width = 3000
    height, width = img.shape
    if height != target_height or width != target_width:
        img = cv2.resize(img, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
        height, width = target_height, target_width
    
    # 使用combined_all_neighbors方法
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
    
    # 取最小值
    img_filtered = np.minimum(np.minimum(z1, z2), z3)
    
    # 找每列的最大值点（波形位置）
    data = np.argmax(img_filtered, axis=0)
    
    # 缩放数据到合适的范围（-5到5）
    data = ((data - np.min(data)) / (np.max(data) - np.min(data)) * 10) - 5
    
    # 最后反转一下数据，使波形方向正确
    data = -data
    
    # 绘制结果
    if plot_result:
        plt.figure(figsize=(15, 5))
        plt.subplot(211)
        plt.imshow(cv2.cvtColor(img, cv2.COLOR_GRAY2RGB))
        plt.title('Processed Image')
        plt.subplot(212)
        plt.plot(data, 'r-', linewidth=1)
        plt.title('Extracted Waveform')
        plt.grid(True)
        plt.tight_layout()
        plt.show()
    
    # 返回x坐标和y坐标
    x_coords = np.arange(len(data))
    return x_coords, data
