import os
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
import uuid
import numpy as np
from PIL import Image
import pydicom
from pydicom.uid import generate_uid
import shutil
import msvcrt
from app.utils.logger_config import logger
from threading import Lock
import imghdr

class DicomConverter:
    def __init__(self, dcmtk_path=None):
        """
        初始化DICOM转换器
        :param dcmtk_path: dcmtk工具的路径，如果在PATH中则不需要指定
        """
        self.dcmtk_path = dcmtk_path or ""
        self._check_dcmtk()
        self.img2dcm_lock = Lock()

    def _check_dcmtk(self):
        """检查dcmtk是否可用"""
        try:
            result = subprocess.run(['img2dcm', '--version'], 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE)
            if result.returncode != 0:
                raise RuntimeError("dcmtk not found in PATH")
        except FileNotFoundError:
            raise RuntimeError("dcmtk not found in PATH")

    def _detect_image_type(self, file_path: Path) -> str:
        """
        检测文件的真实类型
        :param file_path: 文件路径
        :return: 文件类型
        """
        logger.debug(f"Attempting to detect file type for: {file_path}")
        
        # 检查文件是否存在且不为空
        if not file_path.exists():
            logger.error(f"File does not exist: {file_path}")
            raise ValueError("File does not exist")
        if file_path.stat().st_size == 0:
            logger.error(f"File is empty: {file_path}")
            raise ValueError("File is empty")
            
        # 首先尝试使用imghdr检测
        img_type = imghdr.what(str(file_path))
        if img_type:
            logger.debug(f"File type detected by imghdr: {img_type}")
            return img_type

        # 如果imghdr无法检测，尝试用PIL打开
        try:
            with Image.open(file_path) as img:
                format_type = img.format.lower()
                logger.debug(f"File type detected by PIL: {format_type}")
                return format_type
        except Exception as e:
            logger.debug(f"PIL detection failed: {str(e)}")

        # 如果还是无法检测，尝试读取文件头
        try:
            with open(file_path, 'rb') as f:
                header = f.read(12)  # 读取更多字节以支持更多格式
                logger.debug(f"File header (hex): {header.hex()}")
                
                # 检查常见的文件头标识
                if header.startswith(b'\x89PNG\r\n\x1a\n'):
                    return 'png'
                elif header.startswith(b'\xff\xd8'):
                    return 'jpeg'
                elif header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):
                    return 'gif'
                elif header.startswith(b'BM'):
                    return 'bmp'
                elif header.startswith(b'\x49\x49') or header.startswith(b'\x4d\x4d'):
                    return 'tiff'
                elif header.startswith(b'RIFF') and header[8:12] == b'WEBP':
                    return 'webp'
                elif header.startswith(b'\x00\x00\x01\x00'):
                    return 'ico'
                # RAW格式检测
                elif any(header.startswith(sig) for sig in [b'II*\x00', b'MM\x00*']):
                    return 'raw'
                # DICOM格式检测
                elif header.startswith(b'DICM') or (len(header) > 128 and header[128:132] == b'DICM'):
                    return 'dcm'
                
                logger.debug("Attempting to detect format based on file extension")
                # 如果文件头检测失败，尝试使用文件扩展名
                ext = file_path.suffix.lower()
                if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico', '.raw', '.dcm']:
                    logger.debug(f"Using file extension: {ext[1:]}")
                    return ext[1:]
                    
        except Exception as e:
            logger.error(f"Error reading file header: {str(e)}")
            
        # 如果所有方法都失败了，记录更多信息以帮助调试
        logger.error(f"File detection failed for {file_path}")
        logger.error(f"File size: {file_path.stat().st_size} bytes")
        logger.error(f"File extension: {file_path.suffix}")
        
        raise ValueError("Unsupported or unrecognized image format")

    def _extract_waveform_data(self, ds):
        """从DICOM数据集中提取波形数据"""
        try:
            if hasattr(ds, 'WaveformSequence'):
                logger.info("找到波形数据")
                return ds.WaveformSequence
            else:
                logger.warning("未找到波形数据")
                return None
        except Exception as e:
            logger.error(f"提取波形数据失败: {str(e)}")
            return None

    def _create_dicom_metadata(self):
        """创建基本的DICOM元数据"""
        # 创建文件元信息数据集
        file_meta = pydicom.Dataset()
        file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.9.1.1'  # 12-lead ECG Waveform Storage
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.ImplementationClassUID = generate_uid()
        file_meta.TransferSyntaxUID = '1.2.840.10008.1.2.1'  # Explicit VR Little Endian
        
        # 创建数据集
        ds = pydicom.FileDataset(None, {}, file_meta=file_meta, preamble=b"\0" * 128)
        
        # 添加必需的元素
        ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        ds.StudyInstanceUID = generate_uid()
        ds.SeriesInstanceUID = generate_uid()
        
        # 设置日期和时间
        dt = datetime.now()
        ds.ContentDate = dt.strftime('%Y%m%d')
        ds.ContentTime = dt.strftime('%H%M%S.%f')
        ds.StudyDate = dt.strftime('%Y%m%d')  # 确保设置StudyDate
        ds.StudyTime = dt.strftime('%H%M%S.%f')
        
        # ECG特定的标签
        ds.Modality = 'ECG'
        ds.PatientName = 'ANONYMOUS'
        ds.PatientID = str(uuid.uuid4())
        ds.PatientBirthDate = ''
        ds.PatientSex = ''
        ds.AccessionNumber = ''
        
        # Waveform Sequence
        ds.WaveformSequence = [pydicom.Dataset()]
        waveform = ds.WaveformSequence[0]
        waveform.WaveformOriginality = 'ORIGINAL'
        waveform.NumberOfWaveformChannels = 12
        waveform.NumberOfWaveformSamples = 5000  # 示例值，需要根据实际数据调整
        waveform.SamplingFrequency = 500  # Hz
        waveform.WaveformBitsAllocated = 16  # 设置位深度
        waveform.WaveformSampleInterpretation = 'SS'  # 有符号16位整数
        waveform.ChannelDefinitionSequence = []
        
        # 为每个导联创建通道定义
        leads = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
        for i, lead in enumerate(leads):
            channel = pydicom.Dataset()
            channel.WaveformChannelNumber = i + 1
            channel.ChannelLabel = lead
            channel.ChannelSourceSequence = [pydicom.Dataset()]
            channel.ChannelSourceSequence[0].CodeValue = lead
            channel.ChannelSourceSequence[0].CodingSchemeDesignator = 'MDC'
            channel.ChannelSourceSequence[0].CodeMeaning = f'Lead {lead}'
            channel.ChannelSensitivity = 1.0
            channel.ChannelSensitivityUnitsSequence = [pydicom.Dataset()]
            channel.ChannelSensitivityUnitsSequence[0].CodeValue = 'mV'
            channel.ChannelSensitivityUnitsSequence[0].CodingSchemeDesignator = 'UCUM'
            channel.ChannelSensitivityUnitsSequence[0].CodeMeaning = 'millivolt'
            waveform.ChannelDefinitionSequence.append(channel)
        
        return ds

    def convert_to_dicom(self, input_file: Path, output_file: Path) -> bool:
        """Convert an image file to DICOM format"""
        try:
            logger.info(f"开始转换文件: {input_file} -> {output_file}")
            
            # 检测文件类型
            img_type = self._detect_image_type(input_file)
            logger.debug(f"文件类型: {img_type}")
            
            # 如果输入文件是DICOM文件
            if img_type == 'dcm':
                try:
                    # 读取原始DICOM文件
                    original_ds = pydicom.dcmread(str(input_file))
                    logger.info("成功读取DICOM文件")
                    
                    # 提取波形数据
                    waveform_seq = self._extract_waveform_data(original_ds)
                    if waveform_seq:
                        # 如果有波形数据，直接复制文件
                        logger.info("复制带有波形数据的DICOM文件")
                        shutil.copy2(input_file, output_file)
                        return True
                    else:
                        logger.warning("DICOM文件中没有波形数据")
                except Exception as e:
                    logger.error(f"处理DICOM文件失败: {str(e)}")
                    raise
            
            # 如果是图像文件，使用图像转换逻辑
            logger.info("使用图像转换逻辑")
            with Image.open(input_file) as img:
                # 转换为灰度图
                img_gray = img.convert('L')
                img_array = np.array(img_gray)
                
                # 创建DICOM数据集
                ds = self._create_dicom_metadata()
                
                # 设置波形数据
                num_samples = img_array.shape[1]  # 使用图像宽度作为采样点数
                ds.WaveformSequence[0].NumberOfWaveformSamples = num_samples
                
                # 创建波形数据
                waveform_data = []
                for i in range(12):  # 12个导联
                    # 从图像不同行采样数据
                    row = int(i * img_array.shape[0] / 12)
                    channel_data = img_array[row, :].astype(np.int16)  # 使用16位整数
                    # 归一化到合理的mV范围 (-5mV to +5mV)
                    channel_data = ((channel_data - 128) * 10).astype(np.int16)  # 转换为整数值
                    waveform_data.extend(channel_data)
                
                # 将波形数据添加到DICOM数据集
                ds.WaveformSequence[0].WaveformData = bytes(np.array(waveform_data, dtype=np.int16).tobytes())
                
                # 保存DICOM文件
                ds.save_as(str(output_file), write_like_original=False)
                
                # 检查输出文件是否存在且大小合理
                if output_file.exists():
                    output_size = output_file.stat().st_size
                    logger.info(f"DICOM文件已生成: {output_file} (大小: {output_size} bytes)")
                else:
                    raise Exception("DICOM文件未生成")
            
            return True
            
        except Exception as e:
            logger.error(f"转换失败: {str(e)}")
            raise

    def process_ct_scan(self, input_file: Path, output_dir: Path) -> list[Path]:
        """
        处理CT扫描文件，转换为DICOM系列
        :param input_file: 输入文件路径
        :param output_dir: 输出目录
        :return: 生成的DICOM文件路径列表
        """
        # 确保输出目录存在
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 检测文件类型并读取图像
        try:
            img_type = self._detect_image_type(input_file)
            # 直接处理单张图片
            output_file = output_dir / f'{input_file.stem}.dcm'
            success = self.convert_to_dicom(input_file, output_file)
            if success and output_file.exists():
                return [output_file]
            else:
                raise RuntimeError("Failed to convert image to DICOM")
            
        except Exception as e:
            raise RuntimeError(f"Error processing image: {str(e)}")
