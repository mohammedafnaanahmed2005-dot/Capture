@echo off
echo ================================================
echo   VisionAI - Object Detection System Setup
echo ================================================
echo.

echo [1/3] Installing Python dependencies...
pip install flask flask-socketio flask-cors opencv-python opencv-contrib-python numpy requests pillow eventlet

echo.
echo [2/3] Creating directory structure...
mkdir models 2>nul
mkdir static\css 2>nul
mkdir static\js 2>nul
mkdir static\img 2>nul
mkdir templates 2>nul
mkdir data 2>nul

echo.
echo [3/3] Downloading YOLOv4 model files...
echo Downloading yolov4-tiny.weights (this may take a minute)...
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4-tiny.weights' -OutFile 'models\yolov4-tiny.weights' }"

echo Downloading yolov4-tiny.cfg...
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg' -OutFile 'models\yolov4-tiny.cfg' }"

echo Downloading COCO class names...
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/pjreddie/darknet/master/data/coco.names' -OutFile 'models\coco.names' }"

echo.
echo ================================================
echo   Setup complete! Run: python app.py
echo ================================================
pause
