import unittest
import requests
import tempfile
import os
from pathlib import Path
import shutil
from PIL import Image

class TestConvertAPI(unittest.TestCase):
    def setUp(self):
        """测试前的准备工作"""
        self.base_url = "http://localhost:8000"
        self.test_dir = Path(__file__).parent / "test_data"
        self.test_image = self.test_dir / "anonymous_ecg_3x4.png"

    def tearDown(self):
        """测试后的清理工作"""
        pass

    def test_convert_endpoint(self):
        """测试/convert接口"""
        # 准备文件
        files = {
            'file': ('anonymous_ecg_3x4.png', open(self.test_image, 'rb'), 'image/png')
        }
        
        try:
            # 发送请求
            response = requests.post(f"{self.base_url}/convert", files=files)
            
            # 验证状态码
            self.assertEqual(response.status_code, 200, f"转换失败: {response.text}")
            
            # 验证返回的是DICOM文件
            self.assertTrue(response.content, "返回的文件为空")
            self.assertEqual(response.headers['Content-Type'], 'application/dicom', 
                         "返回的不是DICOM文件")
            
            # 保存DICOM文件以供检查
            output_file = Path(tempfile.gettempdir()) / "output.dcm"
            with open(output_file, 'wb') as f:
                f.write(response.content)
            
            # 验证输出文件大小不为0
            self.assertGreater(output_file.stat().st_size, 0)
            
        except Exception as e:
            self.fail(f"请求失败: {str(e)}")
        finally:
            # 关闭文件
            files['file'][1].close()

if __name__ == '__main__':
    unittest.main()
