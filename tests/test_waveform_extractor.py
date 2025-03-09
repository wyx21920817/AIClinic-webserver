import unittest
import os
import numpy as np
from app.services.waveform_extractor import WaveformExtractor

class TestWaveformExtractor(unittest.TestCase):
    def setUp(self):
        """测试前的准备工作"""
        # 设置YOLOv7路径
        self.yolo_path = "D:/study/csproject/AIClinic/AIClinic-webserver/ecg-image-kit/codes/ecg-image-digitizer/roi/yolov7"
        self.assertTrue(os.path.exists(self.yolo_path), f"YOLOv7路径不存在: {self.yolo_path}")
        
        # 设置测试图像和标签文件的路径
        self.image_path = os.path.join(self.yolo_path, "D:/study/csproject/AIClinic/AIClinic-webserver/ecg-image-kit/codes/ecg-image-digitizer/roi/yolov7/runs/detect/exp/test.png")
        self.labels_path = os.path.join(self.yolo_path, "D:/study/csproject/AIClinic/AIClinic-webserver/ecg-image-kit/codes/ecg-image-digitizer/roi/yolov7/runs/detect/exp/labels/test.txt")
        
        # 检查文件是否存在
        self.assertTrue(os.path.exists(self.image_path), f"测试图像不存在: {self.image_path}")
        self.assertTrue(os.path.exists(self.labels_path), f"标签文件不存在: {self.labels_path}")
        
        # 创建WaveformExtractor实例
        self.extractor = WaveformExtractor(self.yolo_path)        
    
    def test_detect_and_extract(self):
        """测试检测和波形提取的完整流程"""
        # 提取波形，使用已有的标签文件
        waveforms = self.extractor.detect_and_extract(self.image_path, self.labels_path)
        
        # 检查返回值是字典
        self.assertIsInstance(waveforms, dict)
        
        # 检查是否包含所有必要的导联
        expected_leads = {'I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6'}
        self.assertEqual(set(waveforms.keys()), expected_leads)
        
        # 检查每个导联的波形数据
        for lead_name, waveform in waveforms.items():
            # 检查波形数据是numpy数组
            self.assertIsInstance(waveform, np.ndarray)
            
            # 检查波形数据不为空
            self.assertGreater(len(waveform), 0)
            
            # 检查波形数据是一维的
            self.assertEqual(len(waveform.shape), 1)
            
            # 打印波形数据的基本信息
            print(f"\n{lead_name} 导联波形数据:")
            print(f"- 数据点数量: {len(waveform)}")
            print(f"- 数据范围: [{waveform.min():.2f}, {waveform.max():.2f}]")
            print(f"- 平均值: {waveform.mean():.2f}")
            print(f"- 标准差: {waveform.std():.2f}")
    
    def test_detect_and_extract_without_labels(self):
        """测试不提供标签文件时的检测和提取流程"""
        # 提取波形，不提供标签文件，让它自己运行检测
        waveforms = self.extractor.detect_and_extract(self.image_path)
        
        # 检查返回值是字典
        self.assertIsInstance(waveforms, dict)
        
        # 检查是否包含所有必要的导联
        expected_leads = {'I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6'}
        self.assertEqual(set(waveforms.keys()), expected_leads)
        



if __name__ == '__main__':
    unittest.main()
