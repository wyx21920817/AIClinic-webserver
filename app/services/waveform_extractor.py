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
        Initialize waveform extractor
        
        Args:
            yolo_path: Path to YOLOv7 detector
        """
        logger.info(f"Initializing WaveformExtractor, YOLOv7 path: {yolo_path}")
        self.yolo_path = Path(yolo_path)
        if not self.yolo_path.exists():
            logger.error(f"YOLOv7 path does not exist: {yolo_path}")
            raise ValueError(f"YOLOv7 path does not exist: {yolo_path}")
            
        self.detect_script = self.yolo_path / "detect.py"
        if not self.detect_script.exists():
            logger.error(f"detect.py does not exist: {self.detect_script}")
            raise ValueError(f"detect.py does not exist: {self.detect_script}")
            
        project_root = Path(__file__).parent.parent.parent
        self.weights = project_root / "models" / "best.pt"
        if not self.weights.exists():
            logger.error(f"Model weights file does not exist: {self.weights}")
            raise ValueError(f"Model weights file does not exist: {self.weights}")
        
        logger.info("WaveformExtractor initialized successfully")
    
    def detect_and_extract(self, image_path, labels_path=None, use_min_length=True):
        """
        Detect lead positions and extract waveform data from ECG image
        
        Args:
            image_path: Path to ECG image
            labels_path: Optional, path to existing label file. If provided, uses this file directly without detection
            use_min_length: Whether to use shortest lead length as reference, default True
            
        Returns:
            dict: Mapping of lead names to waveform data
        """
        logger.info(f"Starting to process image: {image_path}")
        
        # Ensure image exists
        if not os.path.exists(image_path):
            logger.error(f"Image file does not exist: {image_path}")
            raise ValueError(f"Image file does not exist: {image_path}")
        
        # If no label file provided, run detection
        if labels_path is None:
            logger.info("No label file provided, starting detection...")
            
            # Get task_id from image path
            task_id = Path(image_path).parent.name
            project_root = Path(__file__).parent.parent.parent
            output_dir = project_root / "dicom_files" / task_id / "detect"
            
            if output_dir.exists():
                shutil.rmtree(str(output_dir))
            output_dir.parent.mkdir(parents=True, exist_ok=True)
            
            # Run YOLOv7 detection
            cmd = [
                "python", str(self.detect_script),
                "--weights", str(self.weights),
                "--conf-thres", "0.25",
                "--source", image_path,
                "--save-txt",  # Save label file
                "--project", str(output_dir.parent),  # Set output directory to task_id directory
                "--name", "detect",  # Output subdirectory name
                "--exist-ok"  # Overwrite if directory exists
            ]
            
            logger.info(f"Executing detection command: {' '.join(cmd)}")
            try:
                result = subprocess.run(cmd, cwd=str(self.yolo_path), capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"Detection failed: {result.stderr}")
                    raise RuntimeError(f"Detection failed: {result.stderr}")
                logger.info(f"Detection output: {result.stdout}")                    
            except Exception as e:
                logger.error(f"Detection failed: {str(e)}")
                raise RuntimeError(f"Detection failed: {str(e)}")
            
            # Parse detection results
            labels_path = output_dir / "labels" / Path(image_path).name.replace(Path(image_path).suffix, ".txt")
            logger.info(f"Detection result file: {labels_path}")
            
            if not labels_path.exists():
                logger.error(f"Detection result file does not exist: {labels_path}")
                raise RuntimeError(f"Detection result file does not exist: {labels_path}")
        else:
            logger.info(f"Using provided label file: {labels_path}")
            if not os.path.exists(labels_path):
                logger.error(f"Label file does not exist: {labels_path}")
                raise ValueError(f"Label file does not exist: {labels_path}")
        
        # Extract waveforms
        logger.info("Starting waveform extraction...")
        try:
            waveforms = plot_all_leads(str(image_path), str(labels_path), use_min_length=use_min_length)
            if waveforms:
                logger.info(f"Successfully extracted waveforms from {len(waveforms)} leads")
                return waveforms
            else:
                logger.error("Waveform extraction failed")
                raise RuntimeError("Waveform extraction failed")
        except Exception as e:
            logger.error(f"Error during waveform extraction: {str(e)}")
            raise

    def extract_waveforms(self, image_path, labels_path, use_min_length=True):
        """
        Extract waveform data for all leads from ECG image
        
        Args:
            image_path: Path to ECG image
            labels_path: Path to YOLO detection result label file
            use_min_length: Whether to use shortest lead length as reference, default True
            
        Returns:
            dict: Mapping of lead names to waveform data
        """
        logger.info(f"Calling plot_all_leads to extract waveforms, image: {image_path}, labels: {labels_path}")
        try:
            result = plot_all_leads(image_path, labels_path, use_min_length=use_min_length)
            if result:
                logger.info("plot_all_leads executed successfully")
            else:
                logger.error("plot_all_leads returned empty result")
            return result
        except Exception as e:
            logger.error(f"plot_all_leads execution failed: {str(e)}")
            raise
