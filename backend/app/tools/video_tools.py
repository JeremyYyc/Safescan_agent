import os
import cv2
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


def _compute_histogram_signature(image: np.ndarray) -> np.ndarray:
    resized = cv2.resize(image, (160, 90))
    hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def segment_frames_by_histogram(
    frame_paths: List[str],
    similarity_threshold: float = 0.78,
) -> List[List[str]]:
    segments: List[List[str]] = []
    current: List[str] = []
    prev_hist = None

    for frame_path in frame_paths:
        img = cv2.imread(frame_path)
        if img is None:
            continue
        hist = _compute_histogram_signature(img)
        if prev_hist is not None:
            similarity = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
            if similarity < similarity_threshold and current:
                segments.append(current)
                current = []
        current.append(frame_path)
        prev_hist = hist

    if current:
        segments.append(current)
    return segments


def _sample_candidates(segment: List[str], max_candidates: int) -> List[str]:
    if len(segment) <= max_candidates:
        return segment
    indices = np.linspace(0, len(segment) - 1, max_candidates, dtype=int)
    return [segment[i] for i in indices]


def _frame_quality_metrics(frame_path: str) -> Dict[str, float] | None:
    img = cv2.imread(frame_path)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    brightness = hsv[:, :, 2].mean()
    edges = cv2.Canny(gray, 100, 200)
    edge_density = float(edges.mean()) / 255.0

    sharpness_score = min(max(laplacian_var / 300.0, 0.0), 1.0)
    brightness_score = 1.0 - min(abs(brightness - 130.0) / 130.0, 1.0)
    edge_score = min(max(edge_density / 0.2, 0.0), 1.0)

    return {
        "sharpness": sharpness_score,
        "brightness": brightness_score,
        "edge_density": edge_score,
    }


def _yolo_objects_for_frame(
    frame_path: str,
    model: YOLO,
    confidence_threshold: float = 0.5,
) -> List[str]:
    detections = model(frame_path, verbose=False)
    objects_for_frame: List[str] = []
    if len(detections) > 0 and hasattr(detections[0], "boxes"):
        for detection in detections[0].boxes:
            if hasattr(detection, "xyxy") and len(detection.xyxy) > 0:
                conf = detection.conf[0]
                cls = detection.cls[0]
                if conf > confidence_threshold and int(cls) < len(model.names):
                    objects_for_frame.append(model.names[int(cls)])
    return sorted(set(objects_for_frame))


def _infer_room_type(objects: List[str]) -> str:
    if not objects:
        return "Unknown"
    obj_set = {str(obj).lower() for obj in objects}
    bathroom = {"toilet", "sink", "bathtub", "toothbrush", "hair drier"}
    kitchen = {"microwave", "oven", "refrigerator", "sink", "toaster", "knife", "spoon", "fork"}
    bedroom = {"bed"}
    dining = {"dining table"}
    living = {"couch", "sofa", "tv", "chair"}
    laundry = {"washing machine"}

    if obj_set & bathroom:
        return "Bathroom"
    if obj_set & kitchen:
        return "Kitchen"
    if obj_set & bedroom:
        return "Bedroom"
    if obj_set & dining:
        return "Dining Room"
    if obj_set & living:
        return "Living Room"
    if obj_set & laundry:
        return "Laundry"
    return "Unknown"


def select_representative_images_by_room(
    frame_paths: List[str],
    model: YOLO,
    max_frames: int = 15,
    max_per_room: int = 3,
    max_candidates_per_segment: int = 3,
    short_segment_len: int = 3,
    confidence_threshold: float = 0.5,
) -> List[str]:
    if not frame_paths:
        return []

    segments = segment_frames_by_histogram(frame_paths)
    candidates: List[Dict[str, Any]] = []

    for segment_idx, segment in enumerate(segments):
        if not segment:
            continue
        candidate_limit = 1 if len(segment) < short_segment_len else max_candidates_per_segment
        sampled = _sample_candidates(segment, candidate_limit)
        for frame_path in sampled:
            metrics = _frame_quality_metrics(frame_path)
            if not metrics:
                continue
            objects = _yolo_objects_for_frame(frame_path, model, confidence_threshold)
            room_type = _infer_room_type(objects)
            object_score = min(len(objects) / 6.0, 1.0)
            score = (
                0.35 * metrics["sharpness"]
                + 0.25 * metrics["brightness"]
                + 0.25 * object_score
                + 0.15 * metrics["edge_density"]
            )
            candidates.append(
                {
                    "path": frame_path,
                    "room": room_type,
                    "score": score,
                    "segment_id": segment_idx,
                }
            )

    if not candidates:
        return []

    room_buckets: Dict[str, List[Dict[str, Any]]] = {}
    for candidate in candidates:
        room_buckets.setdefault(candidate["room"], []).append(candidate)

    for items in room_buckets.values():
        items.sort(key=lambda item: item["score"], reverse=True)

    selections: List[Dict[str, Any]] = []
    for room, items in room_buckets.items():
        limit = min(max_per_room, len(items))
        selections.extend(items[:limit])

    if len(selections) <= max_frames:
        ordered = sorted(selections, key=lambda item: (item["segment_id"], -item["score"]))
        return [item["path"] for item in ordered]

    # Trim to max_frames with coverage preference
    room_priority = [
        "Kitchen",
        "Bathroom",
        "Bedroom",
        "Living Room",
        "Dining Room",
        "Study",
        "Hallway",
        "Entryway",
        "Laundry",
        "Balcony",
        "Garage",
        "Other",
        "Unknown",
    ]
    priority_index = {room: idx for idx, room in enumerate(room_priority)}

    essentials = []
    extras = []
    for room, items in room_buckets.items():
        essentials.append(items[0])
        extras.extend(items[1:])

    if len(essentials) > max_frames:
        essentials.sort(
            key=lambda item: (priority_index.get(item["room"], 999), -item["score"])
        )
        essentials = essentials[:max_frames]
        ordered = sorted(essentials, key=lambda item: (item["segment_id"], -item["score"]))
        return [item["path"] for item in ordered]

    remaining = max_frames - len(essentials)
    extras.sort(key=lambda item: item["score"], reverse=True)
    final = essentials + extras[:remaining]
    ordered = sorted(final, key=lambda item: (item["segment_id"], -item["score"]))
    return [item["path"] for item in ordered]


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
