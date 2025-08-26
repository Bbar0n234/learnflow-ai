"""Add seed data with name support

Revision ID: 954ed3a47a38
Revises: c541edc48932
Create Date: 2025-08-26 15:51:25.612262

"""
from typing import Sequence, Union
import uuid
from datetime import datetime
from pathlib import Path

import yaml
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String, Text, UUID, DateTime, BigInteger


# revision identifiers, used by Alembic.
revision: str = '954ed3a47a38'
down_revision: Union[str, Sequence[str], None] = 'c541edc48932'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def load_seed_data():
    """Load seed data from YAML file."""
    # Get the path to the seed data file relative to migration
    current_dir = Path(__file__).parent.parent.parent  # Go up to prompt-config-service root
    yaml_path = current_dir / "initial_data.yaml"
    
    if not yaml_path.exists():
        raise FileNotFoundError(f"Seed data file not found: {yaml_path}")
    
    with open(yaml_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def upgrade() -> None:
    """Add initial seed data using op.bulk_insert()."""
    # Load seed data
    data = load_seed_data()
    
    # Define ad-hoc tables for bulk_insert
    placeholders_table = table('placeholders',
        column('id', UUID),
        column('name', String),
        column('display_name', String),
        column('description', Text),
        column('created_at', DateTime),
        column('updated_at', DateTime)
    )
    
    placeholder_values_table = table('placeholder_values',
        column('id', UUID),
        column('placeholder_id', UUID),
        column('name', String),
        column('value', Text),
        column('display_name', String),
        column('description', Text),
        column('created_at', DateTime)
    )
    
    profiles_table = table('profiles',
        column('id', UUID),
        column('name', String),
        column('display_name', String),
        column('category', String),
        column('description', Text),
        column('created_at', DateTime),
        column('updated_at', DateTime)
    )
    
    profile_settings_table = table('profile_placeholder_settings',
        column('profile_id', UUID),
        column('placeholder_id', UUID),
        column('placeholder_value_id', UUID),
        column('created_at', DateTime)
    )
    
    # Track IDs for relationships
    placeholder_ids = {}
    placeholder_value_ids = {}
    placeholder_value_names = {}  # Map for name -> value_id lookup
    profile_ids = {}
    
    # Prepare placeholder data
    placeholders_data = []
    for placeholder_data in data["placeholders"]:
        placeholder_id = uuid.uuid4()
        placeholder_ids[placeholder_data["name"]] = placeholder_id
        
        placeholders_data.append({
            "id": placeholder_id,
            "name": placeholder_data["name"],
            "display_name": placeholder_data["display_name"],
            "description": placeholder_data.get("description"),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
    
    # Insert placeholders
    if placeholders_data:
        op.bulk_insert(placeholders_table, placeholders_data)
    
    # Prepare placeholder values data
    values_data = []
    for placeholder_data in data["placeholders"]:
        placeholder_id = placeholder_ids[placeholder_data["name"]]
        
        # Initialize the nested dict for this placeholder
        if placeholder_data["name"] not in placeholder_value_names:
            placeholder_value_names[placeholder_data["name"]] = {}
        
        for value_data in placeholder_data["values"]:
            value_id = uuid.uuid4()
            
            # Store mapping by placeholder_name -> value_name -> value_id
            value_name = value_data.get("name", value_data["value"])  # Use name if exists, else fallback to value
            placeholder_value_names[placeholder_data["name"]][value_name] = value_id
            
            # Also store by full value for backwards compatibility
            value_key = f"{placeholder_data['name']}:{value_data['value']}"
            placeholder_value_ids[value_key] = value_id
            
            values_data.append({
                "id": value_id,
                "placeholder_id": placeholder_id,
                "name": value_data.get("name", value_data["value"][:100]),  # Use name or truncated value
                "value": value_data["value"],
                "display_name": value_data["display_name"],
                "description": value_data.get("description"),
                "created_at": datetime.utcnow()
            })
    
    # Insert placeholder values
    if values_data:
        op.bulk_insert(placeholder_values_table, values_data)
    
    # Prepare profile data
    profiles_data = []
    for profile_data in data.get("profiles", []):
        profile_id = uuid.uuid4()
        profile_ids[profile_data["name"]] = profile_id
        
        profiles_data.append({
            "id": profile_id,
            "name": profile_data["name"],
            "display_name": profile_data["display_name"],
            "category": profile_data["category"],
            "description": profile_data.get("description"),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
    
    # Insert profiles
    if profiles_data:
        op.bulk_insert(profiles_table, profiles_data)
    
    # Prepare profile settings data
    settings_data = []
    for profile_data in data.get("profiles", []):
        profile_id = profile_ids[profile_data["name"]]
        
        for placeholder_name, value_ref in profile_data["settings"].items():
            if placeholder_name not in placeholder_ids:
                print(f"Warning: Placeholder {placeholder_name} not found for profile {profile_data['name']}")
                continue
            
            placeholder_id = placeholder_ids[placeholder_name]
            
            # Try to find value by name first, then by full value
            value_id = None
            if placeholder_name in placeholder_value_names:
                # First try to find by name reference
                if value_ref in placeholder_value_names[placeholder_name]:
                    value_id = placeholder_value_names[placeholder_name][value_ref]
                else:
                    # Fallback to finding by full value text
                    value_key = f"{placeholder_name}:{value_ref}"
                    if value_key in placeholder_value_ids:
                        value_id = placeholder_value_ids[value_key]
            
            if not value_id:
                print(f"Warning: Value '{value_ref}' not found for placeholder {placeholder_name}")
                continue
            
            settings_data.append({
                "profile_id": profile_id,
                "placeholder_id": placeholder_id,
                "placeholder_value_id": value_id,
                "created_at": datetime.utcnow()
            })
    
    # Insert profile settings
    if settings_data:
        op.bulk_insert(profile_settings_table, settings_data)
    
    # Add default values if specified
    if "default_values" in data:
        default_values = data["default_values"]
        print(f"Default values configured: {list(default_values.keys())}")
    
    print(f"Seeded {len(placeholders_data)} placeholders with {len(values_data)} values")
    print(f"Seeded {len(profiles_data)} profiles with {len(settings_data)} settings")


def downgrade() -> None:
    """Remove seed data - only safe because we're removing all data."""
    # Get connection for executing deletes
    connection = op.get_bind()
    
    # Delete in reverse order due to foreign key constraints
    connection.execute(sa.text("DELETE FROM profile_placeholder_settings"))
    connection.execute(sa.text("DELETE FROM user_placeholder_settings"))
    connection.execute(sa.text("DELETE FROM placeholder_values"))
    connection.execute(sa.text("DELETE FROM profiles"))
    connection.execute(sa.text("DELETE FROM placeholders"))
    
    print("Seed data removed successfully!")
