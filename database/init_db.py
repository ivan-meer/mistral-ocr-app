"""
Database initialization for Mistral OCR App settings
"""
import sqlite3
import os
from datetime import datetime

def init_database(db_path='settings.db'):
    """Initialize the settings database with required tables"""
    
    # Create database directory if it doesn't exist
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create user_settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT UNIQUE NOT NULL,
            setting_value TEXT NOT NULL,
            setting_type TEXT NOT NULL DEFAULT 'string',
            description TEXT,
            category TEXT DEFAULT 'general',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create settings_profiles table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name TEXT UNIQUE NOT NULL,
            profile_data TEXT NOT NULL,
            is_default BOOLEAN DEFAULT FALSE,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create settings_history table for audit trail
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT DEFAULT 'system',
            change_reason TEXT,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insert default settings
    default_settings = [
        # API Settings
        ('api_provider', 'mistral', 'string', 'OCR API provider', 'api'),
        ('mistral_api_key', '', 'string', 'Mistral AI API key', 'api'),
        ('use_mock_ocr', 'true', 'boolean', 'Use demo mode for OCR', 'api'),
        ('api_timeout', '30', 'integer', 'API request timeout in seconds', 'api'),
        ('max_retries', '3', 'integer', 'Maximum API retry attempts', 'api'),
        
        # File Processing Settings
        ('max_file_size_mb', '50', 'integer', 'Maximum file size in MB', 'processing'),
        ('allowed_extensions', 'pdf,png,jpg,jpeg,docx', 'string', 'Allowed file extensions', 'processing'),
        ('include_images_default', 'true', 'boolean', 'Extract images by default', 'processing'),
        ('image_quality', 'high', 'string', 'Image extraction quality', 'processing'),
        ('auto_cleanup', 'true', 'boolean', 'Auto cleanup temporary files', 'processing'),
        
        # UI Settings
        ('theme', 'dark', 'string', 'Application theme', 'ui'),
        ('language', 'ru', 'string', 'Interface language', 'ui'),
        ('font_size', 'medium', 'string', 'Font size preference', 'ui'),
        ('animations_enabled', 'true', 'boolean', 'Enable UI animations', 'ui'),
        ('compact_mode', 'false', 'boolean', 'Use compact interface', 'ui'),
        
        # Visualization Settings
        ('markdown_syntax_highlighting', 'true', 'boolean', 'Enable syntax highlighting', 'visualization'),
        ('markdown_line_numbers', 'false', 'boolean', 'Show line numbers in code', 'visualization'),
        ('image_lazy_loading', 'true', 'boolean', 'Enable lazy loading for images', 'visualization'),
        ('image_zoom_enabled', 'true', 'boolean', 'Enable image zoom on click', 'visualization'),
        ('results_animation', 'true', 'boolean', 'Animate results appearance', 'visualization'),
        
        # Export Settings
        ('default_export_format', 'markdown', 'string', 'Default export format', 'export'),
        ('include_metadata', 'true', 'boolean', 'Include metadata in exports', 'export'),
        ('preserve_formatting', 'true', 'boolean', 'Preserve original formatting', 'export'),
        ('watermark_enabled', 'false', 'boolean', 'Add watermark to exports', 'export'),
        
        # Performance Settings
        ('cache_enabled', 'true', 'boolean', 'Enable result caching', 'performance'),
        ('cache_duration_hours', '24', 'integer', 'Cache duration in hours', 'performance'),
        ('parallel_processing', 'false', 'boolean', 'Enable parallel processing', 'performance'),
        ('memory_limit_mb', '512', 'integer', 'Memory limit in MB', 'performance'),
        
        # Security Settings
        ('log_requests', 'true', 'boolean', 'Log API requests', 'security'),
        ('anonymize_logs', 'true', 'boolean', 'Anonymize sensitive data in logs', 'security'),
        ('session_timeout_minutes', '60', 'integer', 'Session timeout in minutes', 'security'),
        ('rate_limit_enabled', 'true', 'boolean', 'Enable rate limiting', 'security'),
    ]
    
    for setting_key, setting_value, setting_type, description, category in default_settings:
        cursor.execute('''
            INSERT OR IGNORE INTO user_settings 
            (setting_key, setting_value, setting_type, description, category)
            VALUES (?, ?, ?, ?, ?)
        ''', (setting_key, setting_value, setting_type, description, category))
    
    # Insert default profiles
    default_profiles = [
        ('Default', '{"theme": "dark", "include_images_default": true, "markdown_syntax_highlighting": true}', True, 'Default application settings'),
        ('Academic', '{"theme": "light", "include_images_default": true, "markdown_line_numbers": true, "preserve_formatting": true}', False, 'Settings optimized for academic documents'),
        ('Business', '{"theme": "dark", "compact_mode": true, "watermark_enabled": true, "include_metadata": true}', False, 'Settings optimized for business documents'),
        ('Performance', '{"cache_enabled": true, "parallel_processing": true, "image_lazy_loading": true, "animations_enabled": false}', False, 'Settings optimized for performance'),
    ]
    
    for profile_name, profile_data, is_default, description in default_profiles:
        cursor.execute('''
            INSERT OR IGNORE INTO settings_profiles 
            (profile_name, profile_data, is_default, description)
            VALUES (?, ?, ?, ?)
        ''', (profile_name, profile_data, is_default, description))
    
    # Create indexes for better performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_settings_key ON user_settings(setting_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_settings_category ON user_settings(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_profiles_name ON settings_profiles(profile_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_key ON settings_history(setting_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_date ON settings_history(changed_at)')
    
    conn.commit()
    conn.close()
    
    print(f"Database initialized successfully at: {os.path.abspath(db_path)}")
    return True

if __name__ == '__main__':
    init_database()
