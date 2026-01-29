from typing import Dict, Any, List
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.agents.alibaba_base_agent import AlibabaBaseAgent
from app.prompts import report_prompts
from app.llm_registry import get_model_name, get_max_concurrency
import dashscope
from http import HTTPStatus
import os
from app.env import load_env

load_env()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")


class SceneUnderstandingAgent(AlibabaBaseAgent):
    """Agent that analyzes representative images, identifies room types, and groups them."""
    
    def __init__(self):
        # 涓嶈皟鐢ㄧ埗绫荤殑鍒濆鍖栵紝鍥犱负鎴戜滑瑕佷娇鐢ㄩ樋閲屼簯API鐩存帴璋冪敤
        self.name = "SceneUnderstandingAgent"
    
    def _get_system_message(self) -> str:
        return report_prompts.scene_system_message()
    
    def analyze_scene(
        self,
        image_paths: List[str],
        user_attributes: Dict[str, Any],
        yolo_summaries: Dict[str, List[str]] | None = None,
        max_concurrency: int | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Analyze scenes and group by room type.
        
        Args:
            image_paths: List of image paths
            user_attributes: User attributes for personalization
            max_concurrency: Max concurrency for LLM calls
            
        Returns:
            Grouped region evidence
        """
        if max_concurrency is None:
            max_concurrency = min(get_max_concurrency(), 1)
        yolo_summaries = yolo_summaries or {}

        analyses: List[Dict[str, Any]] = [None] * len(image_paths)

        if max_concurrency <= 1 or len(image_paths) <= 1:
            for idx, image_path in enumerate(image_paths):
                _, analysis = self._analyze_single(
                    idx, image_path, yolo_summaries.get(image_path, [])
                )
                analyses[idx] = analysis
            return self._group_regions(analyses)

        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            future_to_idx = {
                executor.submit(
                    self._analyze_single,
                    idx,
                    image_path,
                    yolo_summaries.get(image_path, []),
                ): idx
                for idx, image_path in enumerate(image_paths)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    _, analysis = future.result()
                except Exception as exc:
                    analysis = {
                        "image_path": "unknown",
                        "region_label": "unknown",
                        "description": f"scene_analysis_failed: {str(exc)}",
                        "error": str(exc),
                    }
                analyses[idx] = analysis

        return self._group_regions(analyses)

    def _analyze_single(
        self, idx: int, image_path: str, yolo_objects: List[str]
    ) -> tuple[int, Dict[str, Any]]:
        messages = [
            {
                "role": "system",
                "content": self._get_system_message(),
            },
            {
                "role": "user",
                "content": [
                    {"image": f"file://{image_path}"},
                    {"text": report_prompts.scene_user_text_prompt()},
                ],
            },
        ]

        try:
            response_content = self._call_alibaba_api_with_retry(messages)
            try:
                raw_preview = response_content.replace("\n", " ") if isinstance(response_content, str) else str(response_content)
                print(f"[SCENE_RAW] frame={image_path} len={len(response_content) if isinstance(response_content, str) else 'n/a'} text={raw_preview[:200]}", flush=True)
            except Exception:
                pass
            parsed = self._parse_scene_json(response_content)
            if parsed:
                room_type = parsed.get("room_type") or "Unknown"
                if room_type == "Unknown":
                    inferred = self._infer_room_from_yolo(yolo_objects)
                    if inferred != "Unknown":
                        room_type = inferred
                description = parsed.get("description") or ""
                key_objects = parsed.get("key_objects") or []
                try:
                    desc_len = len(description) if isinstance(description, str) else 0
                    print(f"[SCENE_PARSED] frame={image_path} room_type={room_type} key_objects={key_objects} desc_len={desc_len}", flush=True)
                except Exception:
                    pass
                analysis = {
                    "image_path": image_path,
                    "region_label": room_type,
                    "description": description,
                    "key_objects": key_objects,
                }
            else:
                try:
                    print(f"[SCENE_PARSE_FAIL] frame={image_path} reason=invalid_json", flush=True)
                except Exception:
                    pass
                inferred = self._infer_room_from_yolo(yolo_objects)
                if inferred != "Unknown":
                    analysis = {
                        "image_path": image_path,
                        "region_label": inferred,
                        "description": "Inferred from detected objects.",
                        "key_objects": yolo_objects,
                    }
                else:
                    analysis = {
                        "image_path": image_path,
                        "region_label": self._extract_region_label(response_content),
                        "description": response_content,
                    }
        except Exception as exc:
            try:
                print(f"[SCENE_PARSE_FAIL] frame={image_path} error={str(exc)}", flush=True)
            except Exception:
                pass
            inferred = self._infer_room_from_yolo(yolo_objects)
            if inferred != "Unknown":
                analysis = {
                    "image_path": image_path,
                    "region_label": inferred,
                    "description": "Inferred from detected objects (fallback).",
                    "key_objects": yolo_objects,
                    "error": str(exc),
                }
            else:
                analysis = {
                    "image_path": image_path,
                    "region_label": "unknown",
                    "description": f"scene_analysis_failed: {str(exc)}",
                    "error": str(exc),
                }

        try:
            print(f"[SCENE] room_type={analysis.get('region_label')} image={image_path}", flush=True)
        except Exception:
            pass

        return idx, analysis

    def _call_alibaba_api_with_retry(self, messages: List[Dict[str, Any]], retries: int = 3) -> str:
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return self.call_alibaba_api(messages)
            except Exception as exc:
                last_exc = exc
                if attempt < retries:
                    time.sleep(1.2 * (attempt + 1))
                    continue
                raise exc

    def _infer_room_from_yolo(self, objects: List[str]) -> str:
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

    def _parse_scene_json(self, response: str) -> Dict[str, Any] | None:
        if not response or not isinstance(response, str):
            return None
        try:
            parsed = self.parse_json_response(response)
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        if "room_type" not in parsed and "description" not in parsed:
            return None
        room_type = parsed.get("room_type")
        if isinstance(room_type, str) and room_type.strip():
            normalized = self._normalize_region_label(room_type)
            parsed["room_type"] = normalized
        else:
            parsed["room_type"] = "Unknown"
        if parsed["room_type"] not in self._allowed_room_types():
            parsed["room_type"] = "Unknown"
        return parsed

    def _allowed_room_types(self) -> set[str]:
        return {
            "Bedroom",
            "Bathroom",
            "Kitchen",
            "Living Room",
            "Dining Room",
            "Study",
            "Hallway",
            "Balcony",
            "Laundry",
            "Garage",
            "Entryway",
            "Other",
            "Unknown",
        }

    def _normalize_region_label(self, label: str) -> str:
        if not label or not isinstance(label, str):
            return "Unknown"
        cleaned = re.sub(r"[_-]+", " ", label).strip().lower()
        if not cleaned:
            return "Unknown"
        if cleaned == "unknown":
            return "Unknown"
        canonical = self._canonical_room_label(cleaned)
        if canonical:
            return canonical
        normalized = " ".join(word.capitalize() for word in cleaned.split())
        return normalized if normalized in self._allowed_room_types() else "Unknown"

    def _canonical_room_label(self, label_lower: str) -> str | None:
        mapping = [
            ("bedroom", "Bedroom"),
            ("master bedroom", "Bedroom"),
            ("bathroom", "Bathroom"),
            ("washroom", "Bathroom"),
            ("restroom", "Bathroom"),
            ("toilet", "Bathroom"),
            ("kitchen", "Kitchen"),
            ("kitchenette", "Kitchen"),
            ("living room", "Living Room"),
            ("living area", "Living Room"),
            ("lounge", "Living Room"),
            ("dining room", "Dining Room"),
            ("dining area", "Dining Room"),
            ("study", "Study"),
            ("office", "Study"),
            ("hallway", "Hallway"),
            ("entryway", "Entryway"),
            ("foyer", "Entryway"),
            ("balcony", "Balcony"),
            ("laundry", "Laundry"),
            ("garage", "Garage"),
        ]
        for key, canonical in mapping:
            if key in label_lower:
                return canonical
        return None

    def _build_combined_description(self, descriptions: List[str], max_chars: int = 1200) -> str:
        if not descriptions:
            return ""
        parts = []
        current_len = 0
        for desc in descriptions:
            if not desc:
                continue
            candidate = desc.strip()
            if not candidate:
                continue
            if current_len + len(candidate) + 1 > max_chars:
                break
            parts.append(candidate)
            current_len += len(candidate) + 1
        combined = " ".join(parts).strip()
        if not combined and descriptions:
            combined = descriptions[0][:max_chars].rstrip()
        return combined


    def _select_group_items(
        self,
        items: List[Dict[str, Any]],
        min_per_room: int = 2,
        max_per_room: int = 3,
    ) -> List[Dict[str, Any]]:
        if len(items) <= max_per_room:
            return items
        if max_per_room <= 1:
            return items[:1]
        stride = (len(items) - 1) / float(max_per_room - 1)
        indices = []
        seen = set()
        for i in range(max_per_room):
            idx = int(round(i * stride))
            if idx not in seen:
                indices.append(idx)
                seen.add(idx)
        if len(indices) < max_per_room:
            for idx in range(len(items)):
                if idx not in seen:
                    indices.append(idx)
                    seen.add(idx)
                if len(indices) >= max_per_room:
                    break
        indices.sort()
        return [items[idx] for idx in indices]

    def _group_regions(self, analyses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        bedroom_group_count = 0
        current_bedroom_key = None
        last_bedroom_index = None

        for idx, analysis in enumerate(analyses):
            if not analysis:
                continue
            label_raw = analysis.get("region_label", "Unknown")
            label_norm = self._normalize_region_label(label_raw)

            if label_norm == "Bedroom":
                if last_bedroom_index is None or idx - last_bedroom_index > 1:
                    bedroom_group_count += 1
                    current_bedroom_key = f"Bedroom{bedroom_group_count}"
                label_key = current_bedroom_key
                last_bedroom_index = idx
            else:
                label_key = label_norm
                if label_norm == "Unknown":
                    label_key = f"Unknown {idx + 1}"

            group = grouped.get(label_key)
            if not group:
                group = {
                    "region_label": label_key,
                    "items": [],
                    "first_index": idx,
                }
                grouped[label_key] = group

            group["items"].append(
                {
                    "idx": idx,
                    "image_path": analysis.get("image_path"),
                    "description": analysis.get("description", ""),
                    "key_objects": analysis.get("key_objects") or [],
                }
            )

        grouped_list = sorted(grouped.values(), key=lambda item: item.get("first_index", 0))
        for item in grouped_list:
            selected_items = self._select_group_items(item.get("items", []))
            item["image_paths"] = [
                entry["image_path"]
                for entry in selected_items
                if entry.get("image_path")
            ]
            item["evidence_frames"] = [entry["idx"] for entry in selected_items]
            item["descriptions"] = [
                entry["description"]
                for entry in selected_items
                if entry.get("description")
            ]
            key_objects = []
            for entry in selected_items:
                if isinstance(entry.get("key_objects"), list):
                    key_objects.extend(
                        [obj for obj in entry["key_objects"] if isinstance(obj, str)]
                    )
            if key_objects:
                item["key_objects"] = sorted(set(key_objects))
            combined = self._build_combined_description(item.get("descriptions", []))
            item["description"] = combined
            item.pop("items", None)
            item.pop("first_index", None)

        return grouped_list

    def call_alibaba_api(self, messages: List[Dict[str, Any]]) -> str:
        """
        Call the Alibaba DashScope multimodal API for image analysis.
        """
        import dashscope
        from http import HTTPStatus
        
        model = get_model_name("VL")
        
        try:
            response = dashscope.MultiModalConversation.call(
                model=model,
                messages=messages
            )
            
            if response.status_code == HTTPStatus.OK:
                return response.output.choices[0].message.content[0]['text']
            else:
                raise Exception(f"API call failed: {response.code}, {response.message}")
                
        except Exception as e:
            raise Exception(f"Alibaba API call error: {str(e)}")
    
    def _extract_region_label(self, description: str) -> str:
        """
        Extract a room label from free-form text when structured output is unavailable.
        """
        description_lower = description.lower()

        room_types = [
            ("kitchen", "kitchen"),
            ("kitchenette", "kitchen"),
            ("bedroom", "bedroom"),
            ("master bedroom", "bedroom"),
            ("bathroom", "bathroom"),
            ("washroom", "bathroom"),
            ("restroom", "bathroom"),
            ("toilet", "bathroom"),
            ("living room", "living room"),
            ("living area", "living room"),
            ("lounge", "living room"),
            ("dining room", "dining room"),
            ("dining area", "dining room"),
            ("study", "study"),
            ("office", "study"),
            ("hallway", "hallway"),
            ("entryway", "entryway"),
            ("foyer", "entryway"),
            ("balcony", "balcony"),
            ("laundry", "laundry"),
            ("garage", "garage"),
        ]

        for eng, alias in room_types:
            if eng in description_lower or alias in description_lower:
                return eng.replace(" ", "_").title()

        return "Unknown"




