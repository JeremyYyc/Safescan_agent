"""City defaults for the existing demo identities; never infer a city from a state."""
STAFF_CITIES = {
    "LC001": "sydney", "LC002": "melbourne", "LC003": "brisbane", "LC004": "adelaide",
    "PM001": "sydney", "PM002": "melbourne", "PM003": "brisbane", "PM004": "adelaide",
    "MT001": "sydney", "MT002": "brisbane", "MT003": "melbourne",
    "LC005": "perth", "PM005": "perth", "MT004": "adelaide", "MT005": "perth",
}


def same_city(staff_city, property_city):
    return bool(staff_city and property_city and staff_city == property_city)

# Input normalization for the supplied Australian export, whose `city` field
# sometimes contains a suburb. These aliases never create a second management level.
CITY_LOCALITIES = {
    "sydney": ("NSW", "granville|castle hill|pyrmont|leumeah|drummoyne|gladesville|chiswick|potts point|harris park|alexandria|casula|carlingford|guildford|box hill"),
    "melbourne": ("VIC", "clayton|box hill|bentleigh east|balwyn north|caulfield east|ashwood|bentleigh|docklands"),
    "brisbane": ("QLD", "fairfield|annerley|boronia heights|bellbird park|edens landing|crestmead|alexandra hills|regents park|bundamba"),
}
CITY_NAMES = {"sydney", "melbourne", "brisbane", "adelaide", "perth", "canberra", "hobart", "darwin"}


def normalize_city(city, state=None, address=""):
    import re
    value = (city or "").strip().lower()
    if value in CITY_NAMES:
        return value
    for canonical, (expected_state, localities) in CITY_LOCALITIES.items():
        if state and state.upper() == expected_state and value in localities.split("|"):
            return canonical
    # One supplied source omits both city and state, but explicitly names Docklands.
    if not value and re.search(r"\bdocklands\b", address or "", re.I):
        return "melbourne"
    return None
