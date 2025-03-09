import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
import pydicom
from pathlib import Path

def print_dataset(dataset, indent=0):
    """递归打印DICOM数据集的结构"""
    for data_element in dataset:
        if data_element.VR == "SQ":  # 序列
            print(" " * indent + f"{data_element.name} [{data_element.tag}]:")
            for i, item in enumerate(data_element.value):
                print(" " * (indent + 2) + f"Item {i}:")
                print_dataset(item, indent + 4)
        else:
            print(" " * indent + f"{data_element.name} [{data_element.tag}]: {repr(data_element.value)}")

def analyze_waveform_shape(data, num_channels, num_samples):
    """分析波形数据的形状和分布"""
    try:
        # 重塑数据为(通道数, 采样点数)
        data = data.reshape(num_channels, num_samples)
        
        # 计算每个通道的统计信息
        stats = {
            'mean': np.mean(data, axis=1),
            'std': np.std(data, axis=1),
            'min': np.min(data, axis=1),
            'max': np.max(data, axis=1),
            'range': np.ptp(data, axis=1),
            'zero_crossings': np.sum(np.diff(np.signbit(data), axis=1) != 0, axis=1)
        }
        
        return stats, data
    except Exception as e:
        print(f"分析波形形状时出错: {str(e)}")
        return None, None

def plot_waveforms(data, num_channels, num_samples, title, output_file):
    """绘制波形图"""
    try:
        # 重塑数据
        data = data.reshape(num_channels, num_samples)
        
        # 创建图形
        plt.figure(figsize=(15, 10))
        leads = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
        
        # 绘制前6个导联
        for i in range(6):
            plt.subplot(2, 3, i+1)
            plt.plot(data[i])
            plt.title(f'Lead {leads[i]}')
            plt.grid(True)
        
        plt.suptitle(title)
        plt.tight_layout()
        plt.savefig(output_file)
        plt.close()
        
        print(f"波形图已保存到: {output_file}")
    except Exception as e:
        print(f"绘制波形图时出错: {str(e)}")

def analyze_waveform_data(dicom_file):
    """分析DICOM文件中的波形数据"""
    print(f"\n{'='*80}\n分析文件: {dicom_file}\n{'='*80}")
    
    # 读取DICOM文件
    try:
        ds = pydicom.dcmread(str(dicom_file))
        print("\nDICOM文件基本信息:")
        print(f"传输语法: {ds.file_meta.TransferSyntaxUID}")
        print(f"SOP类: {ds.file_meta.MediaStorageSOPClassUID}")
    except Exception as e:
        print(f"读取DICOM文件失败: {str(e)}")
        return None
    
    # 检查是否包含波形数据
    if not hasattr(ds, 'WaveformSequence'):
        print("文件不包含波形数据")
        return None
    
    # 获取波形序列
    waveform = ds.WaveformSequence[0]
    
    # 获取基本参数
    num_channels = waveform.NumberOfWaveformChannels
    num_samples = waveform.NumberOfWaveformSamples
    bits_allocated = getattr(waveform, 'WaveformBitsAllocated', None)
    bits_stored = getattr(waveform, 'WaveformBitsStored', None)
    sample_interpretation = getattr(waveform, 'WaveformSampleInterpretation', None)
    
    print("\n基本参数:")
    print(f"通道数: {num_channels}")
    print(f"采样点数: {num_samples}")
    print(f"分配的位数: {bits_allocated}")
    print(f"存储的位数: {bits_stored}")
    print(f"采样解释: {sample_interpretation}")
    
    # 检查通道定义
    if hasattr(waveform, 'ChannelDefinitionSequence'):
        channel_seq = waveform.ChannelDefinitionSequence
        print(f"\n通道定义分析:")
        for i, channel in enumerate(channel_seq):
            print(f"\n通道 {i+1} ({channel.ChannelLabel}):")
            sensitivity = getattr(channel, 'ChannelSensitivity', 'N/A')
            bits_stored = getattr(channel, 'WaveformBitsStored', 'N/A')
            baseline = getattr(channel, 'ChannelBaseline', 'N/A')
            low_freq = getattr(channel, 'FilterLowFrequency', 'N/A')
            high_freq = getattr(channel, 'FilterHighFrequency', 'N/A')
            
            print(f"  灵敏度: {sensitivity}")
            print(f"  存储位数: {bits_stored}")
            print(f"  基线: {baseline}")
            print(f"  滤波范围: {low_freq} - {high_freq} Hz")
    
    # 分析波形数据
    if hasattr(waveform, 'WaveformData'):
        waveform_data = waveform.WaveformData
        data_size = len(waveform_data)
        expected_size = num_channels * num_samples * (bits_allocated or 16) // 8
        
        print(f"\n波形数据分析:")
        print(f"预期数据大小: {expected_size} 字节")
        print(f"实际数据大小: {data_size} 字节")
        
        if data_size != expected_size:
            print(f"警告: 数据大小不匹配!")
        
        try:
            # 解析数据
            raw_data = np.frombuffer(waveform_data, dtype=np.int16)
            stats, shaped_data = analyze_waveform_shape(raw_data, num_channels, num_samples)
            
            if stats:
                print("\n各导联统计信息:")
                leads = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
                for i, lead in enumerate(leads):
                    print(f"\n导联 {lead}:")
                    print(f"  平均值: {stats['mean'][i]:.2f}")
                    print(f"  标准差: {stats['std'][i]:.2f}")
                    print(f"  范围: [{stats['min'][i]}, {stats['max'][i]}]")
                    print(f"  过零点数: {stats['zero_crossings'][i]}")
                
                # 绘制波形图
                output_file = str(Path(dicom_file).with_suffix('.png'))
                plot_waveforms(raw_data, num_channels, num_samples, 
                             f"ECG Waveforms - {Path(dicom_file).name}", output_file)
            
        except Exception as e:
            print(f"分析波形数据时出错: {str(e)}")
            return None
        
        return {
            'bits_allocated': bits_allocated,
            'bits_stored': bits_stored,
            'sample_interpretation': sample_interpretation,
            'data_size': data_size,
            'expected_size': expected_size,
            'num_channels': num_channels,
            'num_samples': num_samples,
            'stats': stats if 'stats' in locals() else None
        }
    
    return None

def compare_waveforms(file1, file2):
    """比较两个DICOM文件的波形数据"""
    print("\n比较两个DICOM文件的波形数据:")
    
    # 分析两个文件
    result1 = analyze_waveform_data(file1)
    result2 = analyze_waveform_data(file2)
    
    if result1 and result2:
        print("\n关键属性比较:")
        attrs = [
            ('bits_allocated', 'WaveformBitsAllocated'),
            ('bits_stored', 'WaveformBitsStored'),
            ('sample_interpretation', 'WaveformSampleInterpretation'),
            ('num_channels', '通道数'),
            ('num_samples', '采样点数'),
            ('data_size', '数据大小'),
            ('expected_size', '预期大小')
        ]
        
        print("\n{:<25} {:<20} {:<20} {:<10}".format('属性', '文件1', '文件2', '是否匹配'))
        print("-" * 75)
        
        for key, name in attrs:
            val1 = result1.get(key)
            val2 = result2.get(key)
            match = "✓" if val1 == val2 else "✗"
            print("{:<25} {:<20} {:<20} {:<10}".format(
                name, str(val1), str(val2), match
            ))
        
        # 比较统计信息
        if result1.get('stats') and result2.get('stats'):
            print("\n波形统计信息比较:")
            leads = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
            
            print("\n{:<6} {:<20} {:<20} {:<20}".format('导联', '范围(文件1)', '范围(文件2)', '过零点数比'))
            print("-" * 70)
            
            for i, lead in enumerate(leads):
                range1 = result1['stats']['range'][i]
                range2 = result2['stats']['range'][i]
                zeros1 = result1['stats']['zero_crossings'][i]
                zeros2 = result2['stats']['zero_crossings'][i]
                
                print("{:<6} [{:>6.1f}, {:>6.1f}] {:>6} [{:>6.1f}, {:>6.1f}] {:>6} {:>10.2f}".format(
                    lead,
                    result1['stats']['min'][i], result1['stats']['max'][i],
                    zeros1,
                    result2['stats']['min'][i], result2['stats']['max'][i],
                    zeros2,
                    zeros1/zeros2 if zeros2 != 0 else float('inf')
                ))

if __name__ == '__main__':
    file1 = r"D:\study\csproject\AIClinic\AIClinic-webserver\tests\1.dcm"
    file2 = r"D:\study\csproject\AIClinic\AIClinic-webserver\tests\2.dcm"
    compare_waveforms(file1, file2)
