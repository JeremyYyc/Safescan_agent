"""Add a single city per employee and property without guessing legacy locations."""
from alembic import op
import sqlalchemy as sa

revision = "20261031_0015"
down_revision = "20261031_0014"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("cities", schema="identity_access"):
        op.create_table(
        "cities", sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("state", sa.Text, nullable=False), schema="identity_access",
    )
    op.execute("""INSERT INTO identity_access.cities (id,name,state) VALUES
        ('sydney','Sydney','NSW'), ('melbourne','Melbourne','VIC'),
        ('brisbane','Brisbane','QLD'), ('adelaide','Adelaide','SA'),
        ('perth','Perth','WA'), ('canberra','Canberra','ACT'),
        ('hobart','Hobart','TAS'), ('darwin','Darwin','NT') ON CONFLICT (id) DO NOTHING""")
    if "city_id" not in {col["name"] for col in inspector.get_columns("staff", schema="identity_access")}:
        op.add_column("staff", sa.Column("city_id", sa.Text), schema="identity_access")
        op.create_foreign_key("fk_staff_city_id_cities", "staff", "cities", ["city_id"], ["id"],
                              source_schema="identity_access", referent_schema="identity_access",
                              ondelete="RESTRICT")
        op.create_index("ix_staff_city_id", "staff", ["city_id"], schema="identity_access")
    for table in ("buildings", "properties"):
        if "city_id" not in {col["name"] for col in inspector.get_columns(table, schema="property_leasing")}:
            op.add_column(table, sa.Column("city_id", sa.Text), schema="property_leasing")
            op.create_index(f"ix_{table}_city_id", table, ["city_id"], schema="property_leasing")
    # Existing business records are deliberately left untouched. Resolve locations
    # and assignments through the explicit, previewable manual data-sync command.
    op.execute("""CREATE FUNCTION property_leasing.inherit_property_city() RETURNS trigger
        LANGUAGE plpgsql AS $$ DECLARE building_city text; BEGIN
        IF NEW.building_id IS NOT NULL THEN
            SELECT city_id INTO building_city FROM property_leasing.buildings WHERE id=NEW.building_id;
            IF NEW.city_id IS NOT NULL AND NEW.city_id IS DISTINCT FROM building_city
               AND (TG_OP='INSERT' OR NEW.city_id IS DISTINCT FROM OLD.city_id) THEN
                RAISE EXCEPTION 'Property city must match its building' USING ERRCODE='23514';
            END IF;
            NEW.city_id := building_city;
        END IF;
        RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER properties_inherit_city BEFORE INSERT OR UPDATE OF building_id,city_id
        ON property_leasing.properties FOR EACH ROW EXECUTE FUNCTION property_leasing.inherit_property_city()""")
    op.execute("""CREATE FUNCTION property_leasing.sync_building_city() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        UPDATE property_leasing.properties SET city_id=NEW.city_id WHERE building_id=NEW.id;
        RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER buildings_sync_city AFTER UPDATE OF city_id ON property_leasing.buildings
        FOR EACH ROW WHEN (OLD.city_id IS DISTINCT FROM NEW.city_id)
        EXECUTE FUNCTION property_leasing.sync_building_city()""")


def downgrade():
    op.execute("DROP TRIGGER buildings_sync_city ON property_leasing.buildings")
    op.execute("DROP FUNCTION property_leasing.sync_building_city()")
    op.execute("DROP TRIGGER properties_inherit_city ON property_leasing.properties")
    op.execute("DROP FUNCTION property_leasing.inherit_property_city()")
    for table in ("properties", "buildings"):
        op.drop_index(f"ix_{table}_city_id", table_name=table, schema="property_leasing")
        op.drop_column(table, "city_id", schema="property_leasing")
    op.drop_index("ix_staff_city_id", table_name="staff", schema="identity_access")
    op.drop_constraint("fk_staff_city_id_cities", "staff", schema="identity_access", type_="foreignkey")
    op.drop_column("staff", "city_id", schema="identity_access")
    op.drop_table("cities", schema="identity_access")
