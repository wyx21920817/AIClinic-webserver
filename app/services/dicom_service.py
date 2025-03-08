from pathlib import Path
from pydicom import dcmread
from pynetdicom import AE, StoragePresentationContexts
from pynetdicom.sop_class import PatientRootQueryRetrieveInformationModelFind
from fastapi import HTTPException
from app.core.config import settings
from app.services.dicom_converter import DicomConverter
from app.utils.logger_config import logger

class DicomService:
    def __init__(self):
        self.converter = DicomConverter()

    def send_to_pacs(self, file_path: Path) -> bool:
        """Send a DICOM file to PACS server"""
        try:
            logger.info(f"Attempting to send file to PACS: {file_path}")
            ae = AE(ae_title=settings.AE_TITLE)
            ae.requested_contexts = StoragePresentationContexts
            logger.debug(f"Connecting to PACS server at {settings.PACS_HOST}:{settings.PACS_PORT}")
            assoc = ae.associate(settings.PACS_HOST, settings.PACS_PORT, ae_title=settings.PACS_AE_TITLE)
            
            if assoc.is_established:
                logger.debug("PACS connection established")
                dataset = dcmread(file_path)
                status = assoc.send_c_store(dataset)
                assoc.release()
                success = status.Status == 0
                logger.info(f"File sent to PACS: {'success' if success else 'failed'}")
                return success
            logger.error("Failed to establish PACS connection")
            return False
        except Exception as e:
            logger.error(f"Error sending to PACS: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to send to PACS: {str(e)}")

    def query_pacs(self, query_dataset):
        """Query PACS server for DICOM files"""
        logger.info("Starting PACS query")
        logger.debug(f"Query dataset: {query_dataset}")
        
        ae = AE(ae_title=settings.AE_TITLE)
        ae.add_requested_context(PatientRootQueryRetrieveInformationModelFind)
        
        try:
            logger.debug(f"Connecting to PACS server at {settings.PACS_HOST}:{settings.PACS_PORT}")
            assoc = ae.associate(settings.PACS_HOST, settings.PACS_PORT, ae_title=settings.PACS_AE_TITLE)
            
            if assoc.is_established:
                logger.debug("PACS connection established")
                responses = []
                for (status, dataset) in assoc.send_c_find(query_dataset, PatientRootQueryRetrieveInformationModelFind):
                    if status.Status == 0xFF00:  # Pending
                        logger.debug(f"Received dataset: {dataset}")
                        responses.append(dataset)
                assoc.release()
                logger.info(f"Query completed. Found {len(responses)} results")
                return responses
                
            logger.error("Failed to establish PACS connection")
            return []
            
        except Exception as e:
            logger.error(f"Error querying PACS: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to query PACS: {str(e)}")

    def convert_and_send(self, input_file: Path, output_dir: Path) -> tuple:
        """Convert file to DICOM and send to PACS"""
        try:
            logger.info(f"Converting file {input_file} to DICOM")
            # Convert to DICOM
            dicom_files = self.converter.process_ct_scan(input_file, output_dir)
            logger.info(f"Conversion completed. Generated {len(dicom_files)} DICOM files")
            
            # Send each file to PACS
            success_count = 0
            try:
                for dicom_file in dicom_files:
                    logger.debug(f"Sending DICOM file to PACS: {dicom_file}")
                    if self.send_to_pacs(dicom_file):
                        success_count += 1
            except Exception as e:
                logger.error(f"Error sending to PACS: {str(e)}")
                # 即使PACS发送失败，我们仍然返回已转换的文件
                
            logger.info(f"Sent {success_count} of {len(dicom_files)} files to PACS")
            return dicom_files, len(dicom_files)  # 返回转换成功的文件数，而不是PACS发送成功的数量
            
        except Exception as e:
            logger.error(f"Error in convert_and_send: {str(e)}")
            raise

dicom_service = DicomService()
