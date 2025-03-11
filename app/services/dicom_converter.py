from app.services.waveform_extractor import WaveformExtractor
import os
import sys
import subprocess
import tempfile
from pathlib import Path
import logging
from threading import Lock
import imghdr
import json
import cv2
import numpy as np
from datetime import datetime
import uuid
from PIL import Image
import pydicom
from pydicom.uid import generate_uid
import shutil
import msvcrt
import matplotlib.pyplot as plt
from scipy import signal
from scipy.interpolate import interp1d
from io import BytesIO

from app.utils.logger_config import logger

class DicomConverter:
    def __init__(self, dcmtk_path=None):
        """
        初始化DICOM转换器
        :param dcmtk_path: dcmtk工具的路径，如果在PATH中则不需要指定
        """
        self.dcmtk_path = dcmtk_path or ""
        self._check_dcmtk()
        self.img2dcm_lock = Lock()
        
        # 设置默认的YOLOv7路径
        yolo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                "ecg-image-kit", "codes", "ecg-image-digitizer", "roi", "yolov7")
        if not os.path.exists(yolo_path):
            raise ValueError(f"YOLOv7路径不存在: {yolo_path}")
            
        # 初始化波形提取器
        self.waveform_extractor = WaveformExtractor(yolo_path)
        self.last_waveform_data = None

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

    def convert_to_dicom(self, input_file: Path, output_file: Path) -> bool:
        """
        Convert an image file to DICOM format
        """
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
            
            # 确保输出目录存在
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 创建DICOM数据集
            logger.info("创建DICOM数据集")
            ds = pydicom.Dataset()
            
            # 添加文件元信息
            file_meta = pydicom.Dataset()
            file_meta.FileMetaInformationGroupLength = 200
            file_meta.FileMetaInformationVersion = b'\x00\x01'
            file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.9.1.1'  # 12导联ECG波形存储
            file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
            file_meta.TransferSyntaxUID = '1.2.840.10008.1.2.1'  # 显式VR小端
            file_meta.ImplementationClassUID = '1.2.826.0.1.3680043.9.7433.1.1'
            file_meta.ImplementationVersionName = 'AIClinic'
            ds.file_meta = file_meta
            
            # 设置传输语法
            ds.is_little_endian = True
            ds.is_implicit_VR = False  # 使用显式VR
            
            # 添加必需的DICOM标签
            ds.SOPClassUID = file_meta.MediaStorageSOPClassUID  # 12导联ECG波形存储
            ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
            ds.StudyInstanceUID = pydicom.uid.generate_uid()
            ds.SeriesInstanceUID = pydicom.uid.generate_uid()
            
            # 设置其他必需的标签
            ds.Modality = 'ECG'
            ds.ConversionType = 'WSD'  # Waveform Storage Device
            ds.StudyDate = datetime.now().strftime('%Y%m%d')
            ds.StudyTime = datetime.now().strftime('%H%M%S')
            ds.ContentDate = ds.StudyDate
            ds.ContentTime = ds.StudyTime
            ds.AcquisitionDateTime = datetime.now().strftime('%Y%m%d%H%M%S')
            
            # 设置患者和研究信息（使用默认值）
            ds.PatientName = ''
            ds.PatientID = ''
            ds.PatientBirthDate = ''
            ds.PatientSex = ''
            ds.AccessionNumber = ''
            
            # 使用WaveformExtractor提取波形数据
            logger.info("开始提取波形数据...")
            try:
                # 使用已知的标签文件
                labels_path = os.path.join(
                    str(self.waveform_extractor.yolo_path),
                    "runs", "detect", "exp51", "labels", "test.txt"
                )
                logger.info(f"使用标签文件: {labels_path}")
                
                if not os.path.exists(labels_path):
                    logger.warning(f"标签文件不存在: {labels_path}，尝试运行检测...")
                    # 如果标签文件不存在，运行检测
                    waveforms = self.waveform_extractor.detect_and_extract(str(input_file))
                else:
                    # 如果标签文件存在，直接使用
                    waveforms = self.waveform_extractor.detect_and_extract(str(input_file), labels_path)
                if not waveforms:
                    logger.error("WaveformExtractor返回空的波形数据")
                    raise ValueError("无法提取波形数据")
                logger.info(f"成功提取波形数据，包含导联: {list(waveforms.keys())}")
                
                # 保存图片到服务器
                save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dicom_files", "test")
                os.makedirs(save_dir, exist_ok=True)
                save_path = os.path.join(save_dir, os.path.basename(input_file))
                shutil.copy2(str(input_file), save_path)
                logger.info(f"已保存图片到: {save_path}")
                
                # 收集每个导联的数据
                all_leads_data = []
                lead_order = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
                samples_per_lead = None
                
                # 先收集所有导联的数据到一个字典中
                lead_data_dict = {}
                for lead in lead_order:
                    if lead in waveforms:
                        # 获取当前导联的数据并保持原样
                        lead_data = waveforms[lead]
                        
                        # 只保留中间的4/5数据
                        total_points = len(lead_data)
                        start_idx = total_points // 10  # 跳过前1/10
                        end_idx = total_points - total_points // 10  # 跳过后1/10
                        lead_data = lead_data[start_idx:end_idx]
                        
                        # 使用标准ECG数字化转换，使用较小的转换因子
                        lead_data = (lead_data * 655 / 2).astype(np.int16)
                        
                        # 记录导联数据的一些基本信息
                        logger.info(f"导联 {lead} 数据: 长度={len(lead_data)}, 最小值={lead_data.min()}, 最大值={lead_data.max()}")
                        logger.info(f"导联 {lead} 前10个点: {lead_data[:10]}")
                        
                        if samples_per_lead is None:
                            samples_per_lead = len(lead_data)
                        elif len(lead_data) != samples_per_lead:
                            raise ValueError(f"导联 {lead} 的采样点数 ({len(lead_data)})。5 与其他导联不同 ({samples_per_lead})")
                        
                        # 保存到字典中
                        lead_data_dict[lead] = lead_data
                        
                    else:
                        logger.error(f"缺少导联数据: {lead}")
                        raise ValueError(f"缺少导联 {lead} 的数据")
                
                # 按照每个采样点包含所有导联的数据的方式重新组织数据
                all_leads_data = np.zeros((samples_per_lead, len(lead_order)), dtype=np.int16)
                for i, lead in enumerate(lead_order):
                    all_leads_data[:, i] = lead_data_dict[lead]
                
                # 将数据展平成一维数组，确保使用正确的字节序（行优先顺序）
                all_leads_data = all_leads_data.ravel(order='C')
                logger.info(f"完整波形数据: 形状={all_leads_data.shape}, 长度={len(all_leads_data)}")
                logger.info(f"波形数据统计: 最小值={all_leads_data.min()}, 最大值={all_leads_data.max()}, 均值={all_leads_data.mean():.3f}")
                logger.info(f"波形数据前100个点: {all_leads_data[:100]}")
                
                # 创建波形序列
                ds.WaveformSequence = [pydicom.Dataset()]
                
                # 设置波形序列
                waveform = ds.WaveformSequence[0]
                waveform.WaveformOriginality = 'ORIGINAL'
                waveform.NumberOfWaveformChannels = len(lead_order)
                waveform.NumberOfWaveformSamples = samples_per_lead
                waveform.SamplingFrequency = 500  # Hz
                waveform.WaveformBitsAllocated = 16
                waveform.WaveformBitsStored = 16
                waveform.WaveformSampleInterpretation = 'SS'  # 有符号整数
                waveform.ChannelDefinitionSequence = []
                
                # 为每个导联创建通道定义
                for i, lead in enumerate(lead_order):
                    channel = pydicom.Dataset()
                    channel.WaveformChannelNumber = i + 1
                    channel.ChannelLabel = lead
                    channel.ChannelSourceSequence = [pydicom.Dataset()]
                    source = channel.ChannelSourceSequence[0]
                    source.CodeValue = f'5.6.3-9-{i+1}'  # SCPECG标准代码
                    source.CodingSchemeDesignator = 'SCPECG'
                    source.CodingSchemeVersion = '1.3'
                    source.CodeMeaning = f'Lead {lead}'
                    
                    # 设置通道属性，使用正确的单位和缩放
                    channel.ChannelSensitivity = 0.00152587890625  # 1/6553.6 mV per unit
                    channel.ChannelSensitivityUnitsSequence = [pydicom.Dataset()]
                    units = channel.ChannelSensitivityUnitsSequence[0]
                    units.CodeValue = 'mV'  # millivolt
                    units.CodingSchemeDesignator = 'UCUM'
                    units.CodingSchemeVersion = '1.4'
                    units.CodeMeaning = 'millivolt'
                    
                    # 设置其他必要的通道属性
                    channel.ChannelSensitivityCorrectionFactor = 1.0
                    channel.ChannelBaseline = 0
                    channel.ChannelSampleSkew = 0
                    channel.WaveformBitsStored = 16
                    channel.FilterLowFrequency = 0.16  # 标准ECG低频截止
                    channel.FilterHighFrequency = 150.0  # 标准ECG高频截止
                    
                    waveform.ChannelDefinitionSequence.append(channel)
                
                # 添加波形数据
                ds.WaveformSequence[0].WaveformData = all_leads_data.tobytes()
                
                # 保存DICOM文件
                logger.info(f"开始保存DICOM文件: {output_file}")
                ds.save_as(str(output_file), write_like_original=False)
                
                # 检查输出文件是否存在且大小合理
                if output_file.exists():
                    output_size = output_file.stat().st_size
                    logger.info(f"DICOM文件已生成: {output_file} (大小: {output_size} bytes)")
                else:
                    logger.error("DICOM文件未生成")
                    raise Exception("DICOM文件未生成")
                
                return True
                
            except Exception as e:
                logger.error(f"提取波形数据时出错: {str(e)}")
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")
                raise ValueError(f"提取波形数据失败: {str(e)}")
            
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
