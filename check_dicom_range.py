import pydicom
import numpy as np
import os

# Set DICOM file path
dicom_dir = os.path.join(os.path.dirname(__file__), "dicom_files", "test")
dicom_file = os.path.join(dicom_dir, "image-00000.dcm")

print(f"Looking for DICOM file: {dicom_file}")
if not os.path.exists(dicom_file):
    print(f"File does not exist: {dicom_file}")
    # List all .dcm files in directory
    if os.path.exists(dicom_dir):
        dcm_files = [f for f in os.listdir(dicom_dir) if f.endswith('.dcm')]
        if dcm_files:
            print("\nFound the following DICOM files:")
            for f in dcm_files:
                print(f"- {f}")
            # Use the first file found
            dicom_file = os.path.join(dicom_dir, dcm_files[0])
            print(f"\nWill use the first file: {dcm_files[0]}")
        else:
            print(f"\nNo DICOM files found in directory {dicom_dir}")
            exit(1)
    else:
        print(f"\nDirectory does not exist: {dicom_dir}")
        exit(1)

# Read DICOM file
ds = pydicom.dcmread(dicom_file)

# Get waveform data
if hasattr(ds, 'WaveformSequence'):
    waveform_data = np.frombuffer(ds.WaveformSequence[0].WaveformData, dtype=np.int16)
    num_channels = ds.WaveformSequence[0].NumberOfWaveformChannels
    num_samples = ds.WaveformSequence[0].NumberOfWaveformSamples
    
    print(f"\nWaveform data summary:")
    print(f"Number of leads: {num_channels}")
    print(f"Number of samples per lead: {num_samples}")
    
    # Reshape data to 2D array [samples, channels]
    waveform_data = waveform_data.reshape(num_samples, num_channels)
    
    # Analyze range for each lead
    for i, channel in enumerate(ds.WaveformSequence[0].ChannelDefinitionSequence):
        lead_name = channel.ChannelLabel
        lead_data = waveform_data[:, i]
        print(f"\nLead {lead_name}:")
        print(f"Minimum value: {lead_data.min()}")
        print(f"Maximum value: {lead_data.max()}")
        print(f"Mean value: {lead_data.mean():.2f}")
        print(f"Standard deviation: {lead_data.std():.2f}")
        
        # Convert to millivolts
        mv_min = lead_data.min() / 6553.6
        mv_max = lead_data.max() / 6553.6
        print(f"Millivolt range: {mv_min:.2f}mV to {mv_max:.2f}mV")
else:
    print("No waveform data found")
