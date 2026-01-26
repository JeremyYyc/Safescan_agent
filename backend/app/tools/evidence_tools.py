from typing import List, Dict, Any, Optional


def merge_region_evidence(descriptions: List[str], region_labels: List[str]) -> List[Dict[str, Any]]:
    """
    Merge image descriptions into organized regional evidence.
    
    Args:
        descriptions: List of image descriptions
        region_labels: List of region labels corresponding to descriptions
    
    Returns:
        Merged evidence organized by regions
    """
    # Group descriptions by region
    region_groups = {}
    for desc, label in zip(descriptions, region_labels):
        if label not in region_groups:
            region_groups[label] = []
        region_groups[label].append(desc)
    
    # Create merged evidence structure
    merged_evidence = []
    for region_name, region_descriptions in region_groups.items():
        evidence_item = {
            'regionName': [region_name],
            'descriptions': region_descriptions,
            'combined_description': ' '.join(region_descriptions)
        }
        merged_evidence.append(evidence_item)
    
    return merged_evidence