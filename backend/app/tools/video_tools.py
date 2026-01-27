import os
import cv2
import base64
import numpy as np
from PIL import Image
import imagehash
from typing import List, Tuple, Dict, Any
from ultralytics import YOLO


def extract_frames(video_path: str, extract_dir: str, frame_rate: int = 1) -> List[str]:
    """
    Extract frames from video at specified frame rate.
    
    Args:
        video_path: Path to the input video
        extract_dir: Directory to save extracted frames
        frame_rate: Frame extraction rate (frames per second)
    
    Returns:
        List of paths to extracted frames
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    interval = int(fps / frame_rate) if fps > 0 and frame_rate > 0 else 30
    interval = max(1, interval)

    frame_paths = []
    frame_count = 0
    saved_count = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % interval == 0:
            frame_filename = os.path.join(extract_dir, f"frame_{saved_count}.jpg")
            cv2.imwrite(frame_filename, frame)
            frame_paths.append(frame_filename)
            saved_count += 1

        frame_count += 1

    cap.release()
    return frame_paths


def filter_frames_with_stats(frame_paths: List[str], 
                           hamming_distance_threshold: int = 25, 
                           blur_threshold: float = 50, 
                           brightness_threshold: float = 50.0) -> Tuple[List[str], Dict[str, int]]:
    """
    Filter frames based on various criteria and return statistics.
    
    Args:
        frame_paths: List of frame file paths
        hamming_distance_threshold: Threshold for detecting similar frames
        blur_threshold: Threshold for detecting blurry frames
        brightness_threshold: Threshold for detecting dark frames
    
    Returns:
        Tuple of (filtered frames, deletion statistics)
    """
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    selected_frames = []
    previous_hash = None

    deletion_stats = {
        'similar': 0,
        'blurry': 0,
        'dark': 0,
        'sensitive': 0
    }

    for frame_path in frame_paths:
        try:
            img_pil = Image.open(frame_path)
            current_hash = imagehash.phash(img_pil)
            img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

            # Filter similar frames
            if previous_hash is not None:
                distance = current_hash - previous_hash
                if distance <= hamming_distance_threshold:
                    os.remove(frame_path)
                    deletion_stats['similar'] += 1
                    continue
            previous_hash = current_hash

            # Filter blurry frames
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            if laplacian_var <= blur_threshold:
                os.remove(frame_path)
                deletion_stats['blurry'] += 1
                continue

            # Filter dark frames
            hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)
            brightness = hsv[:, :, 2].mean()
            if brightness <= brightness_threshold:
                os.remove(frame_path)
                deletion_stats['dark'] += 1
                continue

            # Remove frames with faces
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            if len(faces) > 0:
                os.remove(frame_path)
                deletion_stats['sensitive'] += 1
                continue

            selected_frames.append(frame_path)

        except IOError:
            continue

    return selected_frames, deletion_stats


def batch_images(image_paths: List[str], batch_size: int) -> List[List[str]]:
    """
    Split image paths into batches of specified size.
    
    Args:
        image_paths: List of image file paths
        batch_size: Size of each batch
    
    Returns:
        List of image path batches
    """
    batches = []
    for i in range(0, len(image_paths), batch_size):
        batches.append(image_paths[i:i + batch_size])
    return batches


def get_representative_images(frame_batches: List[List[str]]) -> List[str]:
    """
    Select representative images from each batch (first image from each batch).
    
    Args:
        frame_batches: List of image batches
    
    Returns:
        List of representative image paths
    """
    representative_images = []
    
    for batch in frame_batches:
        if len(batch) > 0:
            representative_images.append(batch[0])
    
    return representative_images


def yolo_detect_and_draw(
    frame_paths: List[str],
    model: YOLO,
    confidence_threshold: float = 0.5,
) -> Tuple[List[str], Dict[str, List[str]]]:
    """
    Run YOLO object detection on images and draw bounding boxes.
    
    Args:
        frame_paths: List of image file paths
        model: YOLO model instance
        confidence_threshold: Minimum confidence threshold for detections
    
    Returns:
        Tuple of (processed image paths, detected object summaries)
    """
    processed_paths = []
    detected_objects: Dict[str, List[str]] = {}
    
    for frame_path in frame_paths:
        img = cv2.imread(frame_path)
        if img is None:
            print(f"Error: Unable to load image {frame_path}")
            continue

        # Run YOLO detection
        detections = model(frame_path)
        objects_for_frame: List[str] = []

        # Process detections
        if len(detections) > 0 and hasattr(detections[0], 'boxes'):
            for detection in detections[0].boxes:
                if hasattr(detection, 'xyxy') and len(detection.xyxy) > 0:
                    x1, y1, x2, y2 = detection.xyxy[0]
                    conf = detection.conf[0]
                    cls = detection.cls[0]

                    if conf > confidence_threshold:
                        if int(cls) < len(model.names):
                            class_name = model.names[int(cls)]
                            objects_for_frame.append(class_name)
                            height, width = img.shape[:2]

                            # Draw rectangle
                            if 0 <= x1 <= width and 0 <= y1 <= height and 0 <= x2 <= width and 0 <= y2 <= height:
                                cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)

                                # Add label
                                label = f"{class_name} {conf:.2f}"
                                label_y = max(0, int(y1) - 10)
                                cv2.putText(img, label, (int(x1), label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        # Save processed image
        cv2.imwrite(frame_path, img)
        processed_paths.append(frame_path)
        detected_objects[frame_path] = sorted(set(objects_for_frame))
    
    return processed_paths, detected_objects
