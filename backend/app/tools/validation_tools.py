from typing import Dict, Any, List, Tuple


def validate_region_data(region_data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    """
    Validate a single region's data.
    
    Args:
        region_data: Dictionary containing region information
    
    Returns:
        Tuple of (validity, errors, repair_hints)
    """
    errors = []
    repair_hints = []
    
    # Check required keys
    required_keys = ['regionName', 'potentialHazards', 'colorAndLightingEvaluation', 'suggestions', 'scores']
    for key in required_keys:
        if key not in region_data:
            errors.append(f"Missing required field: {key}")
            repair_hints.append(f"Add '{key}' field with appropriate value")
        elif not region_data[key]:
            errors.append(f"Field '{key}' is empty")
            repair_hints.append(f"Provide a non-empty value for '{key}'")
    
    # Validate scores
    if 'scores' in region_data:
        scores = region_data['scores']
        if not isinstance(scores, list):
            errors.append("'scores' must be a list")
            repair_hints.append("Convert 'scores' to a list of 5 float values")
        elif len(scores) != 5:
            errors.append(f"'scores' must contain exactly 5 values, got {len(scores)}")
            repair_hints.append("Ensure 'scores' contains exactly 5 float values [personal_safety, special_safety, color_lighting, psychological_impact, final_score]")
        else:
            for i, score in enumerate(scores):
                if not isinstance(score, (int, float)) or not (0 <= score <= 5):
                    errors.append(f"Score at index {i} ({score}) is not a float between 0 and 5")
                    repair_hints.append(f"Change score at index {i} to a float between 0 and 5")
    
    # Validate lists
    list_fields = ['regionName', 'potentialHazards', 'colorAndLightingEvaluation', 'suggestions']
    for field in list_fields:
        if field in region_data and not isinstance(region_data[field], list):
            errors.append(f"'{field}' must be a list")
            repair_hints.append(f"Convert '{field}' to a list of strings")
    
    return len(errors) == 0, errors, repair_hints


def validate_report_structure(report: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    """
    Validate the overall report structure.
    
    Args:
        report: Dictionary containing the complete report
    
    Returns:
        Tuple of (validity, errors, repair_hints)
    """
    errors = []
    repair_hints = []
    
    # Check if report has 'regions' key
    if 'regions' not in report:
        errors.append("Report must contain 'regions' key")
        repair_hints.append("Add 'regions' key with a list of region objects")
        return False, errors, repair_hints
    
    if not isinstance(report['regions'], list):
        errors.append("'regions' must be a list")
        repair_hints.append("Convert 'regions' to a list of region objects")
        return False, errors, repair_hints
    
    if len(report['regions']) == 0:
        errors.append("'regions' must not be empty")
        repair_hints.append("Generate at least one region object with required fields")
        return False, errors, repair_hints
    
    # Validate each region
    for i, region in enumerate(report['regions']):
        if not isinstance(region, dict):
            errors.append(f"Region at index {i} must be a dictionary")
            repair_hints.append(f"Convert region at index {i} to a dictionary")
            continue
            
        is_valid, region_errors, region_hints = validate_region_data(region)
        if not is_valid:
            for error in region_errors:
                errors.append(f"Region {i}: {error}")
            for hint in region_hints:
                repair_hints.append(f"For region {i}: {hint}")

    # Validate expanded top-level fields
    expanded_required = [
        "meta",
        "scores",
        "top_risks",
        "recommendations",
        "comfort",
        "compliance",
        "action_plan",
        "limitations",
    ]
    for key in expanded_required:
        if key not in report:
            errors.append(f"Missing required top-level field: {key}")
            repair_hints.append(f"Add '{key}' field with appropriate value")
        elif report[key] in (None, "", []):
            errors.append(f"Field '{key}' is empty")
            repair_hints.append(f"Provide a non-empty value for '{key}'")

    if "scores" in report and isinstance(report.get("scores"), dict):
        if "overall" not in report["scores"]:
            errors.append("Missing 'scores.overall'")
            repair_hints.append("Add 'scores.overall' as a float between 0 and 5")
        if "dimensions" not in report["scores"]:
            errors.append("Missing 'scores.dimensions'")
            repair_hints.append("Add 'scores.dimensions' with per-dimension scores")

    if "recommendations" in report:
        recs = report.get("recommendations")
        if not isinstance(recs, dict):
            errors.append("'recommendations' must be an object")
            repair_hints.append("Convert 'recommendations' to an object with 'actions'")
        else:
            actions = recs.get("actions")
            if not isinstance(actions, list) or len(actions) == 0:
                errors.append("'recommendations.actions' must be a non-empty list")
                repair_hints.append("Provide a non-empty 'recommendations.actions' list")
    
    return len(errors) == 0, errors, repair_hints


def validate_report(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Complete validation of a home safety report.
    
    Args:
        report_data: Raw report data to validate
    
    Returns:
        Validation result with validity, errors, and repair hints
    """
    is_structurally_valid, structure_errors, structure_hints = validate_report_structure(report_data)
    
    return {
        "valid": is_structurally_valid,
        "errors": structure_errors,
        "repair_hints": structure_hints
    }
