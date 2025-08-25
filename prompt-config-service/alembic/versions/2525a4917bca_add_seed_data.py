"""Add seed data

Revision ID: 2525a4917bca
Revises: 74528e2623f1
Create Date: 2025-08-25 19:50:19.662821

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
revision: str = '2525a4917bca'
down_revision: Union[str, Sequence[str], None] = '74528e2623f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def load_seed_data():
    """Load seed data from YAML file."""
    # Get the path to the seed data file relative to migration
    current_dir = Path(__file__).parent.parent.parent  # Go up to prompt-config-service root
    yaml_path = current_dir / "seed" / "initial_data.yaml"
    
    # Try YAML first, fallback to JSON if not found
    if not yaml_path.exists():
        json_path = current_dir / "seed" / "initial_data.json"
        if json_path.exists():
            import json
            with open(json_path, "r", encoding="utf-8") as file:
                return json.load(file)
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
        
        for value_data in placeholder_data["values"]:
            value_id = uuid.uuid4()
            # Store mapping for later use in profiles
            value_key = f"{placeholder_data['name']}:{value_data['value']}"
            placeholder_value_ids[value_key] = value_id
            
            values_data.append({
                "id": value_id,
                "placeholder_id": placeholder_id,
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
    for profile_data in data["profiles"]:
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
    for profile_data in data["profiles"]:
        profile_id = profile_ids[profile_data["name"]]
        
        for placeholder_name, value_text in profile_data["settings"].items():
            if placeholder_name not in placeholder_ids:
                print(f"Warning: Placeholder {placeholder_name} not found for profile {profile_data['name']}")
                continue
            
            placeholder_id = placeholder_ids[placeholder_name]
            value_key = f"{placeholder_name}:{value_text}"
            
            if value_key not in placeholder_value_ids:
                print(f"Warning: Value '{value_text}' not found for placeholder {placeholder_name}")
                continue
            
            value_id = placeholder_value_ids[value_key]
            
            settings_data.append({
                "profile_id": profile_id,
                "placeholder_id": placeholder_id,
                "placeholder_value_id": value_id,
                "created_at": datetime.utcnow()
            })
    
    # Insert profile settings
    if settings_data:
        op.bulk_insert(profile_settings_table, settings_data)
    
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
