"""Promote property presentation metadata to structured columns."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260910_0007"
down_revision = "20260910_0006"
branch_labels = None
depends_on = None

SCHEMA = "property_leasing"


def upgrade() -> None:
    # Existing cover/floorplan URLs have an authoritative one-to-one mapping. Unknown parking
    # and location data remain NULL rather than being guessed.
    op.add_column("properties", sa.Column("parking_spaces", sa.Integer()), schema=SCHEMA)
    op.add_column("properties", sa.Column("floor_area_sqm", sa.Numeric(10, 2)), schema=SCHEMA)
    op.add_column("properties", sa.Column("latitude", sa.Numeric(9, 6)), schema=SCHEMA)
    op.add_column("properties", sa.Column("longitude", sa.Numeric(9, 6)), schema=SCHEMA)
    op.add_column("properties", sa.Column("display_image_urls", JSONB(), nullable=False,
                                           server_default=sa.text("'[]'::jsonb")), schema=SCHEMA)
    op.add_column("properties", sa.Column("floorplan_url", sa.Text()), schema=SCHEMA)
    op.execute(
        """
        UPDATE property_leasing.properties
        SET display_image_urls = jsonb_build_array(attributes ->> 'cover_image_url')
        WHERE jsonb_typeof(attributes -> 'cover_image_url') = 'string'
          AND length(trim(attributes ->> 'cover_image_url')) > 0
        """
    )
    op.execute(
        """
        UPDATE property_leasing.properties
        SET floorplan_url = attributes ->> 'floorplan_url'
        WHERE jsonb_typeof(attributes -> 'floorplan_url') = 'string'
          AND length(trim(attributes ->> 'floorplan_url')) > 0
        """
    )
    op.create_check_constraint("property_parking_spaces_valid", "properties",
                               "parking_spaces IS NULL OR parking_spaces >= 0", schema=SCHEMA)
    op.create_check_constraint("property_floor_area_valid", "properties",
                               "floor_area_sqm IS NULL OR floor_area_sqm > 0", schema=SCHEMA)
    op.create_check_constraint(
        "property_coordinates_valid", "properties",
        "(latitude IS NULL AND longitude IS NULL) OR "
        "(latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)", schema=SCHEMA,
    )
    op.create_check_constraint("property_display_images_array", "properties",
                               "jsonb_typeof(display_image_urls) = 'array'", schema=SCHEMA)
    # Preserve unknown legacy values while enforcing the required field on every new/updated row.
    op.execute(
        "ALTER TABLE property_leasing.properties ADD CONSTRAINT "
        "properties_parking_required CHECK (parking_spaces IS NOT NULL) NOT VALID"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE property_leasing.properties DROP CONSTRAINT properties_parking_required"
    )
    op.drop_constraint("property_display_images_array", "properties", schema=SCHEMA, type_="check")
    op.drop_constraint("property_coordinates_valid", "properties", schema=SCHEMA, type_="check")
    op.drop_constraint("property_floor_area_valid", "properties", schema=SCHEMA, type_="check")
    op.drop_constraint("property_parking_spaces_valid", "properties", schema=SCHEMA, type_="check")
    for column in ("floorplan_url", "display_image_urls", "longitude", "latitude",
                   "floor_area_sqm", "parking_spaces"):
        op.drop_column("properties", column, schema=SCHEMA)
