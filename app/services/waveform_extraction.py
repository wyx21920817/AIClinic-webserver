import cv2
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
from .image_to_sequence import image_to_sequence
import os
import logging
from scipy import interpolate
from pathlib import Path

logger = logging.getLogger("AIClinic")

def is_valid_lead_box(w, h, max_width_ratio=0.5, min_width_ratio=0.1, 
                     max_height_ratio=0.3, min_height_ratio=0.1):
    """
    检查导联框是否合理
    
    参数:
        w, h: 框的宽高（相对值，0-1之间）
        max_width_ratio: 最大允许宽度比例
        min_width_ratio: 最小允许宽度比例
        max_height_ratio: 最大允许高度比例
        min_height_ratio: 最小允许高度比例
    """
    logger.info(f"验证检测框: w={w:.3f}, h={h:.3f}")
    logger.info(f"宽度范围: {min_width_ratio:.3f} - {max_width_ratio:.3f}")
    logger.info(f"高度范围: {min_height_ratio:.3f} - {max_height_ratio:.3f}")
    
    valid = (min_width_ratio <= w <= max_width_ratio and 
            min_height_ratio <= h <= max_height_ratio)
    
    if not valid:
        if not (min_width_ratio <= w <= max_width_ratio):
            logger.warning(f"宽度 {w:.3f} 超出范围 [{min_width_ratio:.3f}, {max_width_ratio:.3f}]")
        if not (min_height_ratio <= h <= max_height_ratio):
            logger.warning(f"高度 {h:.3f} 超出范围 [{min_height_ratio:.3f}, {max_height_ratio:.3f}]")
    
    return valid

def get_region(y, height):
    """
    确定区域
    返回: 0 (top), 1 (middle), 2 (bottom)
    """
    if y < height * 0.2:  # 上20%
        return 0
    elif y > height * 0.8:  # 下20%
        return 2
    else:  # 中间60%
        return 1

def filter_boxes(boxes, height):
    """
    过滤检测框：
    1. 去掉宽度过大或过小的框
    2. 去掉高度过大或过小的框
    3. 去掉重复的框（位置非常接近的框）
    """
    if not boxes:
        return []
    
    print(f"\n开始过滤，原始检测框数量：{len(boxes)}")
    
    # 按x坐标排序
    sorted_boxes = sorted(boxes, key=lambda x: x[1])  # x[1]是x_center
    
    # 去掉宽度和高度不合适的框
    filtered = []
    for box in sorted_boxes:
        if is_valid_lead_box(box[3], box[4]):  # 使用is_valid_lead_box检查宽高
            filtered.append(box)
    
    print(f"宽高过滤后剩余：{len(filtered)} 个框")
    
    # 去掉重复的框（x和y坐标都非常接近的框）
    no_duplicates = []
    for box in filtered:
        # 检查是否和已保留的框重复
        is_duplicate = False
        for kept_box in no_duplicates:
            x_diff = abs(box[1] - kept_box[1])
            y_diff = abs(box[2] - kept_box[2])
            if x_diff < 0.02 and y_diff < 0.02:  # 如果x和y的差距都小于0.02，认为是重复的框
                is_duplicate = True
                break
        if not is_duplicate:
            no_duplicates.append(box)
    
    print(f"去重后剩余：{len(no_duplicates)} 个框")
    return no_duplicates

def filter_boxes_by_x(boxes, min_x_diff=50):
    """
    在x方向上过滤框：
    1. 选择x最小的框作为第一个
    2. 后面的框必须比前一个x大至少min_x_diff像素
    """
    if len(boxes) <= 4:
        return boxes
    
    # 按x坐标排序
    sorted_boxes = sorted(boxes, key=lambda x: x[1])  # x[1]是x_center
    
    filtered = [sorted_boxes[0]]  # 保留x最小的框
    last_x = sorted_boxes[0][1]
    
    # 遍历剩余的框
    for box in sorted_boxes[1:]:
        if box[1] - last_x >= min_x_diff/1000:  # 如果x差距足够大
            filtered.append(box)
            last_x = box[1]
            if len(filtered) >= 4:  # 已经有4个框了，不需要更多
                break
    
    return filtered

def cluster_boxes_by_y(boxes, min_gap=0.1):
    """
    根据y坐标的相似度将框分组
    boxes: [(class_id, x_center, y_center, w, h), ...]
    min_gap: 不同组之间的最小y差距
    """
    if not boxes:
        return []
    
    # 按y坐标排序
    sorted_boxes = sorted(boxes, key=lambda x: x[2])  # x[2]是y_center
    
    # 计算相邻框之间的y差距
    gaps = []
    for i in range(1, len(sorted_boxes)):
        gap = sorted_boxes[i][2] - sorted_boxes[i-1][2]
        gaps.append((i, gap))
    
    # 按差距大小排序，找出最大的几个差距位置
    gaps.sort(key=lambda x: x[1], reverse=True)
    
    # 找出差距大于min_gap的分割点
    split_points = []
    for idx, gap in gaps:
        if gap >= min_gap:
            split_points.append(idx)
    split_points.sort()  # 按位置排序
    
    # 根据分割点分组
    clusters = []
    start = 0
    for split in split_points:
        if split > start:
            clusters.append(sorted_boxes[start:split])
        start = split
    # 添加最后一组
    if start < len(sorted_boxes):
        clusters.append(sorted_boxes[start:])
    
    # 打印每个簇的y坐标
    print("\n检测到的组：")
    for i, cluster in enumerate(clusters):
        y_mean = sum(box[2] for box in cluster) / len(cluster)
        print(f"组 {i+1}: y≈{y_mean:.3f}, 框数量={len(cluster)}")
        for box in cluster:
            class_id, x, y, w, h = box
            print(f"  - ID={class_id}, x={x:.3f}, y={y:.3f}, w={w:.3f}, h={h:.3f}")
    
    # 如果有4组或更多，只保留前3组
    if len(clusters) > 3:
        print(f"\n检测到 {len(clusters)} 组，只保留前3组")
        return clusters[:3]
    
    return clusters

def assign_leads(boxes, height):
    """
    根据区域和位置分配导联
    boxes: [(class_id, x_center, y_center, w, h), ...]
    """
    logger.info("\n开始分配导联...")
    
    # 根据y坐标聚类
    clusters = cluster_boxes_by_y(boxes)
    
    # 如果没有得到至少3组，返回空
    if len(clusters) < 3:
        logger.warning(f"警告：只检测到 {len(clusters)} 组框，需要至少3组")
        return {}
        
    # 按y坐标平均值排序，分配区域
    boxes_by_region = {
        'top': clusters[0],      # y最小的组
        'middle': clusters[1],   # y中间的组
        'bottom': clusters[2]    # y最大的组
    }
    
    # 每个区域的导联分配顺序（从左到右）
    region_leads = {
        'top': ['I', 'aVR', 'V1', 'V4'],      # 按x从小到大的顺序
        'middle': ['II', 'aVL', 'V2', 'V5'],  # 按x从小到大的顺序
        'bottom': ['III', 'aVF', 'V3', 'V6']  # 按x从小到大的顺序
    }
    
    leads = {}
    for region, region_boxes in boxes_by_region.items():
        logger.info(f"\n{region} 区域:")
        logger.info(f"需要分配的导联: {region_leads[region]}")
        logger.info(f"可用的框数量: {len(region_boxes)}")
        
        # 按x坐标排序
        region_boxes.sort(key=lambda x: x[1])
        logger.info("按x坐标排序后的框:")
        for box in region_boxes:
            logger.info(f"  x={box[1]:.2f}, y={box[2]:.2f}")
        
        # 如果框数超过4个，按x坐标分成4组，每组取第一个
        if len(region_boxes) > 4:
            logger.info(f"\n框数({len(region_boxes)})超过4个，进行分组:")
            target_groups = 4
            boxes_per_group = len(region_boxes) // target_groups
            remainder = len(region_boxes) % target_groups
            logger.info(f"每组基础框数: {boxes_per_group}, 余数: {remainder}")
            
            grouped_boxes = []
            start = 0
            for i in range(target_groups):
                group_size = boxes_per_group + (1 if i < remainder else 0)
                end = start + group_size
                # 每组取第一个框
                grouped_boxes.append(region_boxes[start])
                logger.info(f"组 {i+1}: 从位置{start}取框, x={region_boxes[start][1]:.2f}")
                start = end
            region_boxes = grouped_boxes
            logger.info(f"分组后保留的框数: {len(region_boxes)}")
        
        logger.info("\n开始分配导联:")
        # 分配导联（按照指定的顺序）
        for lead_name, box in zip(region_leads[region], region_boxes):
            _, x, y, w, h = box
            leads[lead_name] = (x, y, w, h)
            logger.info(f"分配 {lead_name}: x={x:.2f}, y={y:.2f}")
    
    logger.info("\n导联分配完成!")
    return leads

def extract_lead_waveform(image, bbox, target_length=3000, force_length=True, save_path=None, plot_result=False):
    """
    从图像中提取指定区域的波形
    image: 输入图像
    bbox: (x, y, w, h) 相对坐标，范围0-1
    target_length: 目标波形长度，默认3000点
    force_length: 是否强制使用目标长度，默认True表示强制使用3000点
    save_path: 可选，保存切片图像的路径
    plot_result: 可选，是否绘制波形，默认False
    """
    height, width = image.shape[:2]
    x, y, w, h = bbox
    
    # 转换为像素坐标（使用中心点坐标）
    x1 = int((x - w/2) * width)
    y1 = int((y - h/2) * height)
    x2 = int((x + w/2) * width)
    y2 = int((y + h/2) * height)
    
    # 确保坐标在有效范围内
    x1 = max(0, min(x1, width-1))
    y1 = max(0, min(y1, height-1))
    x2 = max(0, min(x2, width-1))
    y2 = max(0, min(y2, height-1))
    
    # 提取区域图像
    lead_image = image[y1:y2, x1:x2].copy()
    
    # 如果提供了保存路径，保存切片图像
    if save_path:
        cv2.imwrite(save_path, lead_image)
        logger.info(f"已保存切片图像到: {save_path}")
    
    # 使用专门的ECG波形提取函数
    waveform = image_to_sequence(lead_image, mode='dark-foreground', method='combined_all_neighbors', plot_result=False)
    logger.info(f"提取的波形: 类型={waveform.dtype}, 最小值={waveform.min():.3f}, 最大值={waveform.max():.3f}")
    
    # 记录波形信息
    logger.info(f"波形统计信息: 长度={len(waveform)}, 最小值={waveform.min():.3f}, 最大值={waveform.max():.3f}, 均值={waveform.mean():.3f}")
    logger.info(f"波形前20个点: {waveform[:20]}")
    logger.info(f"波形后20个点: {waveform[-20:]}")
    
    # 确保波形长度为3000点
    if len(waveform) != target_length:
        # 创建原始时间点
        x_original = np.linspace(0, 1, len(waveform))
        # 创建目标时间点
        x_target = np.linspace(0, 1, target_length)
        # 使用三次样条插值
        interpolator = interp1d(x_original, waveform, kind='cubic', bounds_error=False, fill_value="extrapolate")
        # 重采样
        waveform = interpolator(x_target)
    
    return waveform

def plot_all_leads(image_path, labels_path, output_dir='dicom_files/test', use_min_length=True):
    """
    读取图像和标签，提取波形
    
    参数:
        image_path: 输入图像路径
        labels_path: 标签文件路径
        output_dir: 输出目录，默认为'dicom_files/test'
        use_min_length: 是否使用最短导联长度作为参考，默认True
        
    返回:
        dict: 导联名称到波形数据的映射
    """
    # 读取图像
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"无法读取图像: {image_path}")
    
    # 转换为灰度图
    if len(image.shape) == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    height, width = image.shape
    
    # 读取标签
    if not os.path.exists(labels_path):
        raise ValueError(f"标签文件不存在: {labels_path}")
        
    with open(labels_path, 'r') as f:
        lines = f.readlines()
    
    # 解析标签
    boxes = []
    
    for line in lines:
        values = line.strip().split()
        if len(values) == 5:
            class_id = int(values[0])
            x_center = float(values[1])
            y_center = float(values[2])
            w = float(values[3])
            h = float(values[4])
            boxes.append((class_id, x_center, y_center, w, h))
    
    # 过滤和分配导联
    leads = assign_leads(boxes, height)
    if not leads:
        raise ValueError("未能正确分配导联")
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 创建切片图像目录
    slices_dir = os.path.join(output_dir, 'slices')
    os.makedirs(slices_dir, exist_ok=True)
    
    # 提取波形
    waveforms = {}
    lengths = []  # 用于存储每个导联的长度
    
    # 先提取所有导联的波形，记录长度
    for lead_name, bbox in leads.items():
        try:
            # 构建切片图像保存路径
            slice_path = os.path.join(slices_dir, f'lead_{lead_name}.png')
            waveform = extract_lead_waveform(image, bbox, save_path=slice_path, plot_result=False)
            waveforms[lead_name] = waveform
            lengths.append(len(waveform))
        except Exception as e:
            logger.error(f"提取导联 {lead_name} 的波形时出错: {str(e)}")
            continue
    
    # 如果需要使用最短长度
    if use_min_length and lengths:
        min_length = min(lengths)
        logger.info(f"使用最短导联长度作为参考: {min_length}")
        
        # 重新提取所有波形
        for lead_name, bbox in leads.items():
            try:
                # 构建切片图像保存路径
                slice_path = os.path.join(slices_dir, f'lead_{lead_name}_resampled.png')
                waveform = extract_lead_waveform(image, bbox, target_length=min_length, force_length=True, save_path=slice_path, plot_result=False)
                waveforms[lead_name] = waveform
            except Exception as e:
                logger.error(f"重采样导联 {lead_name} 的波形时出错: {str(e)}")
                continue
    
    # 绘制波形
    plt.figure(figsize=(15, 10))
    for i, (lead_name, waveform) in enumerate(waveforms.items(), 1):
        plt.subplot(4, 3, i)
        plt.plot(waveform)
        plt.title(f'Lead {lead_name} (len={len(waveform)})')
        plt.grid(True)
    
    # 保存图像
    output_path = os.path.join(output_dir, Path(image_path).stem + '_waveforms.png')
    plt.savefig(output_path)
    plt.close()
    
    return waveforms

if __name__ == '__main__':
    # 使用最新的检测结果
    image_path = "D:/study/csproject/AIClinic/AIClinic-webserver/runs/detect/exp8/test.png"
    labels_path = "D:/study/csproject/AIClinic/AIClinic-webserver/runs/detect/exp8/labels/test.txt"
    
    plot_all_leads(image_path, labels_path)
