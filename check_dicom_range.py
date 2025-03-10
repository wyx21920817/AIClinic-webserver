import pydicom
import numpy as np
import os

# 设置DICOM文件路径
dicom_dir = os.path.join(os.path.dirname(__file__), "dicom_files", "test")
dicom_file = os.path.join(dicom_dir, "image-00000.dcm")

print(f"查找DICOM文件: {dicom_file}")
if not os.path.exists(dicom_file):
    print(f"文件不存在: {dicom_file}")
    # 列出目录中的所有.dcm文件
    if os.path.exists(dicom_dir):
        dcm_files = [f for f in os.listdir(dicom_dir) if f.endswith('.dcm')]
        if dcm_files:
            print("\n找到以下DICOM文件:")
            for f in dcm_files:
                print(f"- {f}")
            # 使用第一个找到的文件
            dicom_file = os.path.join(dicom_dir, dcm_files[0])
            print(f"\n将使用第一个文件: {dcm_files[0]}")
        else:
            print(f"\n目录 {dicom_dir} 中没有找到DICOM文件")
            exit(1)
    else:
        print(f"\n目录不存在: {dicom_dir}")
        exit(1)

# 读取DICOM文件
ds = pydicom.dcmread(dicom_file)

# 获取波形数据
if hasattr(ds, 'WaveformSequence'):
    waveform_data = np.frombuffer(ds.WaveformSequence[0].WaveformData, dtype=np.int16)
    num_channels = ds.WaveformSequence[0].NumberOfWaveformChannels
    num_samples = ds.WaveformSequence[0].NumberOfWaveformSamples
    
    print(f"\n波形数据概况:")
    print(f"导联数量: {num_channels}")
    print(f"每个导联的采样点数: {num_samples}")
    
    # 重塑数据为二维数组 [samples, channels]
    waveform_data = waveform_data.reshape(num_samples, num_channels)
    
    # 分析每个导联的范围
    for i, channel in enumerate(ds.WaveformSequence[0].ChannelDefinitionSequence):
        lead_name = channel.ChannelLabel
        lead_data = waveform_data[:, i]
        print(f"\n导联 {lead_name}:")
        print(f"最小值: {lead_data.min()}")
        print(f"最大值: {lead_data.max()}")
        print(f"平均值: {lead_data.mean():.2f}")
        print(f"标准差: {lead_data.std():.2f}")
        
        # 转换为毫伏值
        mv_min = lead_data.min() / 6553.6
        mv_max = lead_data.max() / 6553.6
        print(f"毫伏范围: {mv_min:.2f}mV 到 {mv_max:.2f}mV")
else:
    print("未找到波形数据")
