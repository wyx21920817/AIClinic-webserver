import requests
import os
import json
import pydicom
from io import BytesIO
import numpy as np
from app.core.config import settings

ORTHANC_SERVER_URL = "http://54.79.224.136:8042"

def get_headers(token):
    """
    获取请求头，包含JWT token
    
    Args:
        token (str): JWT token
        
    Returns:
        dict: 包含Authorization header的字典
    """
    if not token:
        raise ValueError("Token is required for Orthanc API calls")
    
    print(f"Using token for Orthanc API: {token}")  # Debug token
    return {
        'Authorization': f"Bearer {token}",
        'Accept': 'application/json'
    }

def upload_dicom_file(file_path, token):
    """
    Upload a DICOM file to the Orthanc server.
    
    Args:
        file_path (str): The path to the DICOM file to upload
        token (str): JWT token for authentication
        
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
        headers = get_headers(token)
        headers['Content-Type'] = 'application/dicom'
        
        print(f"Sending request to Orthanc with headers: {headers}")  # Debug headers
        
        response = requests.post(
            f"{ORTHANC_SERVER_URL}/instances",
            headers=headers,
            data=dicom_content,
            verify=False  # 如果是自签名证书，可能需要这个
        )
        
        print(f"Upload response status: {response.status_code}")  # Debug
        print(f"Upload response headers: {response.headers}")  # Debug
        print(f"Upload response text: {response.text}")  # Debug
        
        if response.status_code in [200, 201]:  # 接受 200 或 201
            return response.json()
        else:
            print(f"Error uploading DICOM file: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error uploading DICOM file: {str(e)}")
        import traceback
        print(f"Full error: {traceback.format_exc()}")  # 添加完整的错误追踪
        return None

def upload_dicom_folder(folder_path, token):
    """
    Upload all DICOM files from a folder to the Orthanc server.
    
    Args:
        folder_path (str): Path to the folder containing DICOM files
        token (str): JWT token for authentication
        
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
                result = upload_dicom_file(file_path, token)
                if result:
                    successful_uploads.append(result)
                    
    return successful_uploads

def get_instance(instance_id, token):
    """
    Get DICOM instance details from Orthanc server.
    
    Args:
        instance_id (str): The Orthanc instance ID
        token (str): JWT token for authentication
        
    Returns:
        dict: Instance details or None if not found
    """
    try:
        response = requests.get(
            f"{ORTHANC_SERVER_URL}/instances/{instance_id}",
            headers=get_headers(token)
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

def get_instance_dicom(instance_id, token):
    """
    Get DICOM file data from Orthanc server.
    
    Args:
        instance_id (str): The Orthanc instance ID
        token (str): JWT token for authentication
        
    Returns:
        bytes: Raw DICOM data or None if not found
    """
    try:
        response = requests.get(
            f"{ORTHANC_SERVER_URL}/instances/{instance_id}/file",
            headers=get_headers(token)
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

def modify_instance_metadata(instance_id, metadata, token):
    """
    Modify instance metadata in Orthanc server.
    
    Args:
        instance_id (str): The Orthanc instance ID
        metadata (dict): Dictionary containing metadata to modify
        token (str): JWT token for authentication
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        headers = get_headers(token)
        headers['Content-Type'] = 'application/json'
        
        response = requests.put(
            f"{ORTHANC_SERVER_URL}/instances/{instance_id}/metadata",
            headers=headers,
            json=metadata
        )
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"Error modifying metadata: {str(e)}")
        return False

def delete_instance(instance_id, token):
    """
    Delete a DICOM instance from Orthanc server.
    
    Args:
        instance_id (str): The Orthanc instance ID
        token (str): JWT token for authentication
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        response = requests.delete(
            f"{ORTHANC_SERVER_URL}/instances/{instance_id}",
            headers=get_headers(token)
        )
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"Error deleting instance: {str(e)}")
        return False

def search_instances(query, token):
    """
    Search for DICOM instances in Orthanc server.
    
    Args:
        query (dict): Query parameters for search
        token (str): JWT token for authentication
        
    Returns:
        list: List of matching instance IDs
    """
    try:
        headers = get_headers(token)
        headers['Content-Type'] = 'application/json'
        
        response = requests.post(
            f"{ORTHANC_SERVER_URL}/tools/find",
            headers=headers,
            json=query
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

def get_instance_tags(instance_id, token):
    """
    Get DICOM tags of an instance.
    
    Args:
        instance_id (str): The Orthanc instance ID
        token (str): JWT token for authentication
        
    Returns:
        dict: Dictionary containing DICOM tags or None if not found
    """
    try:
        response = requests.get(
            f"{ORTHANC_SERVER_URL}/instances/{instance_id}/tags",
            headers=get_headers(token)
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error getting tags: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error getting tags: {str(e)}")
        return None

def get_instance_waveform(instance_id, token):
    """
    Get ECG waveform data from a DICOM instance.
    
    Args:
        instance_id (str): The Orthanc instance ID
        token (str): JWT token for authentication
        
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
    # Get the DICOM file data
    dicom_data = get_instance_dicom(instance_id, token)
    if not dicom_data:
        return None
        
    try:
        # Load the DICOM data
        dataset = pydicom.dcmread(BytesIO(dicom_data))
        
        # Check if this is a waveform object
        if not hasattr(dataset, 'WaveformSequence'):
            print("No waveform data found in DICOM file")
            return None
            
        # Get the first waveform sequence
        waveform = dataset.WaveformSequence[0]
        
        # Get the number of channels (leads)
        num_channels = waveform.NumberOfWaveformChannels
        
        # Get the number of samples
        num_samples = waveform.NumberOfWaveformSamples
        
        # Get the sampling rate
        sampling_rate = float(waveform.SamplingFrequency)
        
        # Get the waveform data
        waveform_data = waveform.WaveformData
        
        # Get channel definitions
        channel_definitions = waveform.ChannelDefinitionSequence
        
        # Extract lead names
        leads = []
        for channel in channel_definitions:
            leads.append(channel.ChannelSourceSequence[0].CodeMeaning)
            
        # Convert byte array to numpy array of 16-bit integers
        data = np.frombuffer(waveform_data, dtype=np.int16)
        
        # Reshape the data into channels
        data = data.reshape(num_samples, num_channels)
        
        # Calculate duration
        duration = num_samples / sampling_rate
        
        # Get units (usually mV)
        units = channel_definitions[0].ChannelSensitivity
        
        return {
            'waveform_data': data.tolist(),
            'sampling_rate': sampling_rate,
            'duration': duration,
            'leads': leads,
            'units': units
        }
        
    except Exception as e:
        print(f"Error processing waveform data: {str(e)}")
        return None
