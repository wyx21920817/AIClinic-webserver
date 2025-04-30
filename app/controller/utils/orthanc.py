import requests
import os
import json
import pydicom
from io import BytesIO
import numpy as np

ORTHANC_SERVER_URL = "http://54.79.224.136:8042"
ORTHANC_USERNAME = "orthanc"  # default username
ORTHANC_PASSWORD = "orthanc"  # default password

def upload_dicom_file(file_path):
    """
    Upload a DICOM file to the Orthanc server.
    
    Args:
        file_path (str): The path to the DICOM file to upload
        
    Returns:
        dict: Response from the server containing the ID of the uploaded instance
        or None if upload fails
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"DICOM file not found: {file_path}")
    
    try:
        with open(file_path, 'rb') as f:
            dicom_content = f.read()
            
        # Upload the DICOM file to Orthanc
        response = requests.post(
            f"{ORTHANC_SERVER_URL}/instances",
            auth=(ORTHANC_USERNAME, ORTHANC_PASSWORD),
            data=dicom_content,
            headers={'Content-Type': 'application/dicom'}
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error uploading DICOM file: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error uploading DICOM file: {str(e)}")
        return None

def upload_dicom_folder(folder_path):
    """
    Upload all DICOM files from a folder to the Orthanc server.
    
    Args:
        folder_path (str): Path to the folder containing DICOM files
        
    Returns:
        list: List of successful uploads (instance IDs)
    """
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"Folder not found: {folder_path}")
        
    successful_uploads = []
    
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(('.dcm', '.dicom')):
                file_path = os.path.join(root, file)
                result = upload_dicom_file(file_path)
                if result:
                    successful_uploads.append(result)
                    
    return successful_uploads

def get_instance(instance_id):
    """
    Get DICOM instance details from Orthanc server.
    
    Args:
        instance_id (str): The Orthanc instance ID
        
    Returns:
        dict: Instance details or None if not found
    """
    try:
        response = requests.get(
            f"{ORTHANC_SERVER_URL}/instances/{instance_id}",
            auth=(ORTHANC_USERNAME, ORTHANC_PASSWORD)
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error getting instance: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error getting instance: {str(e)}")
        return None

def get_instance_dicom(instance_id):
    """
    Get raw DICOM file data from Orthanc server.
    
    Args:
        instance_id (str): The Orthanc instance ID
        
    Returns:
        bytes: Raw DICOM file data or None if not found
    """
    try:
        response = requests.get(
            f"{ORTHANC_SERVER_URL}/instances/{instance_id}/file",
            auth=(ORTHANC_USERNAME, ORTHANC_PASSWORD)
        )
        
        if response.status_code == 200:
            return response.content
        else:
            print(f"Error getting DICOM file: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error getting DICOM file: {str(e)}")
        return None

def modify_instance_metadata(instance_id, metadata):
    """
    Modify instance metadata in Orthanc server.
    
    Args:
        instance_id (str): The Orthanc instance ID
        metadata (dict): Dictionary containing metadata to modify
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        response = requests.put(
            f"{ORTHANC_SERVER_URL}/instances/{instance_id}/metadata",
            auth=(ORTHANC_USERNAME, ORTHANC_PASSWORD),
            json=metadata
        )
        
        if response.status_code == 200:
            return True
        else:
            print(f"Error modifying instance metadata: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"Error modifying instance metadata: {str(e)}")
        return False

def delete_instance(instance_id):
    """
    Delete a DICOM instance from Orthanc server.
    
    Args:
        instance_id (str): The Orthanc instance ID
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        response = requests.delete(
            f"{ORTHANC_SERVER_URL}/instances/{instance_id}",
            auth=(ORTHANC_USERNAME, ORTHANC_PASSWORD)
        )
        
        if response.status_code == 200:
            return True
        else:
            print(f"Error deleting instance: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"Error deleting instance: {str(e)}")
        return False

def search_instances(query=None):
    """
    Search for DICOM instances in Orthanc server.
    
    Args:
        query (dict, optional): Query parameters for search
        
    Returns:
        list: List of matching instance IDs
    """
    try:
        if query:
            response = requests.post(
                f"{ORTHANC_SERVER_URL}/tools/find",
                auth=(ORTHANC_USERNAME, ORTHANC_PASSWORD),
                json=query
            )
        else:
            response = requests.get(
                f"{ORTHANC_SERVER_URL}/instances",
                auth=(ORTHANC_USERNAME, ORTHANC_PASSWORD)
            )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error searching instances: {response.status_code}")
            print(f"Response: {response.text}")
            return []
            
    except Exception as e:
        print(f"Error searching instances: {str(e)}")
        return []

def get_instance_tags(instance_id):
    """
    Get DICOM tags of an instance.
    
    Args:
        instance_id (str): The Orthanc instance ID
        
    Returns:
        dict: Dictionary containing DICOM tags or None if not found
    """
    try:
        response = requests.get(
            f"{ORTHANC_SERVER_URL}/instances/{instance_id}/tags",
            auth=(ORTHANC_USERNAME, ORTHANC_PASSWORD)
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error getting instance tags: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error getting instance tags: {str(e)}")
        return None

def get_instance_waveform(instance_id):
    """
    Get ECG waveform data from a DICOM instance.
    
    Args:
        instance_id (str): The Orthanc instance ID
        
    Returns:
        dict: Dictionary containing waveform data and metadata, or None if not found
        Format:
        {
            'waveform_data': list of waveform samples,
            'sampling_rate': sampling rate in Hz,
            'duration': duration in seconds,
            'leads': list of lead names,
            'units': measurement units
        }
    """
    try:
        # First get the raw DICOM data
        dicom_data = get_instance_dicom(instance_id)
        if not dicom_data:
            return None
            
        # Read DICOM data into memory
        ds = pydicom.dcmread(BytesIO(dicom_data))
        
        # Print all available attributes for debugging
        print("Available DICOM attributes:")
        for elem in ds:
            print(f"{elem.tag}: {elem.name}")
        
        # Check if this is an ECG waveform
        if not hasattr(ds, 'WaveformSequence'):
            print("No waveform sequence found in DICOM file")
            return None
            
        result = {
            'waveform_data': [],
            'sampling_rate': None,
            'duration': None,
            'leads': [],
            'units': None
        }
        
        # Get waveform data from the first waveform sequence
        waveform = ds.WaveformSequence[0]
        
        # Print waveform attributes for debugging
        print("\nWaveform attributes:")
        for elem in waveform:
            print(f"{elem.tag}: {elem.name}")
        
        # Get sampling rate (0x003A,0x001A - SamplingFrequency)
        if hasattr(waveform, 'SamplingFrequency'):
            result['sampling_rate'] = float(waveform.SamplingFrequency)
        
        # Get number of samples (0x003A,0x0010 - NumberOfWaveformSamples)
        if hasattr(waveform, 'NumberOfWaveformSamples'):
            num_samples = waveform.NumberOfWaveformSamples
            if result['sampling_rate']:
                result['duration'] = num_samples / result['sampling_rate']
        
        # Get channel data
        if hasattr(waveform, 'ChannelDefinitionSequence'):
            for channel in waveform.ChannelDefinitionSequence:
                # Print channel attributes for debugging
                print("\nChannel attributes:")
                for elem in channel:
                    print(f"{elem.tag}: {elem.name}")
                
                # Try different possible tags for lead name
                lead_name = None
                if hasattr(channel, 'ChannelSourceSequence'):
                    source_seq = channel.ChannelSourceSequence[0]
                    if hasattr(source_seq, 'CodeMeaning'):
                        lead_name = str(source_seq.CodeMeaning)
                elif hasattr(channel, 'ChannelLabel'):
                    lead_name = str(channel.ChannelLabel)
                
                if lead_name:
                    result['leads'].append(lead_name)
                
                # Get units (0x003A,0x0211 - ChannelSensitivityUnitsSequence)
                if not result['units'] and hasattr(channel, 'ChannelSensitivityUnitsSequence'):
                    units_seq = channel.ChannelSensitivityUnitsSequence[0]
                    if hasattr(units_seq, 'CodeMeaning'):
                        result['units'] = str(units_seq.CodeMeaning)
        
        # Get actual waveform data (0x5400,0x0100 - WaveformData)
        if hasattr(waveform, 'WaveformData'):
            # Convert byte array to numpy array of 16-bit integers
            data = np.frombuffer(waveform.WaveformData, dtype=np.int16)
            
            # Reshape data for multiple channels
            num_channels = len(waveform.ChannelDefinitionSequence)
            if num_samples and num_channels:
                data = data.reshape(num_samples, num_channels)
            
            # Convert to list for JSON serialization
            result['waveform_data'] = data.tolist()
        
        # Print final result for debugging
        print("\nExtracted waveform data:")
        print(f"Sampling rate: {result['sampling_rate']}")
        print(f"Duration: {result['duration']}")
        print(f"Leads: {result['leads']}")
        print(f"Units: {result['units']}")
        print(f"Data shape: {len(result['waveform_data'])} samples x {len(result['leads'])} leads")
        
        return result
            
    except Exception as e:
        print(f"Error getting waveform data: {str(e)}")
        import traceback
        print(f"Full error: {traceback.format_exc()}")
        return None
