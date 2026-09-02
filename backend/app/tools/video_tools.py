from io import BytesIO
import math
import av
from app import storage
from app.settings import get_settings
import cv2
import numpy as np
from PIL import Image
import imagehash
from typing import List, Tuple, Dict, Any
from ultralytics import YOLO


def _read_image(ref):
    return cv2.imdecode(np.frombuffer(storage.read(ref),dtype=np.uint8),cv2.IMREAD_COLOR)


def _sharpness_variance(gray: np.ndarray) -> float:
    """Measure at a bounded reference scale, not resolution-dependent 4K pixels.

    Only the measurement image is resized; evidence remains at original quality.
    Small inputs are never enlarged and aspect ratio is preserved.
    """
    height, width = gray.shape[:2]
    scale = min(1.0, 960 / max(height, width))
    if scale < 1:
        gray = cv2.resize(gray, (max(1, round(width * scale)), max(1, round(height * scale))),
                         interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _video_duration(container, stream, fps: float) -> float | None:
    candidates=[]
    if container.duration is not None:
        candidates.append(float(container.duration/av.time_base))
    if stream.duration is not None and stream.time_base is not None:
        candidates.append(float(stream.duration*stream.time_base))
    if stream.frames and fps>0:
        candidates.append(float(stream.frames/fps))
    return max(candidates) if candidates else None


def _sample_timestamps(duration: float, sample_rate: float, maximum: int) -> List[float]:
    """Return uniformly distributed timestamps bounded by the configured frame cap."""
    requested=max(1,math.ceil(duration*sample_rate))
    count=min(maximum,requested)
    if requested<=maximum:
        return [index/sample_rate for index in range(count)]
    spacing=duration/count
    return [index*spacing for index in range(count)]


def _store_frame(frame) -> str:
    ok,encoded=cv2.imencode('.jpg',frame.to_ndarray(format='bgr24'))
    if not ok: raise ValueError('Cannot encode extracted frame')
    return storage.put(encoded.tobytes(),'image/jpeg')


def extract_frames(video_asset_id: str) -> List[str]:
    """Extract env-configured samples without loading the complete source into RAM."""
    frames=[]
    settings=get_settings()
    with storage.local_copy(video_asset_id,maximum=settings.MAX_UPLOAD_BYTES) as local_path:
        with av.open(local_path) as container:
            if not container.streams.video:
                raise ValueError('Video stream not found')
            stream=container.streams.video[0]
            fps=float(stream.average_rate or 0)
            duration=_video_duration(container,stream,fps)
            if stream.width*stream.height>settings.MAX_VIDEO_PIXELS:
                raise ValueError('Video resolution exceeds configured limit')
            if duration is not None and duration>settings.MAX_VIDEO_SECONDS:
                raise ValueError('Video duration exceeds configured limit')

            requested=math.ceil(duration*settings.VIDEO_FRAME_SAMPLE_RATE) if duration is not None else None
            if duration is not None and requested>settings.MAX_EXTRACTED_FRAMES:
                seen_pts=set()
                tolerance=1/max(fps,1)
                for target in _sample_timestamps(
                    duration,settings.VIDEO_FRAME_SAMPLE_RATE,settings.MAX_EXTRACTED_FRAMES
                ):
                    container.seek(int(target*av.time_base),backward=True)
                    for frame in container.decode(stream):
                        elapsed=float(frame.time or 0)
                        if elapsed+tolerance<target: continue
                        identity=(frame.pts,frame.time_base)
                        if identity not in seen_pts:
                            seen_pts.add(identity)
                            frames.append(_store_frame(frame))
                        break
                return frames

            interval=max(1,int(fps/settings.VIDEO_FRAME_SAMPLE_RATE) if fps>0 else 30)
            for index,frame in enumerate(container.decode(stream)):
                elapsed=float(frame.time or 0)
                if elapsed>settings.MAX_VIDEO_SECONDS or index>max(fps,30)*settings.MAX_VIDEO_SECONDS:
                    raise ValueError('Video duration exceeds configured limit')
                if index%interval==0 and len(frames)<settings.MAX_EXTRACTED_FRAMES:
                    frames.append(_store_frame(frame))
    return frames


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
            img_pil = Image.open(BytesIO(storage.read(frame_path)))
            current_hash = imagehash.phash(img_pil)
            img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

            # Filter similar frames
            if previous_hash is not None:
                distance = current_hash - previous_hash
                if distance <= hamming_distance_threshold:
                    storage.remove_unreferenced(frame_path)
                    deletion_stats['similar'] += 1
                    continue

            # Filter blurry frames
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            laplacian_var = _sharpness_variance(gray)
            if laplacian_var <= blur_threshold:
                storage.remove_unreferenced(frame_path)
                deletion_stats['blurry'] += 1
                continue

            # Filter dark frames
            hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)
            brightness = hsv[:, :, 2].mean()
            if brightness <= brightness_threshold:
                storage.remove_unreferenced(frame_path)
                deletion_stats['dark'] += 1
                continue

            # Remove frames with faces
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            if len(faces) > 0:
                storage.remove_unreferenced(frame_path)
                deletion_stats['sensitive'] += 1
                continue

            selected_frames.append(frame_path)
            # Rejected frames must not suppress a later usable view of the scene.
            previous_hash = current_hash

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
        img = _read_image(frame_path)
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
    img = _read_image(frame_path)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    laplacian_var = _sharpness_variance(gray)
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
    detections = model(_read_image(frame_path), verbose=False)
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
        img = _read_image(frame_path)
        if img is None:
            print(f"Error: Unable to load image {frame_path}")
            continue

        # Run YOLO detection
        detections = model(img)
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
        ok, encoded = cv2.imencode('.jpg', img)
        if not ok: raise ValueError('Cannot encode annotated frame')
        storage.replace(frame_path, encoded.tobytes())
        processed_paths.append(frame_path)
        detected_objects[frame_path] = sorted(set(objects_for_frame))
    
    return processed_paths, detected_objects
