# AIClinic DICOM Web Viewer

A web-based DICOM viewer application built with React and Python Flask that allows users to upload and view DICOM files, with a focus on ECG data visualization and AI-enhanced features.

## Features

- DICOM file upload and conversion
- ECG waveform extraction and visualization
- Automatic lead detection and classification
- Standard ECG scaling (±5mV range)
- High-quality waveform digitization (3000 points per lead)
- Modern and responsive UI

## Technical Details

### ECG Waveform Processing

- **Waveform Extraction**: Uses computer vision techniques to extract ECG waveforms from images
- **Data Points**: 3000 points per lead, with middle 3/5 (1800 points) used for display
- **Scaling**: Standardized to ±5mV range
- **Digital Conversion**: Uses standard ECG digitization (1mV = 6553.6 counts)
- **Lead Detection**: AI-powered automatic lead detection and classification

### Backend (Python)

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Start the Flask server:
```bash
python run.py
```

The backend server will be available at http://localhost:8000
API documentation will be available at http://localhost:8000/apidocs
Test page will be available at http://localhost:8000/

### Frontend (React)

1. Install Node.js dependencies:
```bash
npm install
```

2. Start the development server:
```bash
npm start
```

The frontend application will be available at http://localhost:3000

## Technologies

### Backend
- Python Flask
- OpenCV for image processing
- NumPy for numerical operations
- PyDICOM for DICOM handling
- YOLOv5 for lead detection

### Frontend
- React
- Material-UI
- DICOM.js
- ECG visualization components

## Testing

### Test Page
The test interface is available at http://localhost:8000/

Features available on the test page:
- File upload testing
- ECG waveform visualization testing
- DICOM conversion testing
- Lead detection verification
- Waveform scaling verification

### API Testing
The API testing interface is available through Swagger UI at http://localhost:8000/apidocs

Key endpoints include:
- `POST /api/upload`: Upload and process DICOM files
- `GET /api/dicom/{id}`: Retrieve processed DICOM data
- `POST /api/convert`: Convert image to DICOM format

## API Endpoints

- `POST /api/upload`: Upload and process DICOM files
- `GET /api/dicom/{id}`: Retrieve processed DICOM data
- `POST /api/convert`: Convert image to DICOM format

## API Documentation

The API documentation is available through Swagger UI at http://localhost:8000/apidocs

Key endpoints include:
- `POST /api/upload`: Upload and process DICOM files
  - Supports both DICOM and image file formats
  - Returns processed file ID and status
- `GET /api/dicom/{id}`: Retrieve processed DICOM data
  - Returns DICOM file with extracted waveforms
- `POST /api/convert`: Convert image to DICOM format
  - Supports various image formats
  - Performs automatic lead detection and waveform extraction
  - Returns standardized DICOM ECG file

For detailed API specifications and testing interface, visit the Swagger UI documentation.

## Development

The project follows modern software development practices:
- Modular architecture
- Clean code principles
- Comprehensive logging
- Error handling
- Standard ECG processing protocols
