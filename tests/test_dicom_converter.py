import unittest
import os
from pathlib import Path
import shutil
import tempfile
from PIL import Image
import io
from app.services.dicom_converter import DicomConverter
import urllib.request

class TestDicomConverter(unittest.TestCase):
    def setUp(self):
        """测试前的准备工作"""
        self.converter = DicomConverter()
        self.test_dir = Path(tempfile.mkdtemp())
        
        # 创建一个测试图像
        self.test_image = self.test_dir / "test.png"
        self.ecg_image = self.test_dir / "anonymous_ecg_3x4.png"
        
        # 创建测试图像
        self._create_test_image()
        
        # 复制ECG图像到测试目录
        shutil.copy("anonymous_ecg_3x4.png", self.ecg_image)

    def tearDown(self):
        """测试后的清理工作"""
        shutil.rmtree(self.test_dir)

    def _create_test_image(self):
        """创建一个简单的测试图像"""
        # 创建一个100x100的黑白测试图像
        img = Image.new('RGB', (100, 100), color='white')
        img.save(self.test_image)

    def test_detect_image_type(self):
        """测试图像类型检测功能"""
        img_type = self.converter._detect_image_type(self.test_image)
        self.assertEqual(img_type, 'png')

    def test_convert_to_dicom(self):
        """测试图像到DICOM的转换"""
        # 设置输出路径
        output_file = self.test_dir / "output.dcm"
        
        try:
            # 执行转换
            result = self.converter.convert_to_dicom(self.test_image, output_file)
            
            # 验证输出文件存在
            self.assertTrue(output_file.exists())
            
            # 验证输出文件大小不为0
            self.assertGreater(output_file.stat().st_size, 0)
            
            # 验证返回值是正确的Path对象
            self.assertEqual(result, output_file)
            
        except Exception as e:
            self.fail(f"转换失败，错误信息: {str(e)}")

    def test_convert_invalid_file(self):
        """测试处理无效文件的情况"""
        # 创建一个无效的图像文件
        invalid_file = self.test_dir / "invalid.png"
        with open(invalid_file, 'w') as f:
            f.write("This is not an image")

        # 验证是否正确抛出异常
        with self.assertRaises(Exception):
            self.converter.convert_to_dicom(invalid_file)

    def test_convert_from_url(self):
        """测试从URL下载并转换图像"""
        # 使用一个公开的测试图像URL
        test_url = "https://raw.githubusercontent.com/microsoft/vscode/main/resources/win32/code_150x150.png"
        
        try:
            # 设置输出路径
            output_file = self.test_dir / "output_from_url.dcm"
            
            # 下载并转换
            with urllib.request.urlopen(test_url) as response:
                temp_file = self.test_dir / "temp_image.png"
                with open(temp_file, 'wb') as f:
                    f.write(response.read())
                
                # 执行转换
                result = self.converter.convert_to_dicom(temp_file, output_file)
                
                # 验证输出文件存在
                self.assertTrue(output_file.exists())
                
                # 验证输出文件大小不为0
                self.assertGreater(output_file.stat().st_size, 0)
                
                # 验证返回值是正确的Path对象
                self.assertEqual(result, output_file)
                
        except Exception as e:
            self.fail(f"从URL转换失败，错误信息: {str(e)}")

    def test_convert_ecg(self):
        """测试转换ECG图像到DICOM格式"""
        try:
            # 设置输出路径
            output_file = self.test_dir / "ecg_output.dcm"
            
            # 执行转换
            result = self.converter.convert_to_dicom(
                self.ecg_image, 
                output_file,
                extra_tags={
                    'Modality': 'ECG',
                    'StudyDescription': 'ECG Study',
                    'SeriesDescription': 'ECG Series',
                    'PatientName': 'Anonymous',
                    'PatientID': '642341',
                    'PatientBirthDate': '19710123',
                    'PatientSex': 'F',
                    'StudyDate': '20130125',
                    'StudyTime': '095400',
                    'ContentDate': '20130125',
                    'ContentTime': '095400'
                }
            )
            
            # 验证输出文件存在
            self.assertTrue(output_file.exists())
            
            # 验证输出文件大小不为0
            self.assertGreater(output_file.stat().st_size, 0)
            
            # 验证返回值是正确的Path对象
            self.assertEqual(result, output_file)
            
        except Exception as e:
            self.fail(f"ECG转换失败，错误信息: {str(e)}")

if __name__ == '__main__':
    unittest.main()
