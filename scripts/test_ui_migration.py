#!/usr/bin/env python3
"""
Script for quick UI testing by adding display_names to existing sessions.
Use this to test the new UI without running the full workflow.
"""

import json
from pathlib import Path
from datetime import datetime

# Path to artifacts data
DATA_PATH = Path("data/artifacts")

# Test display_names for demonstration
TEST_DISPLAY_NAMES = {
    "979557959": {
        "session-20250812_194751-bb111996": "RSA шифрование основы",
        "session-20250818_095712-bb111996": "Эллиптические кривые криптография"
    }
}

def generate_display_name_from_question(exam_question: str) -> str:
    """
    Generate a simple display_name from exam_question.
    Takes first 5 words or 50 characters, whichever is shorter.
    """
    if not exam_question:
        return "Unnamed Session"
    
    # Take first 5 words
    words = exam_question.split()[:5]
    display_name = " ".join(words)
    
    # Limit to 50 characters
    if len(display_name) > 50:
        display_name = display_name[:47] + "..."
    
    return display_name

def update_session_metadata(thread_id: str, session_id: str) -> bool:
    """
    Updates session metadata by adding display_name field.
    
    Args:
        thread_id: Thread identifier
        session_id: Session identifier
        
    Returns:
        True if updated successfully, False otherwise
    """
    session_path = DATA_PATH / thread_id / "sessions" / session_id
    metadata_path = session_path / "session_metadata.json"
    
    try:
        # Read existing metadata or create new
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        else:
            # Create basic metadata if doesn't exist
            metadata = {
                "session_id": session_id,
                "thread_id": thread_id,
                "exam_question": "Test exam question",
                "created": datetime.now().isoformat(),
                "modified": datetime.now().isoformat(),
                "status": "active"
            }
    
        # Skip if display_name already exists
        if "display_name" in metadata and metadata["display_name"]:
            print(f"  ⏭️  {thread_id}/{session_id}: already has display_name")
            return False
        
        # Add display_name
        if thread_id in TEST_DISPLAY_NAMES and session_id in TEST_DISPLAY_NAMES[thread_id]:
            # Use predefined test name
            metadata["display_name"] = TEST_DISPLAY_NAMES[thread_id][session_id]
        else:
            # Generate from exam_question
            exam_question = metadata.get("exam_question", "")
            metadata["display_name"] = generate_display_name_from_question(exam_question)
        
        # Save updated metadata
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        print(f"  ✅ {thread_id}/{session_id}: {metadata.get('display_name')}")
        return True
        
    except Exception as e:
        print(f"  ❌ {thread_id}/{session_id}: Error - {e}")
        return False

def migrate_all_sessions():
    """
    Iterate through all threads and sessions, adding display_names.
    """
    if not DATA_PATH.exists():
        print(f"❌ Data path {DATA_PATH} does not exist!")
        print("  Please ensure the artifacts service has been run at least once.")
        return
    
    print(f"🔍 Scanning {DATA_PATH} for sessions...")
    print()
    
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    # Iterate through all thread directories
    for thread_dir in DATA_PATH.iterdir():
        if not thread_dir.is_dir():
            continue
        
        thread_id = thread_dir.name
        sessions_dir = thread_dir / "sessions"
        
        if not sessions_dir.exists():
            continue
        
        print(f"📁 Thread: {thread_id}")
        
        # Iterate through all session directories
        for session_dir in sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            
            session_id = session_dir.name
            result = update_session_metadata(thread_id, session_id)
            
            if result:
                updated_count += 1
            elif result is False:
                skipped_count += 1
            else:
                error_count += 1
        
        print()
    
    # Summary
    print("=" * 50)
    print("📊 Migration Summary:")
    print(f"  ✅ Updated: {updated_count} sessions")
    print(f"  ⏭️  Skipped: {skipped_count} sessions (already had display_name)")
    print(f"  ❌ Errors: {error_count} sessions")
    print()
    
    if updated_count > 0:
        print("✨ Migration completed successfully!")
        print("   You can now test the new UI with improved session names.")
    else:
        print("ℹ️  No sessions were updated.")
    
    print()
    print("To start the web UI:")
    print("  cd web-ui && npm run dev")

def main():
    """Main entry point."""
    print()
    print("🚀 LearnFlow AI - Test UI Migration Script")
    print("=" * 50)
    print()
    print("This script adds display_name fields to existing sessions")
    print("for testing the new accordion UI without running the full workflow.")
    print()
    
    migrate_all_sessions()

if __name__ == "__main__":
    main()