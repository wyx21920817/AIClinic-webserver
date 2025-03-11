import os
import subprocess
from pathlib import Path
from .waveform_extraction import plot_all_leads
import logging
import shutil

logger = logging.getLogger("AIClinic")

class WaveformExtractor:
    def __init__(self, yolo_path):
        """
        初始化波形提取器
        
        参数:
            yolo_path: YOLOv7检测器的路径
        """
        logger.info(f"初始化WaveformExtractor，YOLOv7路径: {yolo_path}")
        self.yolo_path = Path(yolo_path)
        if not self.yolo_path.exists():
            logger.error(f"YOLOv7路径不存在: {yolo_path}")
            raise ValueError(f"YOLOv7路径不存在: {yolo_path}")
            
        self.detect_script = self.yolo_path / "detect.py"
        if not self.detect_script.exists():
            logger.error(f"detect.py不存在: {self.detect_script}")
            raise ValueError(f"detect.py不存在: {self.detect_script}")
            
        project_root = Path(__file__).parent.parent.parent
        self.weights = project_root / "models" / "best.pt"
        if not self.weights.exists():
            logger.error(f"模型权重文件不存在: {self.weights}")
            raise ValueError(f"模型权重文件不存在: {self.weights}")
        
        logger.info("WaveformExtractor初始化成功")
    
    def detect_and_extract(self, image_path, labels_path=None, use_min_length=True):
        """
        从ECG图像中检测导联位置并提取波形数据
        
        参数:
            image_path: ECG图像的路径
            labels_path: 可选，已有的标签文件路径。如果提供，则直接使用该文件而不进行检测
            use_min_length: 是否使用最短导联长度作为参考，默认True
            
        返回:
            dict: 导联名称到波形数据的映射
        """
        logger.info(f"开始处理图像: {image_path}")
        
        # 确保图像存在
        if not os.path.exists(image_path):
            logger.error(f"图像文件不存在: {image_path}")
            raise ValueError(f"图像文件不存在: {image_path}")
        
        # 如果没有提供标签文件，则运行检测
        if labels_path is None:
            logger.info("未提供标签文件，开始运行检测...")
            
            # 从图像路径获取task_id
            task_id = Path(image_path).parent.name
            project_root = Path(__file__).parent.parent.parent
            output_dir = project_root / "dicom_files" / task_id / "detect"
            
            if output_dir.exists():
                shutil.rmtree(str(output_dir))
            output_dir.parent.mkdir(parents=True, exist_ok=True)
            
            # 运行YOLOv7检测
            cmd = [
                "python", str(self.detect_script),
                "--weights", str(self.weights),
                "--conf-thres", "0.25",
                "--source", image_path,
                "--save-txt",  # 保存标签文件
                "--project", str(output_dir.parent),  # 指定输出目录为task_id目录
                "--name", "detect",  # 输出子目录名
                "--exist-ok"  # 如果目录存在则覆盖
            ]
            
            logger.info(f"执行检测命令: {' '.join(cmd)}")
            try:
                result = subprocess.run(cmd, cwd=str(self.yolo_path), capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"检测失败: {result.stderr}")
                    raise RuntimeError(f"检测失败: {result.stderr}")
                logger.info(f"检测输出: {result.stdout}")
            except Exception as e:
                logger.error(f"检测失败: {str(e)}")
                raise RuntimeError(f"检测失败: {str(e)}")
            
            # 获取检测结果路径
            labels_path = output_dir / "labels" / Path(image_path).name.replace(Path(image_path).suffix, ".txt")
            logger.info(f"检测结果文件: {labels_path}")
            
            if not labels_path.exists():
                logger.error(f"检测结果文件不存在: {labels_path}")
                raise RuntimeError(f"检测结果文件不存在: {labels_path}")
        else:
            logger.info(f"使用提供的标签文件: {labels_path}")
            if not os.path.exists(labels_path):
                logger.error(f"标签文件不存在: {labels_path}")
                raise ValueError(f"标签文件不存在: {labels_path}")
        
        # 提取波形
        logger.info("开始提取波形...")
        try:
            waveforms = plot_all_leads(str(image_path), str(labels_path), use_min_length=use_min_length)
            if waveforms:
                logger.info(f"成功提取 {len(waveforms)} 个导联的波形")
                return waveforms
            else:
                logger.error("波形提取失败")
                raise RuntimeError("波形提取失败")
        except Exception as e:
            logger.error(f"波形提取过程出错: {str(e)}")
            raise

    def extract_waveforms(self, image_path, labels_path, use_min_length=True):
        """
        从ECG图像中提取所有导联的波形数据
        
        参数:
            image_path: ECG图像的路径
            labels_path: YOLO检测结果的标签文件路径
            use_min_length: 是否使用最短导联长度作为参考，默认True
            
        返回:
            dict: 导联名称到波形数据的映射
        """
        logger.info(f"调用plot_all_leads提取波形，图像: {image_path}，标签: {labels_path}")
        try:
            result = plot_all_leads(image_path, labels_path, use_min_length=use_min_length)
            if result:
                logger.info("plot_all_leads执行成功")
            else:
                logger.error("plot_all_leads返回空结果")
            return result
        except Exception as e:
            logger.error(f"plot_all_leads执行失败: {str(e)}")
            raise
