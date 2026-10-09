# HOME Docklands pilot

Captured on 2026-09-28. One official public room-type page, its explicitly linked gallery response, and up to 14 CDN images. No login, application, enquiry submission or video download.

Source: https://www.homeapartments.com.au/home-docklands/floorplans/east-%7C-2-bed-%7C-2-bath-%7C-c04

Local output: `data/collection-pilot/home-20260928T102421Z/` (ignored by Git).

## Meaning and limits

- Building: HOME Docklands; same brand website does not establish legal ownership.
- Room type: C04, two bedrooms and two bathrooms.
- Three public listing rows retain the original apartment identifiers, area and weekly AUD price. Availability is not verified against the booking system.
- Gallery: 13 marketing images and one floorplan. Photos mix display-apartment interiors and common areas; none is attributed to an individual listed unit.
- The page's video modal is empty. It is not counted as a video.
- Raw source, capture timestamps, hashes, structured JSON and a static local HTML preview are retained. No backend seed data was replaced.
- Robots permits the inspected public page paths. This is not a reuse licence. Copyright and reuse permissions remain unverified; do not publish the dataset or scale collection before review.
- Marketing images are not maintenance evidence. No maintenance history, occupant data or inspection records were collected.
- Downloaded all 14 page-provided preview-size images (511,398 bytes). The floorplan is 576-pixel wide and low contrast; obtain a higher-resolution authorised source before OCR or dimension extraction.
- Verified image decoding, SHA-256 hashes, local HTML image references and entity relationships. All 17 collection tests passed. The floorplan was visually inspected; the HTML has not been browser-render tested.

## Commands

Run from the repository root. Fetch a new page snapshot, then pass the printed directory to the following commands:

```powershell
python scripts/data_collection/home_collect.py
python scripts/data_collection/home_collect.py --gallery data/collection-pilot/<directory>
python scripts/data_collection/home_collect.py --process data/collection-pilot/<directory> --download-media
python -m unittest discover -s scripts/data_collection -p "test_*.py"
```

Omit `--download-media` for offline reprocessing. Open `preview.html` in Edge or Chrome; no server is required. External source links require Internet access. Collection is intentionally fixed to a single room type, not a general crawler.
