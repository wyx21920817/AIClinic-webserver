import os
import numpy as np
import pydicom
import matplotlib.pyplot as plt
import sys

def read_waveform_data(dcm_path):
    """读取DICOM文件中的波形数据"""
    print(f"\n分析文件: {dcm_path}")
    ds = pydicom.dcmread(dcm_path)
    
    # 获取波形数据
    waveform_seq = ds.WaveformSequence[0]
    num_channels = waveform_seq.NumberOfWaveformChannels
    num_samples = waveform_seq.NumberOfWaveformSamples
    print(f"通道数: {num_channels}")
    print(f"每个通道的采样点数: {num_samples}")
    
    # 获取通道信息
    channels = []
    sensitivities = []
    for channel in waveform_seq.ChannelDefinitionSequence:
        channels.append(channel.ChannelLabel)
        sensitivities.append(float(channel.ChannelSensitivity))
    print(f"通道标签: {channels}")
    print(f"灵敏度: {sensitivities}")
    
    # 读取波形数据
    waveform_data = np.frombuffer(waveform_seq.WaveformData, dtype=np.int16)
    print(f"原始波形数据大小: {len(waveform_data)}")
    print(f"预期数据大小: {num_channels * num_samples}")
    
    # 检查是否需要调整数据大小
    total_points = len(waveform_data)
    if total_points != num_channels * num_samples:
        print("警告：数据大小与预期不符，尝试调整...")
        # 尝试找到最接近的合适维度
        possible_samples = total_points // num_channels
        print(f"调整采样点数为: {possible_samples}")
        num_samples = possible_samples
    
    waveform_data = waveform_data[:num_channels * num_samples]
    waveform_data = waveform_data.reshape(num_samples, num_channels).T
    
    # 应用灵敏度
    scaled_data = {}
    for i, (channel, sensitivity) in enumerate(zip(channels, sensitivities)):
        scaled_data[channel] = waveform_data[i] * sensitivity
        print(f"\n导联 {channel} 数据统计:")
        print(f"  原始范围: [{np.min(waveform_data[i])}, {np.max(waveform_data[i])}]")
        print(f"  缩放后范围: [{np.min(scaled_data[channel])}, {np.max(scaled_data[channel])}]")
        print(f"  均值: {np.mean(scaled_data[channel]):.2f}")
        print(f"  标准差: {np.std(scaled_data[channel]):.2f}")
    
    return scaled_data, channels, sensitivities

def plot_waveform_comparison(file1_path, file2_path, output_dir):
    """比较两个DICOM文件中的波形数据"""
    # 读取数据
    data1, channels1, sens1 = read_waveform_data(file1_path)
    print("\n" + "="*50 + "\n")
    data2, channels2, sens2 = read_waveform_data(file2_path)
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 为每个导联创建对比图
    common_leads = set(channels1) & set(channels2)
    if not common_leads:
        print("错误：两个文件没有共同的导联")
        return
        
    print(f"\n共同的导联: {common_leads}")
    
    for lead in common_leads:
        plt.figure(figsize=(15, 6))
        
        # 绘制波形
        plt.subplot(2, 1, 1)
        plt.plot(data1[lead], label=f'{os.path.basename(file1_path)}')
        plt.plot(data2[lead], label=f'{os.path.basename(file2_path)}')
        plt.title(f'Lead {lead} Waveform Comparison')
        plt.grid(True)
        plt.legend()
        
        # 绘制差异
        plt.subplot(2, 1, 2)
        # 确保两个信号长度相同
        min_len = min(len(data1[lead]), len(data2[lead]))
        diff = data1[lead][:min_len] - data2[lead][:min_len]
        plt.plot(diff, 'r', label='Difference')
        plt.title(f'Difference (file1 - file2)')
        plt.grid(True)
        plt.legend()
        
        # 保存图片
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, f'{lead}_comparison.png'))
        plt.close()
        
        # 打印统计信息
        print(f"\n导联 {lead} 对比统计信息:")
        print(f"文件1 - 范围: [{np.min(data1[lead]):.2f}, {np.max(data1[lead]):.2f}], "
              f"均值: {np.mean(data1[lead]):.2f}, 标准差: {np.std(data1[lead]):.2f}")
        print(f"文件2 - 范围: [{np.min(data2[lead]):.2f}, {np.max(data2[lead]):.2f}], "
              f"均值: {np.mean(data2[lead]):.2f}, 标准差: {np.std(data2[lead]):.2f}")
        print(f"差异 - 范围: [{np.min(diff):.2f}, {np.max(diff):.2f}], "
              f"均值: {np.mean(diff):.2f}, 标准差: {np.std(diff):.2f}")

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) != 3:
        print("使用方法: python compare_waveforms.py <file1_path> <file2_path>")
        sys.exit(1)
        
    # 获取文件路径
    file1_path = sys.argv[1]
    file2_path = sys.argv[2]
    output_dir = 'dicom_files/waveform_comparison'
    
    # 检查文件是否存在
    if not os.path.exists(file1_path):
        print(f"错误：文件不存在: {file1_path}")
        sys.exit(1)
    if not os.path.exists(file2_path):
        print(f"错误：文件不存在: {file2_path}")
        sys.exit(1)
    
    # 比较波形
    plot_waveform_comparison(file1_path, file2_path, output_dir)
