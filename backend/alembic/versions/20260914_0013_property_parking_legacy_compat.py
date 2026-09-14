"""Allow lifecycle updates for legacy properties with unknown parking."""

from alembic import op


revision = "20260914_0013"
down_revision = "20260914_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOT VALID skips the initial table scan, but PostgreSQL still evaluates the check for every
    # later UPDATE. That made unrelated lifecycle transitions fail for legacy rows whose parking
    # is intentionally unknown. A column-specific trigger preserves those rows while rejecting
    # incomplete new properties and explicit metadata edits that do not resolve parking.
    op.execute(
        "ALTER TABLE property_leasing.properties "
        "DROP CONSTRAINT properties_parking_required"
    )
    op.execute(
        """
        CREATE FUNCTION property_leasing.enforce_property_parking_required()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.parking_spaces IS NULL THEN
                RAISE EXCEPTION 'parking_spaces is required for new or explicitly edited properties'
                    USING ERRCODE = '23514', CONSTRAINT = 'properties_parking_required';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER properties_parking_required_write
        BEFORE INSERT OR UPDATE OF
            building_id, reference, address, bedrooms, bathrooms, parking_spaces,
            floor_area_sqm, latitude, longitude, display_image_urls, floorplan_url,
            weekly_rent, currency, listing_visibility, attributes
        ON property_leasing.properties
        FOR EACH ROW
        EXECUTE FUNCTION property_leasing.enforce_property_parking_required()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER properties_parking_required_write "
        "ON property_leasing.properties"
    )
    op.execute(
        "DROP FUNCTION property_leasing.enforce_property_parking_required()"
    )
    op.execute(
        "ALTER TABLE property_leasing.properties ADD CONSTRAINT "
        "properties_parking_required CHECK (parking_spaces IS NOT NULL) NOT VALID"
    )
