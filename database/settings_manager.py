"""
Settings Manager for Mistral OCR App
Handles all database operations for user settings and profiles
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

class SettingsManager:
    def __init__(self, db_path='settings.db'):
        self.db_path = db_path
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Ensure database exists and is initialized"""
        if not os.path.exists(self.db_path):
            from .init_db import init_database
            init_database(self.db_path)
    
    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        return conn
    
    def _log_change(self, setting_key: str, old_value: str, new_value: str, 
                   changed_by: str = 'system', change_reason: str = None):
        """Log setting changes for audit trail"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO settings_history 
            (setting_key, old_value, new_value, changed_by, change_reason)
            VALUES (?, ?, ?, ?, ?)
        ''', (setting_key, old_value, new_value, changed_by, change_reason))
        
        conn.commit()
        conn.close()
    
    # Settings CRUD Operations
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a single setting value"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT setting_value, setting_type FROM user_settings 
            WHERE setting_key = ?
        ''', (key,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result is None:
            return default
        
        value, setting_type = result
        return self._convert_value(value, setting_type)
    
    def set_setting(self, key: str, value: Any, setting_type: str = None, 
                   description: str = None, category: str = 'general',
                   changed_by: str = 'user', change_reason: str = None) -> bool:
        """Set a setting value"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get old value for logging
        old_value = self.get_setting(key)
        
        # Convert value to string for storage
        str_value = str(value).lower() if isinstance(value, bool) else str(value)
        
        # Auto-detect type if not provided
        if setting_type is None:
            setting_type = self._detect_type(value)
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_settings 
            (setting_key, setting_value, setting_type, description, category, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (key, str_value, setting_type, description, category))
        
        conn.commit()
        conn.close()
        
        # Log the change
        self._log_change(key, str(old_value), str_value, changed_by, change_reason)
        
        return True
    
    def get_settings_by_category(self, category: str) -> Dict[str, Any]:
        """Get all settings in a category"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT setting_key, setting_value, setting_type, description
            FROM user_settings 
            WHERE category = ?
            ORDER BY setting_key
        ''', (category,))
        
        results = cursor.fetchall()
        conn.close()
        
        settings = {}
        for row in results:
            key = row['setting_key']
            value = self._convert_value(row['setting_value'], row['setting_type'])
            settings[key] = {
                'value': value,
                'type': row['setting_type'],
                'description': row['description']
            }
        
        return settings
    
    def get_all_settings(self) -> Dict[str, Dict[str, Any]]:
        """Get all settings grouped by category"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT category, setting_key, setting_value, setting_type, description
            FROM user_settings 
            ORDER BY category, setting_key
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        settings = {}
        for row in results:
            category = row['category']
            key = row['setting_key']
            value = self._convert_value(row['setting_value'], row['setting_type'])
            
            if category not in settings:
                settings[category] = {}
            
            settings[category][key] = {
                'value': value,
                'type': row['setting_type'],
                'description': row['description']
            }
        
        return settings
    
    def update_multiple_settings(self, settings: Dict[str, Any], 
                                changed_by: str = 'user', 
                                change_reason: str = 'bulk_update') -> bool:
        """Update multiple settings at once"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            for key, value in settings.items():
                # Get old value for logging
                old_value = self.get_setting(key)
                
                # Convert value to string for storage
                str_value = str(value).lower() if isinstance(value, bool) else str(value)
                setting_type = self._detect_type(value)
                
                cursor.execute('''
                    UPDATE user_settings 
                    SET setting_value = ?, setting_type = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE setting_key = ?
                ''', (str_value, setting_type, key))
                
                # Log the change
                self._log_change(key, str(old_value), str_value, changed_by, change_reason)
            
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def delete_setting(self, key: str, changed_by: str = 'user') -> bool:
        """Delete a setting"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get old value for logging
        old_value = self.get_setting(key)
        
        cursor.execute('DELETE FROM user_settings WHERE setting_key = ?', (key,))
        
        if cursor.rowcount > 0:
            conn.commit()
            self._log_change(key, str(old_value), None, changed_by, 'deleted')
            result = True
        else:
            result = False
        
        conn.close()
        return result
    
    # Profile Operations
    def create_profile(self, name: str, settings: Dict[str, Any], 
                      description: str = None, is_default: bool = False) -> bool:
        """Create a new settings profile"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # If this is set as default, unset other defaults
        if is_default:
            cursor.execute('UPDATE settings_profiles SET is_default = FALSE')
        
        profile_data = json.dumps(settings)
        
        try:
            cursor.execute('''
                INSERT INTO settings_profiles 
                (profile_name, profile_data, is_default, description)
                VALUES (?, ?, ?, ?)
            ''', (name, profile_data, is_default, description))
            
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Profile name already exists
        finally:
            conn.close()
    
    def get_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a settings profile"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT profile_data, description, is_default, created_at, updated_at
            FROM settings_profiles 
            WHERE profile_name = ?
        ''', (name,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result is None:
            return None
        
        return {
            'name': name,
            'settings': json.loads(result['profile_data']),
            'description': result['description'],
            'is_default': bool(result['is_default']),
            'created_at': result['created_at'],
            'updated_at': result['updated_at']
        }
    
    def get_all_profiles(self) -> List[Dict[str, Any]]:
        """Get all settings profiles"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT profile_name, profile_data, description, is_default, created_at, updated_at
            FROM settings_profiles 
            ORDER BY is_default DESC, profile_name
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        profiles = []
        for row in results:
            profiles.append({
                'name': row['profile_name'],
                'settings': json.loads(row['profile_data']),
                'description': row['description'],
                'is_default': bool(row['is_default']),
                'created_at': row['created_at'],
                'updated_at': row['updated_at']
            })
        
        return profiles
    
    def apply_profile(self, name: str, changed_by: str = 'user') -> bool:
        """Apply a settings profile"""
        profile = self.get_profile(name)
        if profile is None:
            return False
        
        return self.update_multiple_settings(
            profile['settings'], 
            changed_by, 
            f'applied_profile_{name}'
        )
    
    def update_profile(self, name: str, settings: Dict[str, Any], 
                      description: str = None, is_default: bool = None) -> bool:
        """Update an existing profile"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # If this is set as default, unset other defaults
        if is_default:
            cursor.execute('UPDATE settings_profiles SET is_default = FALSE')
        
        profile_data = json.dumps(settings)
        
        # Build update query dynamically
        update_fields = ['profile_data = ?', 'updated_at = CURRENT_TIMESTAMP']
        params = [profile_data]
        
        if description is not None:
            update_fields.append('description = ?')
            params.append(description)
        
        if is_default is not None:
            update_fields.append('is_default = ?')
            params.append(is_default)
        
        params.append(name)
        
        cursor.execute(f'''
            UPDATE settings_profiles 
            SET {', '.join(update_fields)}
            WHERE profile_name = ?
        ''', params)
        
        result = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return result
    
    def delete_profile(self, name: str) -> bool:
        """Delete a settings profile"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM settings_profiles WHERE profile_name = ?', (name,))
        
        result = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return result
    
    def get_default_profile(self) -> Optional[Dict[str, Any]]:
        """Get the default settings profile"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT profile_name, profile_data, description, created_at, updated_at
            FROM settings_profiles 
            WHERE is_default = TRUE
            LIMIT 1
        ''')
        
        result = cursor.fetchone()
        conn.close()
        
        if result is None:
            return None
        
        return {
            'name': result['profile_name'],
            'settings': json.loads(result['profile_data']),
            'description': result['description'],
            'is_default': True,
            'created_at': result['created_at'],
            'updated_at': result['updated_at']
        }
    
    # Utility Methods
    def _convert_value(self, value: str, setting_type: str) -> Any:
        """Convert string value to appropriate type"""
        if setting_type == 'boolean':
            return value.lower() in ('true', '1', 'yes', 'on')
        elif setting_type == 'integer':
            try:
                return int(value)
            except ValueError:
                return 0
        elif setting_type == 'float':
            try:
                return float(value)
            except ValueError:
                return 0.0
        else:
            return value
    
    def _detect_type(self, value: Any) -> str:
        """Auto-detect setting type from value"""
        if isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, int):
            return 'integer'
        elif isinstance(value, float):
            return 'float'
        else:
            return 'string'
    
    def export_settings(self, include_profiles: bool = True) -> Dict[str, Any]:
        """Export all settings and profiles to a dictionary"""
        export_data = {
            'settings': self.get_all_settings(),
            'exported_at': datetime.now().isoformat()
        }
        
        if include_profiles:
            export_data['profiles'] = self.get_all_profiles()
        
        return export_data
    
    def import_settings(self, data: Dict[str, Any], 
                       overwrite: bool = False, 
                       changed_by: str = 'import') -> bool:
        """Import settings and profiles from a dictionary"""
        try:
            # Import settings
            if 'settings' in data:
                for category, settings in data['settings'].items():
                    for key, setting_info in settings.items():
                        if overwrite or self.get_setting(key) is None:
                            self.set_setting(
                                key, 
                                setting_info['value'],
                                setting_info.get('type'),
                                setting_info.get('description'),
                                category,
                                changed_by,
                                'imported'
                            )
            
            # Import profiles
            if 'profiles' in data:
                for profile in data['profiles']:
                    if overwrite:
                        # Delete existing profile if it exists
                        self.delete_profile(profile['name'])
                    
                    self.create_profile(
                        profile['name'],
                        profile['settings'],
                        profile.get('description'),
                        profile.get('is_default', False)
                    )
            
            return True
        except Exception as e:
            print(f"Error importing settings: {e}")
            return False
    
    def get_settings_history(self, setting_key: str = None, 
                           limit: int = 100) -> List[Dict[str, Any]]:
        """Get settings change history"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if setting_key:
            cursor.execute('''
                SELECT * FROM settings_history 
                WHERE setting_key = ?
                ORDER BY changed_at DESC
                LIMIT ?
            ''', (setting_key, limit))
        else:
            cursor.execute('''
                SELECT * FROM settings_history 
                ORDER BY changed_at DESC
                LIMIT ?
            ''', (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        history = []
        for row in results:
            history.append({
                'id': row['id'],
                'setting_key': row['setting_key'],
                'old_value': row['old_value'],
                'new_value': row['new_value'],
                'changed_by': row['changed_by'],
                'change_reason': row['change_reason'],
                'changed_at': row['changed_at']
            })
        
        return history
    
    def reset_to_defaults(self, category: str = None, 
                         changed_by: str = 'user') -> bool:
        """Reset settings to default values"""
        # This would require storing default values separately
        # For now, we'll recreate the database
        try:
            if category:
                # Reset specific category
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM user_settings WHERE category = ?', (category,))
                conn.commit()
                conn.close()
            else:
                # Reset all settings
                if os.path.exists(self.db_path):
                    os.remove(self.db_path)
                self._ensure_db_exists()
            
            return True
        except Exception as e:
            print(f"Error resetting settings: {e}")
            return False
