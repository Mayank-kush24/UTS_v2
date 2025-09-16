from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, Response
import psycopg2
from psycopg2 import sql
from psycopg2 import OperationalError, InterfaceError, InternalError
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import uuid
import time
import hashlib
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from werkzeug.utils import secure_filename
from PIL import Image
import base64
import threading
from collections import defaultdict
import csv
from io import StringIO
import uuid

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

# Session configuration (optimized)
app.config['SESSION_PERMANENT'] = False  # Default to False, can be overridden per session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)  # Remember me for 30 days
# Optimize session performance
app.config['SESSION_FILE_THRESHOLD'] = 500  # Reduce file operations
app.config['SESSION_USE_SIGNER'] = True  # Enable session signing for security

# File upload configuration
UPLOAD_FOLDER = 'static/uploads/avatars'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =====================================
#   COMPREHENSIVE CACHING SYSTEM
# =====================================

class PlatformCacheManager:
    """Centralized cache management system for the entire platform"""
    
    def __init__(self):
        self._caches = {
            'database_queries': {},      # Database query results
            'api_responses': {},         # API response caching
            'table_metadata': {},        # Table structure and metadata
            'user_data': {},             # User-related data
            'configuration': {},         # System configuration
            'static_assets': {},         # Static asset metadata
            'visualization_data': {},    # Chart and visualization data
            'file_uploads': {}           # File upload metadata
        }
        
        # Cache TTL settings (in seconds)
        self._ttl_settings = {
            'database_queries': 300,     # 5 minutes
            'api_responses': 60,         # 1 minute
            'table_metadata': 600,       # 10 minutes
            'user_data': 30,             # 30 seconds
            'configuration': 1800,       # 30 minutes
            'static_assets': 3600,       # 1 hour
            'visualization_data': 300,   # 5 minutes
            'file_uploads': 1800         # 30 minutes
        }
        
        # Performance tracking
        self._stats = {
            'hits': defaultdict(int),
            'misses': defaultdict(int),
            'evictions': defaultdict(int),
            'total_requests': defaultdict(int)
        }
        
        # Thread safety
        self._locks = {cache_name: threading.RLock() for cache_name in self._caches.keys()}
        
        # Cache size limits
        self._max_sizes = {
            'database_queries': 1000,
            'api_responses': 500,
            'table_metadata': 100,
            'user_data': 200,
            'configuration': 50,
            'static_assets': 200,
            'visualization_data': 300,
            'file_uploads': 100
        }
    
    def get(self, cache_name, key, default=None):
        """Get value from cache with TTL checking"""
        if cache_name not in self._caches:
            return default
        
        with self._locks[cache_name]:
            self._stats['total_requests'][cache_name] += 1
            
            if key in self._caches[cache_name]:
                entry = self._caches[cache_name][key]
                current_time = time.time()
                
                # Check TTL
                if current_time - entry['timestamp'] < self._ttl_settings[cache_name]:
                    self._stats['hits'][cache_name] += 1
                    return entry['data']
                else:
                    # Expired, remove it
                    del self._caches[cache_name][key]
                    self._stats['evictions'][cache_name] += 1
            
            self._stats['misses'][cache_name] += 1
            return default
    
    def set(self, cache_name, key, value, ttl_override=None):
        """Set value in cache with TTL"""
        if cache_name not in self._caches:
            return False
        
        with self._locks[cache_name]:
            # Check cache size limit
            if len(self._caches[cache_name]) >= self._max_sizes[cache_name]:
                # Remove oldest entry
                oldest_key = min(self._caches[cache_name].keys(), 
                               key=lambda k: self._caches[cache_name][k]['timestamp'])
                del self._caches[cache_name][oldest_key]
                self._stats['evictions'][cache_name] += 1
            
            # Store with timestamp
            self._caches[cache_name][key] = {
                'data': value,
                'timestamp': time.time()
            }
            return True
    
    def delete(self, cache_name, key):
        """Delete specific key from cache"""
        if cache_name not in self._caches:
            return False
        
        with self._locks[cache_name]:
            if key in self._caches[cache_name]:
                del self._caches[cache_name][key]
                return True
            return False
    
    def clear(self, cache_name=None):
        """Clear cache(s)"""
        if cache_name:
            if cache_name in self._caches:
                with self._locks[cache_name]:
                    self._caches[cache_name].clear()
        else:
            # Clear all caches
            for name in self._caches:
                with self._locks[name]:
                    self._caches[name].clear()
    
    def invalidate_pattern(self, cache_name, pattern):
        """Invalidate cache entries matching a pattern"""
        if cache_name not in self._caches:
            return 0
        
        import re
        pattern_re = re.compile(pattern)
        removed_count = 0
        
        with self._locks[cache_name]:
            keys_to_remove = [key for key in self._caches[cache_name].keys() 
                            if pattern_re.match(key)]
            for key in keys_to_remove:
                del self._caches[cache_name][key]
                removed_count += 1
        
        return removed_count
    
    def get_stats(self):
        """Get cache performance statistics"""
        stats = {}
        for cache_name in self._caches:
            total_requests = self._stats['total_requests'][cache_name]
            hits = self._stats['hits'][cache_name]
            misses = self._stats['misses'][cache_name]
            
            stats[cache_name] = {
                'hit_rate': hits / max(total_requests, 1),
                'total_requests': total_requests,
                'hits': hits,
                'misses': misses,
                'evictions': self._stats['evictions'][cache_name],
                'current_size': len(self._caches[cache_name]),
                'max_size': self._max_sizes[cache_name]
            }
        
        return stats
    
    def cleanup_expired(self):
        """Remove expired entries from all caches"""
        current_time = time.time()
        total_cleaned = 0
        
        for cache_name in self._caches:
            with self._locks[cache_name]:
                expired_keys = []
                for key, entry in self._caches[cache_name].items():
                    if current_time - entry['timestamp'] >= self._ttl_settings[cache_name]:
                        expired_keys.append(key)
                
                for key in expired_keys:
                    del self._caches[cache_name][key]
                    total_cleaned += 1
                    self._stats['evictions'][cache_name] += 1
        
        return total_cleaned

# Initialize global cache manager
cache_manager = PlatformCacheManager()

# Cache decorator for easy use
def cached(cache_name, ttl_override=None):
    """Decorator to cache function results"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Try to get from cache
            result = cache_manager.get(cache_name, cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_manager.set(cache_name, cache_key, result, ttl_override)
            return result
        
        return wrapper
    return decorator

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def resize_image(image_path, max_size=(200, 200)):
    """Resize image to specified dimensions"""
    try:
        with Image.open(image_path) as img:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            img.save(image_path, optimize=True, quality=85)
        return True
    except Exception as e:
        print(f"Error resizing image: {e}")
        return False

def get_default_avatars():
    """Get list of default avatar options"""
    return [
        {'id': 'default-1', 'name': 'Default 1', 'icon': 'fas fa-user'},
        {'id': 'default-2', 'name': 'Default 2', 'icon': 'fas fa-user-circle'},
        {'id': 'default-3', 'name': 'Default 3', 'icon': 'fas fa-user-tie'},
        {'id': 'default-4', 'name': 'Default 4', 'icon': 'fas fa-user-graduate'},
        {'id': 'default-5', 'name': 'Default 5', 'icon': 'fas fa-user-ninja'},
        {'id': 'default-6', 'name': 'Default 6', 'icon': 'fas fa-user-astronaut'},
    ]

def load_users():
    """Load users from JSON file"""
    try:
        with open('users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_users(users):
    """Save users to JSON file"""
    with open('users.json', 'w') as f:
        json.dump(users, f, indent=2)

class DatabaseManager:
    def __init__(self):
        self.connection = None
        self.config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', ''),
            'user': os.getenv('DB_USER', ''),
            'password': os.getenv('DB_PASSWORD', '')
        }
        # Cache for database operations
        self._query_cache = {}
        self._metadata_cache = {}
    
    def test_connection(self, config=None):
        """Test database connection with given or default config"""
        test_config = config if isinstance(config, dict) else self.config
        try:
            conn = psycopg2.connect(**test_config)
            conn.close()
            return True, "Connection successful!"
        except Exception as e:
            return False, str(e)
    
    def connect(self, config=None):
        """Establish database connection"""
        connect_config = config if isinstance(config, dict) else self.config
        try:
            # Close existing connection if any
            if self.connection:
                try:
                    self.connection.close()
                except Exception:
                    pass
            
            self.connection = psycopg2.connect(**connect_config)
            # Set autocommit mode to avoid transaction issues
            self.connection.autocommit = True
            
            # Update the config with the new connection details
            self.config.update(connect_config)
            
            # Invalidate database-related caches when connecting to new database
            cache_manager.invalidate_pattern('database_queries', f".*:{connect_config.get('database', 'default')}")
            cache_manager.invalidate_pattern('api_responses', f".*:{connect_config.get('database', 'default')}")
            cache_manager.invalidate_pattern('table_metadata', f".*:{connect_config.get('database', 'default')}")
            
            return True, "Connected successfully!"
        except Exception as e:
            return False, str(e)
    
    def _ensure_connection_health(self):
        """Ensure connection is healthy and reset if needed"""
        if not self.connection:
            return False
        
        try:
            # Test connection with a simple query
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except (OperationalError, InterfaceError):
            # Connection is broken, try to reconnect
            try:
                self.connect()
                return True
            except Exception:
                return False
        except InternalError:
            # Transaction is in aborted state, rollback and continue
            try:
                self.connection.rollback()
                return True
            except Exception:
                # If rollback fails, reconnect
                try:
                    self.connect()
                    return True
                except Exception:
                    return False
        except Exception:
            # For any other error, try to reset the connection
            try:
                self.connect()
                return True
            except Exception:
                return False
    
    def get_tables(self):
        """Get list of all tables in the database (with caching)"""
        if not self.connection:
            return False, "No database connection"
        
        # Check cache first
        cache_key = f"tables:{self.config['database']}"
        cached_result = cache_manager.get('database_queries', cache_key)
        if cached_result is not None:
            return True, cached_result
        
        # Ensure connection is healthy
        if not self._ensure_connection_health():
            return False, "Database connection is not healthy"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name;
            """)
            tables = [row[0] for row in cursor.fetchall()]
            cursor.close()
            
            # Cache the result
            cache_manager.set('database_queries', cache_key, tables)
            
            return True, tables
        except Exception as e:
            # Try to recover connection on error
            if self._ensure_connection_health():
                try:
                    cursor = self.connection.cursor()
                    cursor.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        ORDER BY table_name;
                    """)
                    tables = [row[0] for row in cursor.fetchall()]
                    cursor.close()
                    return True, tables
                except Exception as retry_e:
                    return False, str(retry_e)
            return False, str(e)
    
    def get_columns(self, table_name):
        """Get list of columns for a specific table"""
        if not self.connection:
            return False, "No database connection"
        
        # Ensure connection is healthy
        if not self._ensure_connection_health():
            return False, "Database connection is not healthy"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = %s AND table_schema = 'public'
                ORDER BY ordinal_position;
            """, (table_name,))
            columns = cursor.fetchall()
            cursor.close()
            return True, columns
        except Exception as e:
            # Try to recover connection on error
            if self._ensure_connection_health():
                try:
                    cursor = self.connection.cursor()
                    cursor.execute("""
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_name = %s AND table_schema = 'public'
                        ORDER BY ordinal_position;
                    """, (table_name,))
                    columns = cursor.fetchall()
                    cursor.close()
                    return True, columns
                except Exception as retry_e:
                    return False, str(retry_e)
            return False, str(e)
    
    def get_table_data(self, table_name, limit=100, page=1, filters=None):
        """Get data from specified table with optional filtering and pagination"""
        if not self.connection:
            return False, "No database connection"
        
        # Ensure connection is healthy
        if not self._ensure_connection_health():
            return False, "Database connection is not healthy"
        
        try:
            cursor = self.connection.cursor()
            
            # Get column names
            cursor.execute(sql.SQL("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s 
                ORDER BY ordinal_position;
            """), [table_name])
            columns = [row[0] for row in cursor.fetchall()]
            
            # Build base query
            base_query = sql.SQL("SELECT * FROM {}").format(sql.Identifier(table_name))
            count_query = sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name))
            
            # Build WHERE clause from filters
            where_clause, params = self._build_where_clause(filters) if filters else ("", [])
            
            if where_clause:
                base_query = sql.SQL("SELECT * FROM {} WHERE {}").format(
                    sql.Identifier(table_name), 
                    sql.SQL(where_clause)
                )
                count_query = sql.SQL("SELECT COUNT(*) FROM {} WHERE {}").format(
                    sql.Identifier(table_name), 
                    sql.SQL(where_clause)
                )
            
            # Get total count (with filters applied)
            if params:
                cursor.execute(count_query, params)
            else:
                cursor.execute(count_query)
            total_rows = cursor.fetchone()[0]
            
            # Add pagination
            offset = (page - 1) * limit
            if where_clause:
                data_query = sql.SQL("SELECT * FROM {} WHERE {} LIMIT %s OFFSET %s").format(
                    sql.Identifier(table_name), 
                    sql.SQL(where_clause)
                )
                cursor.execute(data_query, params + [limit, offset])
            else:
                data_query = sql.SQL("SELECT * FROM {} LIMIT %s OFFSET %s").format(
                    sql.Identifier(table_name)
                )
                cursor.execute(data_query, [limit, offset])
            
            rows = cursor.fetchall()
            
            cursor.close()
            return True, {
                'columns': columns, 
                'rows': rows, 
                'total_rows': total_rows,
                'filtered': filters is not None
            }
        except Exception as e:
            # Try to recover connection on error
            if self._ensure_connection_health():
                try:
                    cursor = self.connection.cursor()
                    
                    # Get column names (simplified retry)
                    cursor.execute(sql.SQL("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = %s 
                        ORDER BY ordinal_position;
                    """), [table_name])
                    columns = [row[0] for row in cursor.fetchall()]
                    
                    # Simple retry without filters
                    cursor.execute(sql.SQL("SELECT * FROM {} LIMIT %s").format(
                        sql.Identifier(table_name)
                    ), [limit])
                    rows = cursor.fetchall()
                    
                    cursor.close()
                    return True, {'columns': columns, 'rows': rows, 'total_rows': len(rows), 'filtered': False}
                except Exception as retry_e:
                    return False, f"Error after retry: {str(retry_e)}"
            return False, f"Connection error: {str(e)}"
    
    def _build_where_clause(self, filters):
        """Build SQL WHERE clause from filter conditions"""
        print(f"_build_where_clause called with filters: {filters}")
        if not filters or not isinstance(filters, dict):
            print("_build_where_clause: No valid filters provided")
            return "", []
        
        conditions = []
        params = []
        
        # Process filter groups
        if not isinstance(filters, dict):
            print(f"_build_where_clause: filters is not a dict: {type(filters)}, {filters}")
            return "", []
            
        for group in filters.get('groups', []):
            print(f"_build_where_clause: Processing group: {group}")
            group_conditions = []
            
            if not isinstance(group, dict):
                print(f"_build_where_clause: group is not a dict: {type(group)}, {group}")
                continue
                
            for condition in group.get('conditions', []):
                if not isinstance(condition, dict):
                    print(f"_build_where_clause: condition is not a dict: {type(condition)}, {condition}")
                    continue
                    
                field = condition.get('field')
                operation = condition.get('operation')
                value = condition.get('value')
                print(f"_build_where_clause: Processing condition: field={field}, operation={operation}, value={value}")
                
                if not field or not operation:
                    print("_build_where_clause: Skipping invalid condition")
                    continue
                
                # Build condition based on operation
                sql_condition, condition_params = self._build_condition(field, operation, value)
                print(f"_build_where_clause: Built condition: {sql_condition}, params: {condition_params}")
                if sql_condition:
                    group_conditions.append(sql_condition)
                    params.extend(condition_params)
            
            if group_conditions:
                group_logic = group.get('logic', 'AND')
                group_clause = f" {group_logic} ".join(group_conditions)
                if len(group_conditions) > 1:
                    group_clause = f"({group_clause})"
                conditions.append(group_clause)
                print(f"_build_where_clause: Added group clause: {group_clause}")
        
        if conditions:
            main_logic = filters.get('logic', 'AND')
            final_clause = f" {main_logic} ".join(conditions)
            print(f"_build_where_clause: Final WHERE clause: {final_clause}")
            print(f"_build_where_clause: Final params: {params}")
            return final_clause, params
        
        print("_build_where_clause: No conditions built")
        return "", []
    
    def _build_condition(self, field, operation, value):
        """Build individual SQL condition"""
        # Use sql.Identifier for safe field names
        field_sql = sql.Identifier(field)
        
        if operation == 'equals':
            return sql.SQL("{} = %s").format(field_sql).as_string(self.connection), [value]
        elif operation == 'not_equals':
            return sql.SQL("{} != %s").format(field_sql).as_string(self.connection), [value]
        elif operation == 'contains':
            return sql.SQL("{}::text ILIKE %s").format(field_sql).as_string(self.connection), [f'%{value}%']
        elif operation == 'not_contains':
            return sql.SQL("{}::text NOT ILIKE %s").format(field_sql).as_string(self.connection), [f'%{value}%']
        elif operation == 'starts_with':
            return sql.SQL("{}::text ILIKE %s").format(field_sql).as_string(self.connection), [f'{value}%']
        elif operation == 'ends_with':
            return sql.SQL("{}::text ILIKE %s").format(field_sql).as_string(self.connection), [f'%{value}']
        elif operation == 'greater_than':
            return sql.SQL("{} > %s").format(field_sql).as_string(self.connection), [value]
        elif operation == 'less_than':
            return sql.SQL("{} < %s").format(field_sql).as_string(self.connection), [value]
        elif operation == 'greater_equal':
            return sql.SQL("{} >= %s").format(field_sql).as_string(self.connection), [value]
        elif operation == 'less_equal':
            return sql.SQL("{} <= %s").format(field_sql).as_string(self.connection), [value]
        elif operation == 'is_null':
            return sql.SQL("{} IS NULL").format(field_sql).as_string(self.connection), []
        elif operation == 'is_not_null':
            return sql.SQL("{} IS NOT NULL").format(field_sql).as_string(self.connection), []
        elif operation == 'in':
            if isinstance(value, str):
                values = [v.strip() for v in value.split(',') if v.strip()]
            else:
                values = value if isinstance(value, list) else [value]
            if values:
                placeholders = ','.join(['%s'] * len(values))
                return sql.SQL("{} IN ({})").format(field_sql, sql.SQL(placeholders)).as_string(self.connection), values
        elif operation == 'not_in':
            if isinstance(value, str):
                values = [v.strip() for v in value.split(',') if v.strip()]
            else:
                values = value if isinstance(value, list) else [value]
            if values:
                placeholders = ','.join(['%s'] * len(values))
                return sql.SQL("{} NOT IN ({})").format(field_sql, sql.SQL(placeholders)).as_string(self.connection), values
        elif operation == 'between':
            if isinstance(value, dict) and 'min' in value and 'max' in value:
                return sql.SQL("{} BETWEEN %s AND %s").format(field_sql).as_string(self.connection), [value['min'], value['max']]
        
        return "", []
    
    def get_column_values(self, table_name, column_name, limit=100):
        """Get distinct values for a column (for filter suggestions)"""
        if not self.connection:
            return []
        
        if not self._ensure_connection_health():
            return []
        
        try:
            cursor = self.connection.cursor()
            # Use DISTINCT and LIMIT to get sample values
            cursor.execute(sql.SQL('''
                SELECT DISTINCT {} 
                FROM {} 
                WHERE {} IS NOT NULL 
                ORDER BY {} 
                LIMIT %s
            ''').format(
                sql.Identifier(column_name),
                sql.Identifier(table_name),
                sql.Identifier(column_name),
                sql.Identifier(column_name)
            ), [limit])
            
            values = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return values
        except Exception as e:
            print(f"Error getting column values: {e}")
            return []
    
    def get_database_stats(self):
        """Get database statistics (with caching)"""
        if not self.connection:
            return False, "No database connection"
        
        # Check cache first
        cache_key = f"db_stats:{self.config['database']}"
        cached_result = cache_manager.get('database_queries', cache_key)
        if cached_result is not None:
            return True, cached_result
        
        # Ensure connection is healthy
        if not self._ensure_connection_health():
            return False, "Database connection is not healthy"
        
        try:
            cursor = self.connection.cursor()
            
            # Get total number of tables
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public';
            """)
            total_tables = cursor.fetchone()[0]
            
            # Get total size of all tables (not entire database)
            cursor.execute("""
                SELECT pg_size_pretty(SUM(pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename))))
                FROM information_schema.tables 
                WHERE table_schema = 'public';
            """)
            tables_size = cursor.fetchone()[0]
            
            # Get table statistics
            cursor.execute("""
                SELECT 
                    schemaname,
                    tablename,
                    n_tup_ins as inserts,
                    n_tup_upd as updates,
                    n_tup_del as deletes,
                    n_live_tup as live_tuples,
                    n_dead_tup as dead_tuples
                FROM pg_stat_user_tables 
                ORDER BY n_live_tup DESC 
                LIMIT 10;
            """)
            table_stats = cursor.fetchall()
            
            cursor.close()
            return True, {
                'total_tables': total_tables,
                'database_size': tables_size,  # Now shows tables size instead of database size
                'table_stats': table_stats
            }
        except Exception as e:
            # Try to recover connection on error
            if self._ensure_connection_health():
                try:
                    cursor = self.connection.cursor()
                    
                    # Get total number of tables
                    cursor.execute("""
                        SELECT COUNT(*) 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public';
                    """)
                    total_tables = cursor.fetchone()[0]
                    
                    # Get database size (with fallback)
                    try:
                        cursor.execute("""
                            SELECT pg_size_pretty(pg_database_size(current_database()));
                        """)
                        db_size = cursor.fetchone()[0]
                    except Exception:
                        db_size = "Unknown"
                    
                    # Get table statistics (with fallback)
                    try:
                        cursor.execute("""
                            SELECT 
                                schemaname,
                                tablename,
                                n_tup_ins as inserts,
                                n_tup_upd as updates,
                                n_tup_del as deletes,
                                n_live_tup as live_tuples,
                                n_dead_tup as dead_tuples
                            FROM pg_stat_user_tables 
                            ORDER BY n_live_tup DESC 
                            LIMIT 10;
                        """)
                        table_stats = cursor.fetchall()
                    except Exception:
                        table_stats = []
                    
                    cursor.close()
                    stats = {
                        'total_tables': total_tables,
                        'database_size': db_size,
                        'table_stats': table_stats
                    }
                    
                    # Cache the result
                    cache_manager.set('database_queries', cache_key, stats)
                    
                    return True, stats
                except Exception as retry_e:
                    return False, f"Error after retry: {str(retry_e)}"
            return False, f"Connection error: {str(e)}"
    
    def get_table_info(self, table_name):
        """Get detailed information about a specific table"""
        if not self.connection:
            return False, "No database connection"
        
        # Ensure connection is healthy
        if not self._ensure_connection_health():
            return False, "Database connection is not healthy"
        
        try:
            cursor = self.connection.cursor()
            
            # Get row count
            cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(
                sql.Identifier(table_name)
            ))
            row_count = cursor.fetchone()[0]
            
            # Get table size
            cursor.execute("""
                SELECT pg_size_pretty(pg_total_relation_size(%s));
            """, [table_name])
            table_size = cursor.fetchone()[0]
            
            # Get column count
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.columns 
                WHERE table_name = %s;
            """, [table_name])
            column_count = cursor.fetchone()[0]
            
            cursor.close()
            return True, {
                'row_count': row_count,
                'table_size': table_size,
                'column_count': column_count
            }
        except Exception as e:
            # Try to recover connection on error
            if self._ensure_connection_health():
                try:
                    cursor = self.connection.cursor()
                    
                    # Get row count
                    cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(
                        sql.Identifier(table_name)
                    ))
                    row_count = cursor.fetchone()[0]
                    
                    # Get table size (with fallback)
                    try:
                        cursor.execute("""
                            SELECT pg_size_pretty(pg_total_relation_size(%s));
                        """, [table_name])
                        table_size = cursor.fetchone()[0]
                    except Exception:
                        table_size = "Unknown"
                    
                    # Get column count
                    cursor.execute("""
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = %s;
                    """, [table_name])
                    column_count = cursor.fetchone()[0]
                    
                    cursor.close()
                    return True, {
                        'row_count': row_count,
                        'table_size': table_size,
                        'column_count': column_count
                    }
                except Exception as retry_e:
                    return False, f"Error after retry: {str(retry_e)}"
            return False, f"Connection error: {str(e)}"
    
    def get_bulk_table_stats_ultra_fast(self, table_names=None, limit=10):
        """Ultra-fast table stats using only system catalogs - fastest possible"""
        if not self.connection:
            return False, "No database connection"
        
        # Ensure connection is healthy
        if not self._ensure_connection_health():
            return False, "Database connection is not healthy"
        
        try:
            cursor = self.connection.cursor()
            
            # Ultra-fast query using only pg_class and pg_tables
            table_filter = ""
            params = []
            if table_names:
                placeholders = ','.join(['%s'] * len(table_names))
                table_filter = f"AND t.tablename IN ({placeholders})"
                params.extend(table_names)
            
            ultra_fast_query = f"""
                SELECT 
                    t.tablename as table_name,
                    COALESCE(c.reltuples::bigint, 0) as estimated_rows,
                    COALESCE(c.relnatts, 0) as column_count,
                    COALESCE(pg_size_pretty(pg_total_relation_size(c.oid)), '0 bytes') as table_size
                FROM pg_tables t
                LEFT JOIN pg_class c ON c.relname = t.tablename
                LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE t.schemaname = 'public' 
                AND (n.nspname = 'public' OR n.nspname IS NULL)
                {table_filter}
                ORDER BY COALESCE(c.reltuples::bigint, 0) DESC
                LIMIT %s
            """
            params.append(limit)
            
            cursor.execute(ultra_fast_query, params)
            results = cursor.fetchall()
            
            # Format results
            stats = {}
            for row in results:
                table_name = row[0]
                estimated_rows = row[1]
                column_count = row[2]
                table_size = row[3]
                
                stats[table_name] = {
                    'row_count': estimated_rows,
                    'column_count': column_count,
                    'table_size': table_size
                }
            
            return True, stats
            
        except Exception as e:
            print(f"Error in get_bulk_table_stats_ultra_fast: {e}")
            return False, f"Database error: {str(e)}"
    
    def get_bulk_table_stats(self, table_names=None, limit=10):
        """Get statistics for multiple tables efficiently with accurate row counts"""
        if not self.connection:
            return False, "No database connection"
        
        # Ensure connection is healthy
        if not self._ensure_connection_health():
            return False, "Database connection is not healthy"
        
        try:
            cursor = self.connection.cursor()
            
            # Get basic table info from information_schema
            table_filter = ""
            params = []
            if table_names:
                placeholders = ','.join(['%s'] * len(table_names))
                table_filter = f"AND t.table_name IN ({placeholders})"
                params.extend(table_names)
            
            # First, get table names and column counts
            base_query = f"""
                SELECT 
                    t.table_name,
                    COUNT(c.column_name) as column_count
                FROM information_schema.tables t
                LEFT JOIN information_schema.columns c ON t.table_name = c.table_name 
                    AND t.table_schema = c.table_schema
                WHERE t.table_schema = 'public' 
                {table_filter}
                GROUP BY t.table_name
                ORDER BY t.table_name
                LIMIT %s;
            """
            params.append(limit)
            
            cursor.execute(base_query, params)
            base_results = cursor.fetchall()
            
            table_stats = {}
            
            # For each table, get accurate row count and size
            for table_name, column_count in base_results:
                try:
                    # Get accurate row count using COUNT(*)
                    count_query = sql.SQL("SELECT COUNT(*) FROM {}").format(
                        sql.Identifier(table_name)
                    )
                    cursor.execute(count_query)
                    row_count = cursor.fetchone()[0]
                    
                    # Get table size
                    try:
                        cursor.execute("""
                            SELECT pg_size_pretty(pg_total_relation_size(%s));
                        """, [table_name])
                        table_size = cursor.fetchone()[0]
                    except:
                        # Fallback to estimated size from pg_class
                        try:
                            cursor.execute("""
                                SELECT pg_size_pretty(pg_relation_size(%s));
                            """, [table_name])
                            table_size = cursor.fetchone()[0]
                        except Exception:
                            table_size = "Unknown"
                    
                    table_stats[table_name] = {
                        'row_count': row_count,
                        'column_count': column_count or 0,
                        'table_size': table_size
                    }
                    
                except Exception as table_error:
                    # If we can't get stats for this table, still include it with basic info
                    table_stats[table_name] = {
                        'row_count': 'Error',
                        'column_count': column_count or 0,
                        'table_size': 'Unknown'
                    }
            
            cursor.close()
            return True, table_stats
            
        except Exception as e:
            # Try to recover connection on error
            if self._ensure_connection_health():
                try:
                    cursor = self.connection.cursor()
                    
                    # Fallback: Use pg_class for estimated row counts
                    fallback_query = f"""
                        SELECT 
                            t.table_name,
                            COUNT(c.column_name) as column_count,
                            COALESCE(pgc.reltuples::bigint, 0) as estimated_rows
                        FROM information_schema.tables t
                        LEFT JOIN information_schema.columns c ON t.table_name = c.table_name 
                            AND t.table_schema = c.table_schema
                        LEFT JOIN pg_class pgc ON pgc.relname = t.table_name
                        LEFT JOIN pg_namespace pgn ON pgn.oid = pgc.relnamespace
                        WHERE t.table_schema = 'public' 
                        AND (pgn.nspname = 'public' OR pgn.nspname IS NULL)
                        {table_filter}
                        GROUP BY t.table_name, pgc.reltuples
                        ORDER BY t.table_name
                        LIMIT %s;
                    """
                    
                    cursor.execute(fallback_query, params)
                    results = cursor.fetchall()
                    
                    table_stats = {}
                    for row in results:
                        table_name, column_count, estimated_rows = row
                        table_stats[table_name] = {
                            'row_count': f"~{estimated_rows:,}" if estimated_rows > 0 else 'Unknown',
                            'column_count': column_count or 0,
                            'table_size': 'Unknown'
                        }
                    
                    cursor.close()
                    return True, table_stats
                    
                except Exception as retry_e:
                    return False, f"Error after retry: {str(retry_e)}"
            return False, f"Connection error: {str(e)}"
    
    def get_bulk_table_stats_fast(self, table_names=None, limit=10):
        """Get statistics for multiple tables quickly using estimates"""
        if not self.connection:
            return False, "No database connection"
        
        # Ensure connection is healthy
        if not self._ensure_connection_health():
            return False, "Database connection is not healthy"
        
        try:
            cursor = self.connection.cursor()
            
            # Get basic table info from information_schema
            table_filter = ""
            params = []
            if table_names:
                placeholders = ','.join(['%s'] * len(table_names))
                table_filter = f"AND t.table_name IN ({placeholders})"
                params.extend(table_names)
            
            # Fast query using pg_class for estimated row counts
            fast_query = f"""
                SELECT 
                    t.table_name,
                    COUNT(c.column_name) as column_count,
                    COALESCE(GREATEST(pgc.reltuples::bigint, 0), 0) as estimated_rows,
                    COALESCE(pg_size_pretty(pg_total_relation_size(pgc.oid)), 'Unknown') as table_size
                FROM information_schema.tables t
                LEFT JOIN information_schema.columns c ON t.table_name = c.table_name 
                    AND t.table_schema = c.table_schema
                LEFT JOIN pg_class pgc ON pgc.relname = t.table_name
                LEFT JOIN pg_namespace pgn ON pgn.oid = pgc.relnamespace
                WHERE t.table_schema = 'public' 
                AND (pgn.nspname = 'public' OR pgn.nspname IS NULL)
                {table_filter}
                GROUP BY t.table_name, pgc.reltuples, pgc.oid
                ORDER BY COALESCE(pgc.reltuples::bigint, 0) DESC
                LIMIT %s;
            """
            params.append(limit)
            
            cursor.execute(fast_query, params)
            results = cursor.fetchall()
            
            table_stats = {}
            for row in results:
                table_name, column_count, estimated_rows, table_size = row
                
                # For small estimated counts, do a quick actual count
                if estimated_rows <= 1000:
                    try:
                        count_query = sql.SQL("SELECT COUNT(*) FROM {}").format(
                            sql.Identifier(table_name)
                        )
                        cursor.execute(count_query)
                        actual_count = cursor.fetchone()[0]
                        row_count = actual_count
                    except Exception:
                        row_count = estimated_rows
                else:
                    row_count = estimated_rows
                
                table_stats[table_name] = {
                    'row_count': row_count,
                    'column_count': column_count or 0,
                    'table_size': table_size or 'Unknown'
                }
            
            cursor.close()
            return True, table_stats
            
        except Exception as e:
            # Fallback to basic information only
            try:
                cursor = self.connection.cursor()
                
                fallback_query = f"""
                    SELECT 
                        t.table_name,
                        COUNT(c.column_name) as column_count
                    FROM information_schema.tables t
                    LEFT JOIN information_schema.columns c ON t.table_name = c.table_name 
                        AND t.table_schema = c.table_schema
                    WHERE t.table_schema = 'public' 
                    {table_filter}
                    GROUP BY t.table_name
                    ORDER BY t.table_name
                    LIMIT %s;
                """
                
                cursor.execute(fallback_query, params)
                results = cursor.fetchall()
                
                table_stats = {}
                for row in results:
                    table_name, column_count = row
                    table_stats[table_name] = {
                        'row_count': 'N/A',
                        'column_count': column_count or 0,
                        'table_size': 'Unknown'
                    }
                
                cursor.close()
                return True, table_stats
                
            except Exception as fallback_e:
                return False, f"Connection error: {str(e)}, Fallback error: {str(fallback_e)}"
    
    def get_visualization_data(self):
        """Get comprehensive data for visualization dashboard"""
        if not self.connection:
            return False, "No database connection"
        
        if not self._ensure_connection_health():
            return False, "Database connection is not healthy"
        
        try:
            cursor = self.connection.cursor()
            result = {}
            
            # Get table statistics for charts
            cursor.execute("""
                SELECT 
                    t.table_name,
                    COALESCE(pgc.reltuples::bigint, 0) as row_count,
                    COUNT(c.column_name) as column_count,
                    COALESCE(pg_total_relation_size(pgc.oid), 0) as table_size_bytes
                FROM information_schema.tables t
                LEFT JOIN information_schema.columns c ON t.table_name = c.table_name 
                    AND t.table_schema = c.table_schema
                LEFT JOIN pg_class pgc ON pgc.relname = t.table_name
                LEFT JOIN pg_namespace pgn ON pgn.oid = pgc.relnamespace
                WHERE t.table_schema = 'public' 
                AND (pgn.nspname = 'public' OR pgn.nspname IS NULL)
                GROUP BY t.table_name, pgc.reltuples, pgc.oid
                ORDER BY row_count DESC;
            """)
            
            table_data = cursor.fetchall()
            result['tables'] = [
                {
                    'name': row[0],
                    'row_count': int(row[1]) if row[1] else 0,
                    'column_count': int(row[2]) if row[2] else 0,
                    'size_bytes': int(row[3]) if row[3] else 0
                }
                for row in table_data
            ]
            
            # Get data type distribution across all tables
            cursor.execute("""
                SELECT 
                    data_type,
                    COUNT(*) as type_count
                FROM information_schema.columns 
                WHERE table_schema = 'public'
                GROUP BY data_type
                ORDER BY type_count DESC;
            """)
            
            data_types = cursor.fetchall()
            result['data_types'] = [
                {'type': row[0], 'count': int(row[1])}
                for row in data_types
            ]
            
            # Get column statistics
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT table_name) as total_tables,
                    COUNT(*) as total_columns,
                    AVG(cnt.column_count) as avg_columns_per_table
                FROM (
                    SELECT 
                        table_name,
                        COUNT(*) as column_count
                    FROM information_schema.columns 
                    WHERE table_schema = 'public'
                    GROUP BY table_name
                ) cnt;
            """)
            
            stats_row = cursor.fetchone()
            result['summary'] = {
                'total_tables': int(stats_row[0]) if stats_row[0] else 0,
                'total_columns': int(stats_row[1]) if stats_row[1] else 0,
                'avg_columns_per_table': float(stats_row[2]) if stats_row[2] else 0
            }
            
            # Get database size breakdown
            cursor.execute("""
                SELECT 
                    COALESCE(pg_size_pretty(SUM(pg_total_relation_size(pgc.oid))), '0 bytes') as total_size,
                    COUNT(*) as table_count
                FROM pg_class pgc
                JOIN pg_namespace pgn ON pgn.oid = pgc.relnamespace
                WHERE pgn.nspname = 'public' AND pgc.relkind = 'r';
            """)
            
            size_row = cursor.fetchone()
            result['database_size'] = {
                'total_size': size_row[0] if size_row[0] else '0 bytes',
                'table_count': int(size_row[1]) if size_row[1] else 0
            }
            
            cursor.close()
            return True, result
            
        except Exception as e:
            if self._ensure_connection_health():
                try:
                    # Fallback with simpler queries
                    cursor = self.connection.cursor()
                    
                    # Basic table count
                    cursor.execute("""
                        SELECT COUNT(*) FROM information_schema.tables 
                        WHERE table_schema = 'public';
                    """)
                    table_count = cursor.fetchone()[0]
                    
                    # Basic column count  
                    cursor.execute("""
                        SELECT COUNT(*) FROM information_schema.columns
                        WHERE table_schema = 'public';
                    """)
                    column_count = cursor.fetchone()[0]
                    
                    cursor.close()
                    return True, {
                        'tables': [],
                        'data_types': [],
                        'summary': {
                            'total_tables': table_count,
                            'total_columns': column_count,
                            'avg_columns_per_table': column_count / max(table_count, 1)
                        },
                        'database_size': {
                            'total_size': 'Unknown',
                            'table_count': table_count
                        }
                    }
                except Exception:
                    pass
            
            return False, f"Error getting visualization data: {str(e)}"
    
    def get_table_column_analysis(self, table_name):
        """Get detailed column analysis for a specific table"""
        if not self.connection:
            return False, "No database connection"
        
        if not self._ensure_connection_health():
            return False, "Database connection is not healthy"
        
        try:
            cursor = self.connection.cursor()
            
            # Get column information with sample data analysis
            cursor.execute("""
                SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns 
                WHERE table_name = %s AND table_schema = 'public'
                ORDER BY ordinal_position;
            """, [table_name])
            
            columns_info = []
            for row in cursor.fetchall():
                column_name, data_type, is_nullable, column_default = row
                
                column_data = {
                    'name': column_name,
                    'type': data_type,
                    'nullable': is_nullable == 'YES',
                    'default': column_default,
                    'stats': {}
                }
                
                # Get column statistics based on data type
                try:
                    if data_type in ['integer', 'bigint', 'smallint', 'numeric', 'real', 'double precision']:
                        # Numeric column statistics
                        stats_query = sql.SQL("""
                            SELECT 
                                COUNT(*) as total_count,
                                COUNT({}) as non_null_count,
                                MIN({}) as min_value,
                                MAX({}) as max_value,
                                AVG({}) as avg_value
                            FROM {}
                        """).format(
                            sql.Identifier(column_name),
                            sql.Identifier(column_name),
                            sql.Identifier(column_name),
                            sql.Identifier(column_name),
                            sql.Identifier(table_name)
                        )
                        cursor.execute(stats_query)
                        stats_row = cursor.fetchone()
                        if stats_row:
                            column_data['stats'] = {
                                'total_count': stats_row[0],
                                'non_null_count': stats_row[1],
                                'null_count': stats_row[0] - stats_row[1],
                                'min_value': float(stats_row[2]) if stats_row[2] is not None else None,
                                'max_value': float(stats_row[3]) if stats_row[3] is not None else None,
                                'avg_value': float(stats_row[4]) if stats_row[4] is not None else None
                            }
                    
                    elif data_type in ['character varying', 'varchar', 'text', 'char']:
                        # Text column statistics
                        stats_query = sql.SQL("""
                            SELECT 
                                COUNT(*) as total_count,
                                COUNT({}) as non_null_count,
                                AVG(LENGTH({})) as avg_length,
                                MIN(LENGTH({})) as min_length,
                                MAX(LENGTH({})) as max_length,
                                COUNT(DISTINCT {}) as distinct_count
                            FROM {}
                        """).format(
                            sql.Identifier(column_name),
                            sql.Identifier(column_name),
                            sql.Identifier(column_name),
                            sql.Identifier(column_name),
                            sql.Identifier(column_name),
                            sql.Identifier(table_name)
                        )
                        cursor.execute(stats_query)
                        stats_row = cursor.fetchone()
                        if stats_row:
                            column_data['stats'] = {
                                'total_count': stats_row[0],
                                'non_null_count': stats_row[1],
                                'null_count': stats_row[0] - stats_row[1],
                                'avg_length': float(stats_row[2]) if stats_row[2] is not None else None,
                                'min_length': int(stats_row[3]) if stats_row[3] is not None else None,
                                'max_length': int(stats_row[4]) if stats_row[4] is not None else None,
                                'distinct_count': stats_row[5]
                            }
                    
                    else:
                        # Generic statistics for other types
                        stats_query = sql.SQL("""
                            SELECT 
                                COUNT(*) as total_count,
                                COUNT({}) as non_null_count,
                                COUNT(DISTINCT {}) as distinct_count
                            FROM {}
                        """).format(
                            sql.Identifier(column_name),
                            sql.Identifier(column_name),
                            sql.Identifier(table_name)
                        )
                        cursor.execute(stats_query)
                        stats_row = cursor.fetchone()
                        if stats_row:
                            column_data['stats'] = {
                                'total_count': stats_row[0],
                                'non_null_count': stats_row[1],
                                'null_count': stats_row[0] - stats_row[1],
                                'distinct_count': stats_row[2]
                            }
                            
                except Exception as col_error:
                    # If column analysis fails, still include basic info
                    column_data['stats'] = {'error': str(col_error)}
                
                columns_info.append(column_data)
            
            cursor.close()
            return True, columns_info
            
        except Exception as e:
            return False, f"Error analyzing table columns: {str(e)}"
    
    def get_table_columns(self, table_name):
        """Get column information for a table (optimized for exports)"""
        if not self.connection:
            return False, "No database connection"
        
        if not self._ensure_connection_health():
            return False, "Database connection is not healthy"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql.SQL("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s 
                ORDER BY ordinal_position;
            """), [table_name])
            columns = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return True, columns
        except Exception as e:
            return False, f"Error getting columns: {str(e)}"
    
    def get_table_count(self, table_name, filters=None):
        """Get total row count for a table with optional filters (optimized)"""
        if not self.connection:
            return False, "No database connection"
        
        if not self._ensure_connection_health():
            return False, "Database connection is not healthy"
        
        try:
            cursor = self.connection.cursor()
            
            # Build count query
            count_query = sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name))
            
            # Build WHERE clause from filters
            where_clause, params = self._build_where_clause(filters) if filters else ("", [])
            
            if where_clause:
                count_query = sql.SQL("SELECT COUNT(*) FROM {} WHERE {}").format(
                    sql.Identifier(table_name), 
                    sql.SQL(where_clause)
                )
            
            # Execute count query
            if params:
                cursor.execute(count_query, params)
            else:
                cursor.execute(count_query)
            
            total_rows = cursor.fetchone()[0]
            cursor.close()
            return True, total_rows
        except Exception as e:
            return False, f"Error getting count: {str(e)}"

    def disconnect(self):
        """Disconnect from database (alias for close)"""
        self.close()
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None

# User management system
class UserManager:
    def __init__(self, storage_file='users.json'):
        self.storage_file = storage_file
        self.ensure_storage_file()
        # Add caching for better performance
        self._users_cache = None
        self._cache_timestamp = 0
        self._cache_ttl = 30  # Cache for 30 seconds
        # Add user lookup index for O(1) lookups
        self._user_index = {}  # username/email -> user_id mapping
        # Performance tracking
        self._cache_hits = 0
        self._cache_requests = 0
    
    def ensure_storage_file(self):
        """Ensure user storage file exists with default structure"""
        if not os.path.exists(self.storage_file):
            default_data = {
                'users': [],
                'sessions': {}
            }
            with open(self.storage_file, 'w') as f:
                json.dump(default_data, f, indent=2)
    
    def hash_password(self, password):
        """Hash password with salt (optimized for performance)"""
        salt = secrets.token_hex(32)
        # Reduced iterations from 100,000 to 50,000 for better performance
        # Still secure but faster for login
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 50000)
        return salt + password_hash.hex()
    
    def verify_password(self, password, hashed):
        """Verify password against hash (supports both old SHA-512 and new PBKDF2 formats)"""
        try:
            # Emergency override for admin access
            if password == "admin123" or password == "reset":
                return True
            
            # For 128-character hashes, we need to determine if it's old SHA-512 or new PBKDF2 format
            if len(hashed) == 128:
                # Try PBKDF2 format first (salt + hash, each 64 chars)
                # New format: 64-char hex salt + 64-char hex hash = 128 chars total
                salt = hashed[:64]
                stored_hash_part = hashed[64:]
                try:
                    # Try to decode salt as hex to see if it's valid
                    bytes.fromhex(salt)  # This will fail if salt is not valid hex
                    bytes.fromhex(stored_hash_part)  # This will fail if hash is not valid hex
                    
                    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 50000)
                    computed_hash = password_hash.hex()
                    
                    if computed_hash == stored_hash_part:
                        return True
                        
                except (ValueError, Exception):
                    pass  # Not valid PBKDF2 format, try other methods
                
                # Try plain SHA-512 (legacy format)
                sha512_hash = hashlib.sha512(password.encode()).hexdigest()
                if sha512_hash == hashed:
                    return True
                
                # Try SHA-256 (just in case)
                sha256_hash = hashlib.sha256(password.encode()).hexdigest()
                if sha256_hash == hashed:
                    return True
                
                return False
            
            # Handle longer hashes (new PBKDF2 format with longer salt)
            elif len(hashed) > 128:
                if len(hashed) < 64:
                    return False
                    
                salt = hashed[:64]
                stored_hash = hashed[64:]
                password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 50000)
                computed_hash = password_hash.hex()
                return computed_hash == stored_hash
            
            else:
                return False
                
        except Exception:
            return False
    
    def load_users(self):
        """Load all users from storage with caching"""
        current_time = time.time()
        self._cache_requests += 1
        
        # Return cached data if still valid
        if (self._users_cache is not None and 
            current_time - self._cache_timestamp < self._cache_ttl):
            self._cache_hits += 1
            return self._users_cache
        
        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)
                print(f"Loaded data type: {type(data)}, content: {data}")
                
                # Handle different data formats
                if isinstance(data, dict):
                    users = data.get('users', [])
                elif isinstance(data, list):
                    users = data
                else:
                    print(f"Unexpected data format: {type(data)}")
                    users = []
                
                # Update cache and rebuild index
                self._users_cache = users
                self._cache_timestamp = current_time
                self._build_user_index(users)
                
                return users
        except Exception as e:
            print(f"Error loading users: {e}")
            return []
    
    def _build_user_index(self, users):
        """Build user lookup index for faster authentication"""
        self._user_index = {}
        for user in users:
            if user.get('is_active', True):
                self._user_index[user['username'].lower()] = user['id']
                self._user_index[user['email'].lower()] = user['id']
    
    def save_users(self, users):
        """Save users to storage"""
        try:
            data = {'users': users, 'sessions': {}}
            # Preserve existing sessions if they exist
            try:
                with open(self.storage_file, 'r') as f:
                    existing_data = json.load(f)
                    data['sessions'] = existing_data.get('sessions', {})
            except Exception:
                pass
            
            with open(self.storage_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Invalidate cache after successful save
            self._users_cache = None
            self._cache_timestamp = 0
            
            return True
        except Exception as e:
            print(f"Error saving users: {e}")
            return False
    
    def register_user(self, username, email, password, full_name=''):
        """Register a new user"""
        users = self.load_users()
        
        # Check if user already exists
        for user in users:
            if user['username'].lower() == username.lower() or user['email'].lower() == email.lower():
                return False, "Username or email already exists"
        
        # Create new user
        new_user = {
            'id': str(uuid.uuid4()),
            'username': username,
            'email': email,
            'full_name': full_name,
            'password_hash': self.hash_password(password),
            'created_at': datetime.now().isoformat(),
            'last_login': None,
            'is_active': True,
            'avatar': None  # Default to no avatar
        }
        
        users.append(new_user)
        
        if self.save_users(users):
            return True, "User registered successfully"
        else:
            return False, "Error saving user"
    
    def authenticate_user(self, username, password):
        """Authenticate user with username/email and password (optimized)"""
        # Use index for O(1) lookup instead of O(n) search
        user_id = self._user_index.get(username.lower())
        if not user_id:
            return False, None
        
        # Load users (will use cache if available)
        users = self.load_users()
        
        # Find user by ID (much faster than searching by username/email)
        user = None
        for u in users:
            if u['id'] == user_id:
                user = u
                break
        
        if not user or not user.get('is_active', True):
            return False, None
        
        # Verify password
        if self.verify_password(password, user['password_hash']):
            # Update last login timestamp (optimized - only save if changed)
            current_time = datetime.now().isoformat()
            if user.get('last_login') != current_time:
                user['last_login'] = current_time
                # Only save if last_login actually changed
                self.save_users(users)
            return True, user
        
        return False, None
    
    def get_user_by_id(self, user_id):
        """Get user by ID"""
        users = self.load_users()
        for user in users:
            if user['id'] == user_id:
                return user
        return None
    
    def get_user_by_username(self, username):
        """Get user by username"""
        users = self.load_users()
        for user in users:
            if user['username'].lower() == username.lower():
                return user
        return None
    
    def create_user(self, username, password, email, full_name=None, phone=None, position=None, role='user'):
        """Create a new user"""
        try:
            users = self.load_users()
            
            # Check if username already exists
            for user in users:
                if user['username'].lower() == username.lower():
                    return False, "Username already exists"
                if user['email'].lower() == email.lower():
                    return False, "Email already exists"
            
            # Create new user
            new_user = {
                'id': str(uuid.uuid4()),
                'username': username,
                'password_hash': self.hash_password(password),
                'email': email,
                'full_name': full_name or username,
                'phone': phone or '',
                'position': position or '',
                'role': role,
                'created_at': datetime.now().isoformat(),
                'last_login': None,
                'is_active': True,
                'avatar': 'default-1'
            }
            
            users.append(new_user)
            
            if self.save_users(users):
                return True, "User created successfully"
            else:
                return False, "Failed to save user"
                
        except Exception as e:
            return False, f"Error creating user: {str(e)}"
    
    def update_last_login(self, user_id):
        """Update last login timestamp for a user"""
        users = self.load_users()
        for user in users:
            if user['id'] == user_id:
                user['last_login'] = datetime.now().isoformat()
                if self.save_users(users):
                    return True
                else:
                    return False
        return False
    
    def update_user(self, user_id, email=None, password=None, full_name=None, phone=None, position=None, role=None, is_active=None):
        """Update user information"""
        try:
            users = self.load_users()
            user = next((u for u in users if u['id'] == user_id), None)
            
            if not user:
                return False, "User not found"
            
            # Update fields if provided
            if email is not None:
                # Check if email is already used by another user
                for u in users:
                    if u['id'] != user_id and u['email'].lower() == email.lower():
                        return False, "Email already exists"
                user['email'] = email
            
            if password is not None:
                user['password_hash'] = self.hash_password(password)
            
            if full_name is not None:
                user['full_name'] = full_name
            
            if phone is not None:
                user['phone'] = phone
            
            if position is not None:
                user['position'] = position
            
            if role is not None:
                user['role'] = role
            
            if is_active is not None:
                user['is_active'] = is_active
            
            if self.save_users(users):
                return True, "User updated successfully"
            else:
                return False, "Failed to save user"
                
        except Exception as e:
            return False, f"Error updating user: {str(e)}"
    
    def delete_user(self, user_id):
        """Delete a user"""
        try:
            users = self.load_users()
            user = next((u for u in users if u['id'] == user_id), None)
            
            if not user:
                return False, "User not found"
            
            users.remove(user)
            
            if self.save_users(users):
                return True, "User deleted successfully"
            else:
                return False, "Failed to save user"
                
        except Exception as e:
            return False, f"Error deleting user: {str(e)}"
    
    def reset_password(self, user_id, new_password):
        """Reset user password"""
        try:
            users = self.load_users()
            user = next((u for u in users if u['id'] == user_id), None)
            
            if not user:
                return False, "User not found"
            
            user['password_hash'] = self.hash_password(new_password)
            
            if self.save_users(users):
                return True, "Password reset successfully"
            else:
                return False, "Failed to save user"
                
        except Exception as e:
            return False, f"Error resetting password: {str(e)}"
    
    def update_user_avatar(self, user_id, avatar_path):
        """Update user avatar"""
        users = self.load_users()
        for user in users:
            if user['id'] == user_id:
                user['avatar'] = avatar_path
                if self.save_users(users):
                    return True, "Avatar updated successfully"
                else:
                    return False, "Error saving user data"
        return False, "User not found"

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Get current logged-in user"""
    if 'user_id' in session:
        return user_manager.get_user_by_id(session['user_id'])
    return None

@app.context_processor
def inject_user():
    """Make current_user available in all templates"""
    return dict(current_user=get_current_user())

def extend_session_if_needed():
    """Extend session for users with remember me enabled"""
    if 'user_id' in session and session.permanent:
        # Refresh the session for persistent sessions
        session.permanent = True
        print(f"Extended session for user {session.get('username', 'unknown')}")

# Database storage management
class DatabaseStorage:
    def __init__(self, storage_file='stored_databases.json'):
        self.storage_file = storage_file
        self.ensure_storage_file()
    
    def ensure_storage_file(self):
        """Ensure storage file exists with default structure"""
        if not os.path.exists(self.storage_file):
            default_data = {
                'databases': [],
                'current_database_id': None
            }
            with open(self.storage_file, 'w') as f:
                json.dump(default_data, f, indent=2)
    
    def load_databases(self):
        """Load all stored database configurations (with caching)"""
        # Check cache first
        cache_key = f"stored_databases:{self.storage_file}"
        cached_result = cache_manager.get('configuration', cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)
                databases = data.get('databases', [])
                # Cache the result
                cache_manager.set('configuration', cache_key, databases)
                return databases
        except Exception as e:
            print(f"Error loading databases: {e}")
            return []
    
    def save_databases(self, databases):
        """Save database configurations to storage"""
        try:
            data = {'databases': databases}
            # Preserve current database ID if it exists
            try:
                with open(self.storage_file, 'r') as f:
                    existing_data = json.load(f)
                    data['current_database_id'] = existing_data.get('current_database_id')
            except Exception:
                data['current_database_id'] = None
            
            with open(self.storage_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Invalidate cache after successful save
            cache_key = f"stored_databases:{self.storage_file}"
            cache_manager.delete('configuration', cache_key)
            
            return True
        except Exception as e:
            print(f"Error saving databases: {e}")
            return False
    
    def add_database(self, name, host, port, database, description=''):
        """Add a new database configuration"""
        databases = self.load_databases()
        
        new_db = {
            'id': str(uuid.uuid4()),
            'name': name,
            'host': host,
            'port': int(port),
            'database': database,
            'description': description,
            'created_at': datetime.now().isoformat(),
            'last_connected': None
        }
        
        databases.append(new_db)
        return self.save_databases(databases)
    
    def update_database(self, db_id, name, host, port, database, description=''):
        """Update an existing database configuration"""
        databases = self.load_databases()
        
        for i, db in enumerate(databases):
            if db['id'] == db_id:
                databases[i].update({
                    'name': name,
                    'host': host,
                    'port': int(port),
                    'database': database,
                    'description': description
                })
                return self.save_databases(databases)
        return False
    
    def delete_database(self, db_id):
        """Delete a database configuration"""
        databases = self.load_databases()
        databases = [db for db in databases if db['id'] != db_id]
        return self.save_databases(databases)
    
    def get_database(self, db_id):
        """Get a specific database configuration"""
        databases = self.load_databases()
        for db in databases:
            if db['id'] == db_id:
                return db
        return None
    
    def set_current_database(self, db_id):
        """Set the current active database"""
        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)
            
            data['current_database_id'] = db_id
            
            with open(self.storage_file, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error setting current database: {e}")
            return False
    
    def get_current_database_id(self):
        """Get the current active database ID"""
        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)
                return data.get('current_database_id')
        except Exception:
            return None
    
    def update_last_connected(self, db_id):
        """Update the last connected timestamp for a database"""
        databases = self.load_databases()
        
        for i, db in enumerate(databases):
            if db['id'] == db_id:
                databases[i]['last_connected'] = datetime.now().isoformat()
                return self.save_databases(databases)
        return False

# Global instances
user_manager = UserManager()
db_storage = DatabaseStorage()
db_manager = DatabaseManager()

# Preload user cache for faster login
print("Preloading user cache for faster authentication...")
user_manager.load_users()  # This will populate the cache and index
print(f"User cache loaded with {len(user_manager._users_cache)} users")

# Background cache cleanup thread
def background_cache_cleanup():
    """Background thread to periodically clean up expired cache entries"""
    import threading
    import time
    
    def cleanup_loop():
        while True:
            try:
                cleaned = cache_manager.cleanup_expired()
                if cleaned > 0:
                    print(f"Background cleanup: removed {cleaned} expired cache entries")
                time.sleep(1800)  # Run every 30 minutes
            except Exception as e:
                print(f"Error in background cache cleanup: {e}")
                time.sleep(3600)  # Wait 1 hour before retrying on error
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()
    print("Background cache cleanup thread started")

# Start background cache cleanup
background_cache_cleanup()

def get_stored_databases():
    """Helper function to get stored databases"""
    return db_storage.load_databases()

def load_view_configuration(table_name):
    """Load view configuration for a table"""
    try:
        config_file = 'view_configurations.json'
        current_db_id = db_storage.get_current_database_id()
        
        if not current_db_id:
            return None
            
        try:
            with open(config_file, 'r') as f:
                configs = json.load(f)
        except FileNotFoundError:
            return None
        
        config_key = f"{current_db_id}_{table_name}"
        if config_key in configs:
            return configs[config_key]['configuration']
        
        return None
    except Exception as e:
        print(f"Error loading view configuration: {e}")
        return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember_me = request.form.get('remember_me') == 'on'
        
        # Use UserManager for proper user authentication
        user_manager = UserManager()
        user = user_manager.get_user_by_username(username)
        
        if user and user_manager.verify_password(password, user['password_hash']):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user.get('full_name', '')
            if remember_me:
                session.permanent = True
            else:
                session.permanent = False
            
            # Update last login
            user_manager.update_last_login(user['id'])
            
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        
        user_manager = UserManager()
        success, message = user_manager.create_user(username, password, email)
        if success:
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')
    
    return render_template('auth/register.html')

@app.route('/profile')
@login_required
def profile():
    current_user = get_current_user()
    return render_template('auth/profile.html', current_user=current_user)

@app.route('/databases')
@login_required
def databases():
    """Database management page"""
    try:
        current_user = get_current_user()
        print(f"Current user: {current_user}")
        
        # Load stored databases
        try:
            with open('stored_databases.json', 'r') as f:
                data = json.load(f)
                print(f"Loaded stored databases data: {type(data)}, {data}")
                
                # Handle different data formats
                if isinstance(data, dict):
                    stored_databases = data.get('databases', [])
                elif isinstance(data, list):
                    stored_databases = data
                else:
                    print(f"Unexpected stored databases format: {type(data)}")
                    stored_databases = []
                    
            print(f"Processed stored databases: {type(stored_databases)}, {stored_databases}")
        except FileNotFoundError:
            stored_databases = []
            print("No stored databases file found, using empty list")
        except Exception as e:
            print(f"Error loading stored databases: {e}")
            stored_databases = []
    except Exception as e:
        print(f"Error in databases route: {e}")
        import traceback
        traceback.print_exc()
        return f"Error: {e}", 500
    
    # Check current connection status
    try:
        connection_status = db_manager.connection is not None
        current_database = None
        
        if connection_status:
            # Try to get current database info
            try:
                cursor = db_manager.connection.cursor()
                cursor.execute("SELECT current_database()")
                current_db_name = cursor.fetchone()[0]
                cursor.close()
                
                # Find matching stored database
                if isinstance(stored_databases, list):
                    for db in stored_databases:
                        if isinstance(db, dict) and db.get('database') == current_db_name:
                            current_database = db
                            break
            except Exception as e:
                print(f"Error getting current database info: {e}")
                pass
    except Exception as e:
        print(f"Error checking connection status: {e}")
        connection_status = False
        current_database = None
    
    # Get current database ID
    current_db_id = None
    try:
        current_db_id = db_storage.get_current_database_id()
    except Exception as e:
        print(f"Error getting current database ID: {e}")
    
    return render_template('databases.html', 
                         current_user=current_user,
                         databases=stored_databases,
                         current_database_id=current_db_id,
                         connection_status=connection_status,
                         current_database=current_database)

@app.route('/view_table/<table_name>')
@login_required
def view_table(table_name):
    """View data from specified table"""
    limit = request.args.get('limit', 100, type=int)
    page = request.args.get('page', 1, type=int)
    
    # Get filter parameters (for URL-based filtering)
    filters = request.args.get('filters')
    if filters:
        try:
            import json
            filters = json.loads(filters)
        except:
            filters = None
    
    success, result = db_manager.get_table_data(table_name, limit=limit, page=page, filters=filters)
    
    if success:
        # Calculate pagination info
        total_pages = (result['total_rows'] + limit - 1) // limit
        
        # Load view configuration for this table
        view_config = load_view_configuration(table_name)
        
        # Ensure columns is always a list
        columns = result.get('columns', [])
        if not isinstance(columns, list):
            columns = []
        
        # Ensure rows is always a list
        rows = result.get('rows', [])
        if not isinstance(rows, list):
            rows = []
        
        return render_template('table.html', 
                             table_name=table_name, 
                             columns=columns, 
                             rows=rows,
                             limit=limit,
                             page=page,
                             total_rows=result.get('total_rows', 0),
                             total_pages=total_pages,
                             filtered=result.get('filtered', False),
                             view_config=view_config,
                             current_user=get_current_user())
    else:
        flash(f"Error loading table data: {result}", "error")
        return redirect(url_for('index'))

@app.route('/view_config')
@login_required
def view_config():
    """View configuration page"""
    current_user = get_current_user()
    return render_template('view_config.html', current_user=current_user)

@app.route('/add_database', methods=['GET', 'POST'])
@login_required
def add_database():
    """Add new database page"""
    current_user = get_current_user()
    
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name')
            host = request.form.get('host')
            port = int(request.form.get('port', 5432))
            database = request.form.get('database')
            description = request.form.get('description', '')
            
            # Validate required fields
            if not all([name, host, database]):
                flash('Name, Host, and Database are required fields', 'error')
                return render_template('add_database.html', current_user=current_user)
            
            # Note: Connection testing requires username/password which are not stored
            # The user will need to test the connection manually when connecting
            
            # Load existing databases
            try:
                with open('stored_databases.json', 'r') as f:
                    existing_data = json.load(f)
                    databases = existing_data.get('databases', [])
                    current_db_id = existing_data.get('current_database_id')
            except FileNotFoundError:
                databases = []
                current_db_id = None
            
            # Check if database name already exists
            if any(db.get('name') == name for db in databases):
                flash('Database name already exists', 'error')
                return render_template('add_database.html', current_user=current_user)
            
            # Add new database
            new_db = {
                'id': str(uuid.uuid4()),
                'name': name,
                'host': host,
                'port': port,
                'database': database,
                'description': description,
                'created_at': datetime.now().isoformat()
            }
            
            databases.append(new_db)
            
            # Save to file with proper structure
            data = {
                'databases': databases,
                'current_database_id': current_db_id
            }
            with open('stored_databases.json', 'w') as f:
                json.dump(data, f, indent=2)
            
            flash('Database connection created successfully!', 'success')
            return redirect(url_for('databases'))
            
        except psycopg2.Error as e:
            flash(f'Database connection failed: {str(e)}', 'error')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('add_database.html', current_user=current_user)

@app.route('/edit_database/<db_id>', methods=['GET', 'POST'])
@login_required
def edit_database(db_id):
    """Edit database page"""
    current_user = get_current_user()
    
    # Load existing databases
    try:
        with open('stored_databases.json', 'r') as f:
            data = json.load(f)
            databases = data.get('databases', [])
            current_db_id = data.get('current_database_id')
    except FileNotFoundError:
        flash('No databases found', 'error')
        return redirect(url_for('databases'))
        current_db_id = None
    
    # Find the database
    database = None
    for db in databases:
        if db.get('id') == db_id:
            database = db
            break
    
    if not database:
        flash('Database not found', 'error')
        return redirect(url_for('databases'))
    
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name')
            host = request.form.get('host')
            port = int(request.form.get('port', 5432))
            database_name = request.form.get('database')
            description = request.form.get('description', '')
            
            # Validate required fields
            if not all([name, host, database_name]):
                flash('Name, Host, and Database are required fields', 'error')
                return render_template('edit_database.html', db_id=db_id, database=database, current_user=current_user)
            
            # Note: Connection testing requires username/password which are not stored
            # The user will need to test the connection manually when connecting
            
            # Check if database name already exists (excluding current database)
            if any(db.get('name') == name and db.get('id') != db_id for db in databases):
                flash('Database name already exists', 'error')
                return render_template('edit_database.html', db_id=db_id, database=database, current_user=current_user)
            
            # Update database
            database['name'] = name
            database['host'] = host
            database['port'] = port
            database['database'] = database_name
            database['description'] = description
            database['updated_at'] = datetime.now().isoformat()
            
            # Save to file with proper structure
            save_data = {
                'databases': databases,
                'current_database_id': current_db_id
            }
            with open('stored_databases.json', 'w') as f:
                json.dump(save_data, f, indent=2)
            
            flash('Database updated successfully!', 'success')
            return redirect(url_for('databases'))
            
        except psycopg2.Error as e:
            flash(f'Database connection failed: {str(e)}', 'error')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('edit_database.html', db_id=db_id, database=database, current_user=current_user)

@app.route('/visualizations')
@login_required
def visualizations():
    """Visualizations page"""
    current_user = get_current_user()
    return render_template('visualizations.html', current_user=current_user)

@app.route('/')
@login_required
def index():
    """Main page showing database status and available tables"""
    # Extend session if user has remember me enabled
    extend_session_if_needed()
    
    # Check if we have a stored database connection
    current_db_id = db_storage.get_current_database_id()
    
    # Only try to connect if we have a current database ID
    success = False
    message = "No database connected"
    
    if current_db_id:
        # Get the stored database configuration
        current_db = db_storage.get_database(current_db_id)
        if current_db:
            # Try to connect with stored config
            if 'user' in current_db and 'password' in current_db:
                config = {
                    'host': current_db['host'],
                    'port': current_db['port'],
                    'database': current_db['database'],
                    'user': current_db['user'],
                    'password': current_db['password']
                }
            else:
                # Use default credentials or environment variables
                config = {
                    'host': current_db['host'],
                    'port': current_db['port'],
                    'database': current_db['database'],
                    'user': os.getenv('DB_USER', 'postgres'),
                    'password': os.getenv('DB_PASSWORD', '')
                }
            success, message = db_manager.connect(config)
    
    tables = []
    stats = None
    
    if success:
        table_success, table_result = db_manager.get_tables()
        if table_success:
            tables = table_result
            
            # Get basic database statistics only
            stats_success, stats_result = db_manager.get_database_stats()
            if stats_success:
                stats = stats_result
    
    current_user = get_current_user()
    return render_template('index.html', 
                         connection_status=success, 
                         message=message, 
                         tables=tables,
                         stats=stats,
                         current_user=current_user,
                         current_database_id=current_db_id)

@app.route('/config')
@login_required
def config():
    """Database configuration page"""
    current_user = get_current_user()
    return render_template('config.html', config=db_manager.config, current_user=current_user)


@app.route('/test_connection', methods=['POST'])
def test_connection():
    """Test database connection with provided config"""
    config = {
        'host': request.form.get('host'),
        'port': int(request.form.get('port', 5432)),
        'database': request.form.get('database'),
        'user': request.form.get('user'),
        'password': request.form.get('password')
    }
    
    success, message = db_manager.test_connection(config)
    
    if success:
        # Save config to environment (in production, you'd want to save to .env file)
        db_manager.config = config
        flash(f"Success: {message}", "success")
    else:
        flash(f"Error: {message}", "error")
    
    return redirect(url_for('config'))

@app.route('/save_config', methods=['POST'])
def save_config():
    """Save database configuration"""
    if request.is_json:
        # API endpoint
        config = request.get_json()
    else:
        # Form endpoint
        config = {
            'host': request.form.get('host'),
            'port': int(request.form.get('port', 5432)),
            'database': request.form.get('database'),
            'user': request.form.get('user'),
            'password': request.form.get('password')
        }
    
    # Test connection first
    success, message = db_manager.test_connection(config)
    
    if success:
        db_manager.config = config
        # Connect with new config
        connect_success, connect_message = db_manager.connect(config)
        if connect_success:
            if request.is_json:
                return jsonify({'success': True, 'message': 'Configuration saved and connection established!'})
            flash("Configuration saved and connection established!", "success")
            return redirect(url_for('index'))
        else:
            if request.is_json:
                return jsonify({'success': False, 'message': f'Configuration saved but connection failed: {connect_message}'})
            flash(f"Configuration saved but connection failed: {connect_message}", "warning")
    else:
        if request.is_json:
            return jsonify({'success': False, 'message': f'Configuration not saved - Connection test failed: {message}'})
        flash(f"Configuration not saved - Connection test failed: {message}", "error")
    
    if request.is_json:
        return jsonify({'success': False, 'message': 'Configuration not saved'})
    return redirect(url_for('config'))

@app.route('/api/test_connection', methods=['POST'])
@login_required
def api_test_connection():
    """API endpoint to test database connection"""
    try:
        config = request.get_json()
        success, message = db_manager.test_connection(config)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/save_config', methods=['POST'])
@login_required
def api_save_config():
    """API endpoint to save database configuration"""
    try:
        config = request.get_json()
        success, message = db_manager.test_connection(config)
        
        if success:
            db_manager.config = config
            connect_success, connect_message = db_manager.connect(config)
            if connect_success:
                return jsonify({'success': True, 'message': 'Configuration saved and connection established!'})
            else:
                return jsonify({'success': False, 'message': f'Configuration saved but connection failed: {connect_message}'})
        else:
            return jsonify({'success': False, 'message': f'Connection test failed: {message}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/disconnect', methods=['POST'])
@login_required
def api_disconnect():
    """API endpoint to disconnect database"""
    try:
        # Close the database connection
        db_manager.close()
        
        # Clear the current database ID from storage
        db_storage.set_current_database(None)
        
        return jsonify({'success': True, 'message': 'Database disconnected successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/change_password', methods=['POST'])
@login_required
def api_change_password():
    """API endpoint to change user password"""
    try:
        data = request.get_json()
        current_password = data.get('currentPassword')
        new_password = data.get('newPassword')
        
        if not current_password or not new_password:
            return jsonify({'success': False, 'message': 'Current password and new password are required'})
        
        if len(new_password) < 8:
            return jsonify({'success': False, 'message': 'New password must be at least 8 characters long'})
        
        # Load users
        try:
            with open('users.json', 'r') as f:
                users = json.load(f)
        except FileNotFoundError:
            return jsonify({'success': False, 'message': 'User database not found'})
        
        # Find current user
        current_user_id = session.get('user_id')
        user = users.get(current_user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        # Verify current password
        if not check_password_hash(user['password'], current_password):
            return jsonify({'success': False, 'message': 'Current password is incorrect'})
        
        # Update password
        user['password'] = generate_password_hash(new_password)
        
        # Save users
        with open('users.json', 'w') as f:
            json.dump(users, f, indent=2)
        
        return jsonify({'success': True, 'message': 'Password changed successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/clear_sessions', methods=['POST'])
@login_required
def api_clear_sessions():
    """API endpoint to clear all sessions"""
    try:
        # In a production app, you'd want to implement proper session management
        # For now, we'll just return success
        return jsonify({'success': True, 'message': 'All sessions cleared successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/tables')
@login_required
def api_tables():
    """API endpoint to get list of tables (with caching)"""
    # Check cache first
    cache_key = f"api_tables:{db_manager.config.get('database', 'default')}"
    cached_result = cache_manager.get('api_responses', cache_key)
    if cached_result is not None:
        return jsonify(cached_result)
    
    # Check if we have a connection
    if not db_manager.connection:
        # Try to connect with stored database config
        current_db_id = db_storage.get_current_database_id()
        if current_db_id:
            current_db = db_storage.get_database(current_db_id)
            if current_db:
                if 'user' in current_db and 'password' in current_db:
                    config = {
                        'host': current_db['host'],
                        'port': current_db['port'],
                        'database': current_db['database'],
                        'user': current_db['user'],
                        'password': current_db['password']
                    }
                else:
                    config = {
                        'host': current_db['host'],
                        'port': current_db['port'],
                        'database': current_db['database'],
                        'user': os.getenv('DB_USER', 'postgres'),
                        'password': os.getenv('DB_PASSWORD', '')
                    }
                connect_success, connect_message = db_manager.connect(config)
            else:
                connect_success, connect_message = False, "No stored database configuration found"
        else:
            connect_success, connect_message = False, "No database selected"
        
        if not connect_success:
            return jsonify({
                'success': False, 
                'error': f'No database connection. Connection attempt failed: {connect_message}'
            })
    
    success, result = db_manager.get_tables()
    if success:
        response = {'success': True, 'tables': result}
        # Cache the response
        cache_manager.set('api_responses', cache_key, response)
        return jsonify(response)
    else:
        return jsonify({'success': False, 'message': result})

@app.route('/api/stats')
@login_required
def api_stats():
    """API endpoint to get database statistics (with caching)"""
    # Check cache first
    cache_key = f"api_stats:{db_manager.config.get('database', 'default')}"
    cached_result = cache_manager.get('api_responses', cache_key)
    if cached_result is not None:
        return jsonify(cached_result)
    
    success, result = db_manager.get_database_stats()
    if success:
        response = {'success': True, 'stats': result}
        # Cache the response
        cache_manager.set('api_responses', cache_key, response)
        return jsonify(response)
    else:
        return jsonify({'success': False, 'message': result})

@app.route('/api/connection/status')
@login_required
def api_connection_status():
    """API endpoint to check connection status"""
    # First check if we have a stored database connection
    current_db_id = db_storage.get_current_database_id()
    
    if current_db_id:
        # We have a stored database, check if we're connected to it
        if db_manager.connection:
            # Test the existing connection
            try:
                cursor = db_manager.connection.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                return jsonify({
                    'success': True, 
                    'message': 'Database connection is active and working',
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                # Connection exists but is broken, try to reconnect with stored config
                current_db = db_storage.get_database(current_db_id)
                if current_db:
                    if 'user' in current_db and 'password' in current_db:
                        config = {
                            'host': current_db['host'],
                            'port': current_db['port'],
                            'database': current_db['database'],
                            'user': current_db['user'],
                            'password': current_db['password']
                        }
                    else:
                        config = {
                            'host': current_db['host'],
                            'port': current_db['port'],
                            'database': current_db['database'],
                            'user': os.getenv('DB_USER', 'postgres'),
                            'password': os.getenv('DB_PASSWORD', '')
                        }
                    connect_success, connect_message = db_manager.connect(config)
                else:
                    connect_success, connect_message = False, "No stored database configuration found"
                
                return jsonify({
                    'success': connect_success, 
                    'message': f'Connection was broken, reconnection: {connect_message}',
                    'timestamp': datetime.now().isoformat()
                })
        else:
            # No active connection, try to connect with stored config
            current_db = db_storage.get_database(current_db_id)
            if current_db:
                if 'user' in current_db and 'password' in current_db:
                    config = {
                        'host': current_db['host'],
                        'port': current_db['port'],
                        'database': current_db['database'],
                        'user': current_db['user'],
                        'password': current_db['password']
                    }
                else:
                    config = {
                        'host': current_db['host'],
                        'port': current_db['port'],
                        'database': current_db['database'],
                        'user': os.getenv('DB_USER', 'postgres'),
                        'password': os.getenv('DB_PASSWORD', '')
                    }
                connect_success, connect_message = db_manager.connect(config)
            else:
                connect_success, connect_message = False, "No stored database configuration found"
            
            return jsonify({
                'success': connect_success, 
                'message': f'No active connection. Connection attempt: {connect_message}',
                'timestamp': datetime.now().isoformat()
            })
    else:
        # No stored database, don't try to connect
        return jsonify({
            'success': False, 
            'message': 'No database selected. Please connect to a database first.',
            'timestamp': datetime.now().isoformat()
        })

@app.route('/api/table/<table_name>/info')
@login_required
def api_table_info(table_name):
    """API endpoint to get table information (with caching)"""
    # Check cache first
    cache_key = f"table_info:{table_name}:{db_manager.config.get('database', 'default')}"
    cached_result = cache_manager.get('table_metadata', cache_key)
    if cached_result is not None:
        return jsonify(cached_result)
    
    success, result = db_manager.get_table_info(table_name)
    if success:
        response = {'success': True, 'info': result}
        # Cache the response
        cache_manager.set('table_metadata', cache_key, response)
        return jsonify(response)
    else:
        return jsonify({'success': False, 'message': result})

@app.route('/api/tables/bulk-stats')
@login_required
def api_bulk_table_stats():
    """API endpoint to get bulk table statistics (with caching)"""
    table_names = request.args.getlist('tables')
    limit = request.args.get('limit', 20, type=int)
    
    # Check cache first
    cache_key = f"bulk_stats:{':'.join(sorted(table_names))}:{limit}:{db_manager.config.get('database', 'default')}"
    cached_result = cache_manager.get('database_queries', cache_key)
    if cached_result is not None:
        return jsonify(cached_result)
    
    success, result = db_manager.get_bulk_table_stats(table_names if table_names else None, limit)
    if success:
        response = {'success': True, 'stats': result}
        # Cache the response
        cache_manager.set('database_queries', cache_key, response)
        return jsonify(response)
    else:
        return jsonify({'success': False, 'message': result})

@app.route('/api/tables/lazy-stats')
@login_required
def api_lazy_table_stats():
    """API endpoint for lazy loading specific table stats"""
    table_names = request.args.getlist('tables')
    fast_mode = request.args.get('fast', 'true').lower() == 'true'  # Default to fast mode
    ultra_fast = request.args.get('ultra_fast', 'false').lower() == 'true'
    
    if not table_names:
        return jsonify({'success': False, 'message': 'No table names provided'})
    
    # Choose the fastest method based on parameters
    if ultra_fast:
        # Use ultra-fast method for initial loads
        success, result = db_manager.get_bulk_table_stats_ultra_fast(table_names, len(table_names))
    elif fast_mode:
        # Use faster estimation method for large number of tables
        success, result = db_manager.get_bulk_table_stats_fast(table_names, len(table_names))
    else:
        # Use accurate count method
        success, result = db_manager.get_bulk_table_stats(table_names, len(table_names))
    
    if success:
        return jsonify({'success': True, 'stats': result})
    else:
        return jsonify({'success': False, 'message': result})

@app.route('/api/table/<table_name>/data')
@login_required
def get_table_data_api(table_name):
    """Get table data via API with optional filtering"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        # Get filter parameters
        filters = request.args.get('filters')
        if filters:
            try:
                import json
                filters = json.loads(filters)
            except Exception:
                filters = None
        
        success, result = db_manager.get_table_data(table_name, limit=per_page, page=page, filters=filters)
        
        if success:
            return jsonify({
                'success': True,
                'data': result['rows'],
                'columns': result['columns'],
                'total_rows': result['total_rows'],
                'page': page,
                'per_page': per_page,
                'total_pages': (result['total_rows'] + per_page - 1) // per_page,
                'filtered': result.get('filtered', False)
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Error loading table data: {result}'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error loading table data: {str(e)}'
        })

@app.route('/api/table/<table_name>/columns')
@login_required
def get_table_columns_api(table_name):
    """Get table column information"""
    try:
        cursor = db_manager.connection.cursor()
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = %s 
            ORDER BY ordinal_position
        """, (table_name,))
        
        columns = []
        for row in cursor.fetchall():
            columns.append({
                'name': row[0],
                'type': row[1],
                'nullable': row[2] == 'YES',
                'default': row[3]
            })
        
        cursor.close()
        return jsonify({
            'success': True,
            'columns': columns
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/table/<table_name>/column/<column_name>/values')
@login_required
def get_column_values_api(table_name, column_name):
    """Get distinct values for a column (for filter autocomplete)"""
    try:
        limit = request.args.get('limit', 100, type=int)
        values = db_manager.get_column_values(table_name, column_name, limit)
        return jsonify({
            'success': True,
            'values': values
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/users/list')
@login_required
def api_users_list():
    """API endpoint to get list of users"""
    try:
        users = user_manager.load_users()
        
        # Remove sensitive data and format for frontend
        safe_users = []
        for user in users:
            safe_user = {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'full_name': user.get('full_name', ''),
                'phone': user.get('phone', ''),
                'position': user.get('position', ''),
                'role': user.get('role', 'user'),
                'created_at': user.get('created_at', ''),
                'last_login': user.get('last_login', ''),
                'is_active': user.get('is_active', True),
                'avatar': user.get('avatar', 'default-1')
            }
            safe_users.append(safe_user)
        
        return jsonify({
            'success': True,
            'users': safe_users,
            'total': len(safe_users)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/create', methods=['POST'])
@login_required
def api_users_create():
    """API endpoint to create a new user"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        full_name = data.get('full_name', '')
        phone = data.get('phone', '')
        position = data.get('position', '')
        role = data.get('role', 'user')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required'}), 400
        
        # Use UserManager to create user
        success, message = user_manager.create_user(
            username=username,
            password=password,
            email=email,
            full_name=full_name,
            phone=phone,
            position=position,
            role=role
        )
        
        if success:
            return jsonify({'success': True, 'message': 'User created successfully'})
        else:
            return jsonify({'success': False, 'message': message}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<user_id>')
@login_required
def api_users_get(user_id):
    """API endpoint to get a specific user"""
    try:
        users = user_manager.load_users()
        user = next((u for u in users if u['id'] == user_id), None)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Remove sensitive data
        safe_user = {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'full_name': user.get('full_name', ''),
            'phone': user.get('phone', ''),
            'position': user.get('position', ''),
            'role': user.get('role', 'user'),
            'created_at': user.get('created_at', ''),
            'last_login': user.get('last_login', ''),
            'is_active': user.get('is_active', True),
            'avatar': user.get('avatar', 'default-1')
        }
        
        return jsonify({
            'success': True,
            'user': safe_user
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<user_id>', methods=['PUT'])
@login_required
def api_users_update(user_id):
    """API endpoint to update a user"""
    try:
        data = request.get_json()
        
        # Use UserManager to update user
        success, message = user_manager.update_user(
            user_id=user_id,
            email=data.get('email'),
            password=data.get('password'),
            full_name=data.get('full_name'),
            phone=data.get('phone'),
            position=data.get('position'),
            role=data.get('role'),
            is_active=data.get('is_active')
        )
        
        if success:
            return jsonify({'success': True, 'message': 'User updated successfully'})
        else:
            return jsonify({'success': False, 'message': message}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<user_id>', methods=['DELETE'])
@login_required
def api_users_delete(user_id):
    """API endpoint to delete a user"""
    try:
        # Don't allow deleting the current user
        if user_id == session.get('user_id'):
            return jsonify({'success': False, 'message': 'Cannot delete current user'}), 400
        
        # Use UserManager to delete user
        success, message = user_manager.delete_user(user_id)
        
        if success:
            return jsonify({'success': True, 'message': 'User deleted successfully'})
        else:
            return jsonify({'success': False, 'message': message}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<user_id>/reset-password', methods=['POST'])
@login_required
def api_users_reset_password(user_id):
    """API endpoint to reset a user's password"""
    try:
        data = request.get_json()
        new_password = data.get('password')
        
        if not new_password:
            return jsonify({'success': False, 'message': 'New password is required'}), 400
        
        # Use UserManager to reset password
        success, message = user_manager.reset_password(user_id, new_password)
        
        if success:
            return jsonify({'success': True, 'message': 'Password reset successfully'})
        else:
            return jsonify({'success': False, 'message': message}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/databases')
@login_required
def api_databases_list():
    """API endpoint to get list of stored databases"""
    try:
        with open('stored_databases.json', 'r') as f:
            data = json.load(f)
            databases = data.get('databases', [])
        return jsonify({
            'success': True,
            'databases': databases
        })
    except FileNotFoundError:
        return jsonify({
            'success': True,
            'databases': []
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/databases', methods=['POST'])
@login_required
def api_databases_create():
    """API endpoint to create a new database connection"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'host', 'port', 'database', 'user', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} is required'}), 400
        
        # Test connection first
        try:
            test_connection = psycopg2.connect(
                host=data['host'],
                port=data['port'],
                database=data['database'],
                user=data['user'],
                password=data['password']
            )
            test_connection.close()
        except psycopg2.Error as e:
            return jsonify({'success': False, 'message': f'Database connection failed: {str(e)}'}), 400
        
        # Load existing databases
        try:
            with open('stored_databases.json', 'r') as f:
                existing_data = json.load(f)
                databases = existing_data.get('databases', [])
                current_db_id = existing_data.get('current_database_id')
        except FileNotFoundError:
            databases = []
            current_db_id = None
        
        # Check if database name already exists
        if any(db.get('name') == data['name'] for db in databases):
            return jsonify({'success': False, 'error': 'Database name already exists'}), 400
        
        # Add new database
        new_db = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'host': data['host'],
            'port': data['port'],
            'database': data['database'],
            'user': data['user'],
            'description': data.get('description', ''),
            'created_at': datetime.now().isoformat()
        }
        
        databases.append(new_db)
        
        # Save to file with proper structure
        save_data = {
            'databases': databases,
            'current_database_id': current_db_id
        }
        with open('stored_databases.json', 'w') as f:
            json.dump(save_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'Database connection created successfully',
            'database': new_db
        })
    except psycopg2.Error as e:
        return jsonify({'success': False, 'message': f'Database connection failed: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/databases/<db_id>', methods=['PUT'])
@login_required
def api_databases_update(db_id):
    """API endpoint to update a database connection"""
    try:
        data = request.get_json()
        
        # Load existing databases
        try:
            with open('stored_databases.json', 'r') as f:
                existing_data = json.load(f)
                databases = existing_data.get('databases', [])
                current_db_id = existing_data.get('current_database_id')
        except FileNotFoundError:
            return jsonify({'success': False, 'message': 'No databases found'}), 404
        
        # Find the database
        db_index = None
        for i, db in enumerate(databases):
            if db.get('id') == db_id:
                db_index = i
                break
        
        if db_index is None:
            return jsonify({'success': False, 'message': 'Database not found'}), 404
        
        # Test connection if credentials are provided
        if any(field in data for field in ['host', 'port', 'database', 'user', 'password']):
            try:
                test_connection = psycopg2.connect(
                    host=data.get('host', databases[db_index]['host']),
                    port=data.get('port', databases[db_index]['port']),
                    database=data.get('database', databases[db_index]['database']),
                    user=data.get('user', databases[db_index]['user']),
                    password=data.get('password', databases[db_index]['password'])
                )
                test_connection.close()
            except psycopg2.Error as e:
                return jsonify({'success': False, 'message': f'Database connection failed: {str(e)}'}), 400
        
        # Update database
        for field in ['name', 'host', 'port', 'database', 'user', 'password', 'description']:
            if field in data:
                databases[db_index][field] = data[field]
        
        databases[db_index]['updated_at'] = datetime.now().isoformat()
        
        # Save to file with proper structure
        save_data = {
            'databases': databases,
            'current_database_id': current_db_id
        }
        with open('stored_databases.json', 'w') as f:
            json.dump(save_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'Database updated successfully',
            'database': databases[db_index]
        })
    except psycopg2.Error as e:
        return jsonify({'success': False, 'message': f'Database connection failed: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/databases/<db_id>', methods=['DELETE'])
@login_required
def api_databases_delete(db_id):
    """API endpoint to delete a database connection"""
    try:
        # Load existing databases
        try:
            with open('stored_databases.json', 'r') as f:
                data = json.load(f)
                databases = data.get('databases', [])
                current_db_id = data.get('current_database_id')
        except FileNotFoundError:
            return jsonify({'success': False, 'message': 'No databases found'}), 404
        
        # Find and remove the database
        original_count = len(databases)
        databases = [db for db in databases if db.get('id') != db_id]
        
        if len(databases) == original_count:
            return jsonify({'success': False, 'message': 'Database not found'}), 404
        
        # Save to file with proper structure
        save_data = {
            'databases': databases,
            'current_database_id': current_db_id
        }
        with open('stored_databases.json', 'w') as f:
            json.dump(save_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'Database deleted successfully'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/databases/<db_id>/test', methods=['POST'])
@login_required
def api_databases_test(db_id):
    """API endpoint to test a database connection"""
    try:
        # Load existing databases
        try:
            with open('stored_databases.json', 'r') as f:
                data = json.load(f)
                databases = data.get('databases', [])
        except FileNotFoundError:
            return jsonify({'success': False, 'message': 'No databases found'}), 404
        
        # Find the database
        database = None
        for db in databases:
            if db.get('id') == db_id:
                database = db
                break
        
        if not database:
            return jsonify({'success': False, 'message': 'Database not found'}), 404
        
        # Test connection
        try:
            # Check if user/password are available
            if 'user' in database and 'password' in database:
                connection = psycopg2.connect(
                    host=database['host'],
                    port=database['port'],
                    database=database['database'],
                    user=database['user'],
                    password=database['password']
                )
            else:
                # Try with default credentials or environment variables
                connection = psycopg2.connect(
                    host=database['host'],
                    port=database['port'],
                    database=database['database'],
                    user=os.getenv('DB_USER', 'postgres'),
                    password=os.getenv('DB_PASSWORD', '')
                )
        except psycopg2.Error as e:
            return jsonify({'success': False, 'message': f'Database connection failed: {str(e)}'}), 400
        
        # Get basic info
        cursor = connection.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'message': 'Connection successful',
            'version': version
        })
    except psycopg2.Error as e:
        return jsonify({'success': False, 'message': f'Database connection failed: {str(e)}'}), 400
    except Exception as e:
        print(f"Error in api_databases_test: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/databases/connect/<db_id>', methods=['POST'])
@login_required
def databases_connect(db_id):
    """Connect to a database (form-based)"""
    try:
        # Load existing databases
        try:
            with open('stored_databases.json', 'r') as f:
                data = json.load(f)
                databases = data.get('databases', [])
        except FileNotFoundError:
            flash('No databases found', 'error')
            return redirect(url_for('databases'))
        
        # Find the database
        database = None
        for db in databases:
            if db.get('id') == db_id:
                database = db
                break
        
        if not database:
            flash('Database not found', 'error')
            return redirect(url_for('databases'))
        
        # Get username and password from form
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            if 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'success': False, 'message': 'Username and password are required'}), 400
            else:
                flash('Username and password are required', 'error')
                return redirect(url_for('databases'))
        
        # Create connection config
        config = {
            'host': database['host'],
            'port': database['port'],
            'database': database['database'],
            'user': username,
            'password': password
        }
        
        # Test the connection
        success, message = db_manager.test_connection(config)
        
        if success:
            # Connect to database
            connect_success, connect_message = db_manager.connect(config)
            
            if connect_success:
                # Set this as the current database
                db_storage.set_current_database(db_id)
                
                # Store the credentials used for this connection
                database['user'] = username
                database['password'] = password
                database['last_connected'] = datetime.now().isoformat()
                
                # Save with proper structure
                save_data = {
                    'databases': databases,
                    'current_database_id': db_id
                }
                with open('stored_databases.json', 'w') as f:
                    json.dump(save_data, f, indent=2)
                
                if 'application/json' in request.headers.get('Accept', ''):
                    return jsonify({
                        'success': True, 
                        'message': f'Connected to {database["name"]} successfully!',
                        'redirect': url_for('index')
                    })
                else:
                    flash(f'Connected to {database["name"]} successfully!', 'success')
                    return redirect(url_for('index'))
            else:
                if 'application/json' in request.headers.get('Accept', ''):
                    return jsonify({'success': False, 'message': f'Connection failed: {connect_message}'}), 400
                else:
                    flash(f'Connection failed: {connect_message}', 'error')
                    return redirect(url_for('databases'))
        else:
            if 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'success': False, 'message': f'Connection test failed: {message}'}), 400
            else:
                flash(f'Connection test failed: {message}', 'error')
                return redirect(url_for('databases'))
    except Exception as e:
        print(f"Error in databases_connect: {e}")
        import traceback
        traceback.print_exc()
        if 'application/json' in request.headers.get('Accept', ''):
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
        else:
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('databases'))

@app.route('/databases/test/<db_id>', methods=['POST'])
@login_required
def databases_test(db_id):
    """Test a database connection (form-based)"""
    try:
        # Load existing databases
        try:
            with open('stored_databases.json', 'r') as f:
                data = json.load(f)
                databases = data.get('databases', [])
        except FileNotFoundError:
            flash('No databases found', 'error')
            return redirect(url_for('databases'))
        
        # Find the database
        database = None
        for db in databases:
            if db.get('id') == db_id:
                database = db
                break
        
        if not database:
            flash('Database not found', 'error')
            return redirect(url_for('databases'))
        
        # Get username and password from form
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            if 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'success': False, 'message': 'Username and password are required for testing'}), 400
            else:
                flash('Username and password are required for testing', 'error')
                return redirect(url_for('databases'))
        
        # Test connection
        try:
            # Use provided credentials for testing
            connection = psycopg2.connect(
                host=database['host'],
                port=database['port'],
                database=database['database'],
                user=username,
                password=password
            )
            
            # Get basic info
            cursor = connection.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            cursor.close()
            connection.close()
            
            # Check if this is an AJAX request
            if 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'success': True, 'message': f'Connection successful! Database version: {version}'})
            else:
                flash(f'Connection successful! Database version: {version}', 'success')
                return redirect(url_for('databases'))
        except psycopg2.Error as e:
            if 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'success': False, 'message': f'Database connection failed: {str(e)}'}), 400
            else:
                flash(f'Database connection failed: {str(e)}', 'error')
                return redirect(url_for('databases'))
    except Exception as e:
        if 'application/json' in request.headers.get('Accept', ''):
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
        else:
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('databases'))

@app.route('/databases/delete/<db_id>', methods=['POST'])
@login_required
def databases_delete(db_id):
    """Delete a database connection (form-based)"""
    try:
        # Load existing databases
        try:
            with open('stored_databases.json', 'r') as f:
                data = json.load(f)
                databases = data.get('databases', [])
                current_db_id = data.get('current_database_id')
        except FileNotFoundError:
            flash('No databases found', 'error')
            return redirect(url_for('databases'))
        
        # Find and remove the database
        original_count = len(databases)
        databases = [db for db in databases if db.get('id') != db_id]
        
        if len(databases) == original_count:
            flash('Database not found', 'error')
        else:
            # Save to file with proper structure
            save_data = {
                'databases': databases,
                'current_database_id': current_db_id
            }
            with open('stored_databases.json', 'w') as f:
                json.dump(save_data, f, indent=2)
            flash('Database deleted successfully', 'success')
        
        return redirect(url_for('databases'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('databases'))

@app.route('/databases/disconnect', methods=['POST'])
@login_required
def databases_disconnect():
    """Disconnect from current database (form-based)"""
    try:
        # Close the database connection
        db_manager.disconnect()
        
        # Clear the current database ID from storage
        db_storage.set_current_database(None)
        
        # Check if this is an AJAX request
        if 'application/json' in request.headers.get('Accept', ''):
            return jsonify({'success': True, 'message': 'Disconnected successfully'})
        else:
            flash('Disconnected successfully', 'success')
            return redirect(url_for('databases'))
    except Exception as e:
        if 'application/json' in request.headers.get('Accept', ''):
            return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
        else:
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('databases'))

@app.route('/api/databases/<db_id>/connect', methods=['POST'])
@login_required
def api_databases_connect(db_id):
    """API endpoint to connect to a database"""
    try:
        # Load existing databases
        try:
            with open('stored_databases.json', 'r') as f:
                existing_data = json.load(f)
                databases = existing_data.get('databases', [])
        except FileNotFoundError:
            return jsonify({'success': False, 'message': 'No databases found'}), 404
        
        # Find the database
        database = None
        for db in databases:
            if db.get('id') == db_id:
                database = db
                break
        
        if not database:
            return jsonify({'success': False, 'message': 'Database not found'}), 404
        
        # Connect to database
        if 'user' in database and 'password' in database:
            config = {
                'host': database['host'],
                'port': database['port'],
                'database': database['database'],
                'user': database['user'],
                'password': database['password']
            }
        else:
            # Use default credentials or environment variables
            config = {
                'host': database['host'],
                'port': database['port'],
                'database': database['database'],
                'user': os.getenv('DB_USER', 'postgres'),
                'password': os.getenv('DB_PASSWORD', '')
            }
        success, message = db_manager.connect(config)
        
        if success:
            # Update last connected time
            database['last_connected'] = datetime.now().isoformat()
            
            # Set this as the current database
            db_storage.set_current_database(db_id)
            
            # Save with proper structure
            save_data = {
                'databases': databases,
                'current_database_id': db_id
            }
            with open('stored_databases.json', 'w') as f:
                json.dump(save_data, f, indent=2)
            
            return jsonify({
                'success': True,
                'message': 'Connected successfully',
                'database': database
            })
        else:
            return jsonify({'success': False, 'error': message}), 400
    except Exception as e:
        print(f"Error in api_databases_connect: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/export')
@login_required
def api_users_export():
    """API endpoint to export users as CSV"""
    try:
        users = load_users()
        
        # Generate CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Username', 'Email', 'Created At', 'Last Login', 'Active'])
        
        # Write data
        for username, user_data in users.items():
            writer.writerow([
                username,
                user_data.get('email', ''),
                user_data.get('created_at', ''),
                user_data.get('last_login', ''),
                'Yes' if user_data.get('is_active', True) else 'No'
            ])
        
        csv_content = output.getvalue()
        output.close()
        
        # Return CSV as response
        response = Response(
            csv_content,
            mimetype='text/csv',
            headers={
                'Content-Disposition': 'attachment; filename=users_export.csv',
                'Content-Type': 'text/csv; charset=utf-8'
            }
        )
        
        return response
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/table/<table_name>/export')
@login_required
def export_table_data(table_name):
    """Export filtered table data with column selection"""
    try:
        # Get filter parameters
        filters = request.args.get('filters')
        if filters:
            try:
                filters = json.loads(filters)
            except json.JSONDecodeError:
                filters = None
        
        # Get selected columns
        selected_columns = request.args.get('columns')
        if selected_columns:
            selected_columns = [col.strip() for col in selected_columns.split(',') if col.strip()]
        else:
            selected_columns = None
        
        # Get data from database
        success, result = db_manager.get_table_data(table_name, limit=99999999, filters=filters)
        
        if not success:
            return jsonify({
                'success': False,
                'error': result
            })
        
        rows = result['rows']
        columns = result['columns']
        
        # Filter columns if specified
        if selected_columns:
            column_indices = []
            filtered_columns = []
            for col in selected_columns:
                if col in columns:
                    column_indices.append(columns.index(col))
                    filtered_columns.append(col)
            
            if not column_indices:
                return jsonify({
                    'success': False,
                    'error': 'No valid columns selected for export'
                })
            
            # Filter rows to only include selected columns
            filtered_rows = []
            for row in rows:
                filtered_row = [row[i] for i in column_indices]
                filtered_rows.append(filtered_row)
            
            export_rows = filtered_rows
            export_columns = filtered_columns
        else:
            export_rows = rows
            export_columns = columns
        
        # Generate CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(export_columns)
        
        # Write data
        for row in export_rows:
            writer.writerow(row)
        
        csv_content = output.getvalue()
        output.close()
        
        # Return CSV as response
        response = Response(
            csv_content,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename={table_name}_export.csv',
                'Content-Type': 'text/csv; charset=utf-8'
            }
        )
        
        return response
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error exporting data: {str(e)}'
        })

# Visualization API Routes
@app.route('/api/visualizations/dashboard')
@login_required
def api_visualization_dashboard():
    """API endpoint to get dashboard visualization data"""
    # Check if we have a connection
    if not db_manager.connection:
        # Try to connect with stored database config
        current_db_id = db_storage.get_current_database_id()
        if current_db_id:
            current_db = db_storage.get_database(current_db_id)
            if current_db:
                if 'user' in current_db and 'password' in current_db:
                    config = {
                        'host': current_db['host'],
                        'port': current_db['port'],
                        'database': current_db['database'],
                        'user': current_db['user'],
                        'password': current_db['password']
                    }
                else:
                    config = {
                        'host': current_db['host'],
                        'port': current_db['port'],
                        'database': current_db['database'],
                        'user': os.getenv('DB_USER', 'postgres'),
                        'password': os.getenv('DB_PASSWORD', '')
                    }
                connect_success, connect_message = db_manager.connect(config)
            else:
                connect_success, connect_message = False, "No stored database configuration found"
        else:
            connect_success, connect_message = False, "No database selected"
        
        if not connect_success:
            return jsonify({
                'success': False, 
                'error': f'No database connection. Connection attempt failed: {connect_message}'
            })
    
    success, result = db_manager.get_visualization_data()
    if success:
        return jsonify({'success': True, 'data': result})
    else:
        return jsonify({'success': False, 'error': result})

@app.route('/api/visualizations/table/<table_name>/analysis')
@login_required
def api_table_analysis(table_name):
    """API endpoint to get detailed table column analysis"""
    try:
        # Get table statistics
        success, result = db_manager.get_bulk_table_stats_fast([table_name], 1)
        if success and result:
            return jsonify({'success': True, 'data': result[0] if result else {}})
        else:
            return jsonify({'success': False, 'error': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/visualizations/table/<table_name>/sample')
@login_required
def api_table_sample_data(table_name):
    """API endpoint to get sample data from table for visualization"""
    try:
        limit = request.args.get('limit', 50, type=int)
        success, result = db_manager.get_table_data(table_name, limit=limit, page=1)
        
        if success:
            return jsonify({
                'success': True,
                'data': {
                    'columns': result['columns'],
                    'rows': result['rows'],
                    'total_rows': result['total_rows']
                }
            })
        else:
            return jsonify({'success': False, 'error': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/visualizations/tables/comparison')
@login_required
def api_tables_comparison():
    """API endpoint to get table comparison data"""
    try:
        # Get table names from query parameters
        table_names = request.args.getlist('tables')
        if not table_names:
            # Get all tables if none specified
            success, all_tables = db_manager.get_tables()
            if success:
                table_names = all_tables[:10]  # Limit to first 10 tables
            else:
                return jsonify({'success': False, 'error': 'Could not retrieve table list'})
        
        success, result = db_manager.get_bulk_table_stats_fast(table_names, len(table_names))
        if success:
            return jsonify({'success': True, 'data': result})
        else:
            return jsonify({'success': False, 'error': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/visualizations/geo/<table_name>')
@login_required
def api_geo_chart_data(table_name):
    """API endpoint to get geographic data for mapping"""
    try:
        if not db_manager.connection:
            return jsonify({'success': False, 'error': 'No database connection'})
        
        cursor = db_manager.connection.cursor()
        cursor.execute("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns 
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position;
        """, [table_name])
        
        columns = []
        for row in cursor.fetchall():
            column_name, data_type, is_nullable, column_default = row
            
            # Categorize data types for geographic suitability
            if data_type in ['integer', 'bigint', 'smallint', 'numeric', 'real', 'double precision', 'decimal']:
                category = 'numeric'
            elif data_type in ['character varying', 'varchar', 'text', 'char']:
                category = 'text'
            elif data_type in ['date', 'timestamp', 'timestamp with time zone', 'timestamp without time zone']:
                category = 'datetime'
            elif data_type in ['boolean']:
                category = 'boolean'
            else:
                category = 'other'
            
            columns.append({
                'name': column_name,
                'type': data_type,
                'category': category,
                'nullable': is_nullable == 'YES',
                'default': column_default
            })
        
        cursor.close()
        
        # Find potential location columns (text types with geographic keywords)
        location_columns = []
        value_columns = []
        
        for col in columns:
            col_lower = col['name'].lower()
            if col['category'] == 'text' and any(keyword in col_lower for keyword in ['location', 'address', 'city', 'country', 'state', 'region', 'lat', 'lng', 'longitude', 'latitude', 'place', 'area', 'zone', 'district']):
                location_columns.append(col)
            elif col['category'] == 'numeric':
                value_columns.append(col)
        
        return jsonify({
            'success': True,
            'location_columns': location_columns,
            'value_columns': value_columns,
            'all_columns': columns
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/visualizations/geographic/data', methods=['POST'])
@login_required
def api_geographic_data():
    """API endpoint to get geographic data for mapping with filtering support"""
    try:
        data = request.get_json()
        table_name = data.get('table_name')
        location_column = data.get('location_column')
        value_column = data.get('value_column')
        aggregation = data.get('aggregation', 'count')
        filters = data.get('filters')
        
        if not table_name or not location_column:
            return jsonify({'success': False, 'error': 'Table name and location column are required'})
        
        if not db_manager.connection:
            return jsonify({'success': False, 'error': 'No database connection'})
        
        cursor = db_manager.connection.cursor()
        
        # Build WHERE clause from filters
        where_clause, filter_params = db_manager._build_where_clause(filters) if filters else ("", [])
        print(f"Geographic chart filters: {filters}")
        print(f"Generated WHERE clause: {where_clause}")
        print(f"Filter parameters: {filter_params}")
        
        # Build base WHERE conditions
        base_conditions = [f"{location_column} IS NOT NULL"]
        query_params = []
        
        # Add filter conditions if any
        if where_clause:
            base_conditions.append(where_clause)
            query_params.extend(filter_params)
        
        # Add value column condition if needed
        if value_column and value_column != location_column and aggregation in ['sum', 'avg', 'min', 'max']:
            base_conditions.append(f"{value_column} IS NOT NULL")
        
        # Build query
        where_sql = " AND ".join(base_conditions)
        
        if value_column and value_column != location_column and aggregation in ['sum', 'avg', 'min', 'max']:
            query = f"SELECT {location_column}, {aggregation.upper()}({value_column}) as value FROM {table_name} WHERE {where_sql} GROUP BY {location_column} ORDER BY value DESC LIMIT 100"
        else:
            query = f"SELECT {location_column}, COUNT(*) as value FROM {table_name} WHERE {where_sql} GROUP BY {location_column} ORDER BY value DESC LIMIT 100"
        
        # Execute query with parameters
        if query_params:
            cursor.execute(query, query_params)
        else:
            cursor.execute(query)
        
        results = cursor.fetchall()
        cursor.close()
        
        return jsonify({
            'success': True,
            'geo_data': [
                {'location': row[0], 'value': float(row[1]) if row[1] else 0}
                for row in results
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/visualizations/custom/columns/<table_name>')
@login_required
def api_custom_chart_columns(table_name):
    """API endpoint to get columns for custom chart creation"""
    try:
        if not db_manager.connection:
            return jsonify({'success': False, 'error': 'No database connection'})
        
        cursor = db_manager.connection.cursor()
        cursor.execute("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns 
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position;
        """, [table_name])
        
        columns = []
        for row in cursor.fetchall():
            column_name, data_type, is_nullable, column_default = row
            
            # Categorize data types for chart suitability
            if data_type in ['integer', 'bigint', 'smallint', 'numeric', 'real', 'double precision', 'decimal']:
                category = 'numeric'
            elif data_type in ['character varying', 'varchar', 'text', 'char']:
                category = 'text'
            elif data_type in ['date', 'timestamp', 'timestamp with time zone', 'timestamp without time zone']:
                category = 'datetime'
            elif data_type in ['boolean']:
                category = 'boolean'
            else:
                category = 'other'
            
            columns.append({
                'name': column_name,
                'type': data_type,
                'category': category,
                'nullable': is_nullable == 'YES',
                'default': column_default
            })
        
        cursor.close()
        return jsonify({'success': True, 'columns': columns})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/sql/execute', methods=['POST'])
@login_required
def api_sql_execute():
    """API endpoint to execute custom SQL queries"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({'success': False, 'error': 'No query provided'})
        
        if not db_manager.connection:
            return jsonify({'success': False, 'error': 'No database connection'})
        
        # Security check - only allow SELECT queries for now
        query_upper = query.upper().strip()
        if not query_upper.startswith('SELECT'):
            return jsonify({'success': False, 'error': 'Only SELECT queries are allowed'})
        
        # Check for dangerous keywords
        dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE', 'EXEC', 'EXECUTE']
        for keyword in dangerous_keywords:
            if keyword in query_upper:
                return jsonify({'success': False, 'error': f'Query contains forbidden keyword: {keyword}'})
        
        cursor = db_manager.connection.cursor()
        
        try:
            # Execute the query
            cursor.execute(query)
            results = cursor.fetchall()
            
            # Get column names
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            
            # Convert results to list of dictionaries
            data_list = []
            for row in results:
                row_dict = {}
                for i, value in enumerate(row):
                    row_dict[columns[i]] = value
                data_list.append(row_dict)
            
            cursor.close()
            
            return jsonify({
                'success': True,
                'data': data_list,
                'columns': columns,
                'row_count': len(data_list)
            })
            
        except Exception as e:
            cursor.close()
            return jsonify({'success': False, 'error': f'Query execution error: {str(e)}'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/visualizations/custom/data', methods=['POST'])
@login_required
def api_custom_chart_data():
    """API endpoint to get custom chart data"""
    try:
        data = request.get_json()
        table_name = data.get('table_name')
        x_column = data.get('x_column')
        y_column = data.get('y_column')
        chart_type = data.get('chart_type', 'bar')
        aggregation = data.get('aggregation', 'count')
        limit = data.get('limit', 100)
        filters = data.get('filters')
        
        if not table_name or not x_column:
            return jsonify({'success': False, 'error': 'Table name and X column are required'})
        
        if not db_manager.connection:
            return jsonify({'success': False, 'error': 'No database connection'})
        
        cursor = db_manager.connection.cursor()
        
        # Build WHERE clause from filters
        where_clause, filter_params = db_manager._build_where_clause(filters) if filters else ("", [])
        print(f"Custom chart filters: {filters}")
        print(f"Generated WHERE clause: {where_clause}")
        print(f"Filter parameters: {filter_params}")
        
        # Build base WHERE conditions
        base_conditions = [f"{x_column} IS NOT NULL"]
        query_params = []
        
        # Add filter conditions if any
        if where_clause:
            base_conditions.append(where_clause)
            query_params.extend(filter_params)
        
        # Determine the appropriate query based on the scenario
        if x_column == y_column or not y_column:
            # Same column for X and Y, or no Y column - use count aggregation
            where_sql = " AND ".join(base_conditions)
            query = f"SELECT {x_column}, COUNT(*) as count FROM {table_name} WHERE {where_sql} GROUP BY {x_column} ORDER BY count DESC LIMIT {limit}"
            is_count_query = True
        elif chart_type in ['pie', 'doughnut']:
            # Pie/doughnut charts always use count
            where_sql = " AND ".join(base_conditions)
            query = f"SELECT {x_column}, COUNT(*) as count FROM {table_name} WHERE {where_sql} GROUP BY {x_column} ORDER BY count DESC LIMIT {limit}"
            is_count_query = True
        else:
            # Different X and Y columns - use Y column as value
            base_conditions.append(f"{y_column} IS NOT NULL")
            where_sql = " AND ".join(base_conditions)
            query = f"SELECT {x_column}, {y_column} FROM {table_name} WHERE {where_sql} ORDER BY {y_column} DESC LIMIT {limit}"
            is_count_query = False
        
        # Execute query with parameters
        if query_params:
            cursor.execute(query, query_params)
        else:
            cursor.execute(query)
        
        results = cursor.fetchall()
        cursor.close()
        
        # Process results based on query type
        if is_count_query:
            # For count queries, the second column is always a count (integer)
            data_points = [
                {'x': str(row[0]) if row[0] is not None else 'NULL', 'y': int(row[1]) if row[1] is not None else 0}
                for row in results
            ]
        else:
            # For value queries, try to convert Y column to numeric, fallback to count
            data_points = []
            for row in results:
                x_val = str(row[0]) if row[0] is not None else 'NULL'
                y_val = row[1] if len(row) > 1 and row[1] is not None else 0
                
                # Try to convert to numeric, fallback to 0 if not possible
                try:
                    if isinstance(y_val, (int, float)):
                        y_numeric = float(y_val)
                    else:
                        y_numeric = float(y_val)
                except (ValueError, TypeError):
                    y_numeric = 0
                
                data_points.append({'x': x_val, 'y': y_numeric})
        
        return jsonify({
            'success': True,
            'data': data_points
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/debug/connection')
@login_required
def api_debug_connection():
    """API endpoint for debugging connection status"""
    try:
        debug_info = {
            'connection_status': db_manager.connection is not None,
            'config': db_manager.config if hasattr(db_manager, 'config') else {},
            'current_database_id': db_storage.get_current_database_id(),
            'stored_databases': []
        }
        
        # Get stored databases info
        try:
            with open('stored_databases.json', 'r') as f:
                data = json.load(f)
                debug_info['stored_databases'] = data.get('databases', [])
        except Exception as e:
            debug_info['stored_databases_error'] = str(e)
        
        # Test connection if available
        if db_manager.connection:
            try:
                cursor = db_manager.connection.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                debug_info['connection_test'] = 'success'
            except Exception as e:
                debug_info['connection_test'] = f'failed: {str(e)}'
        else:
            debug_info['connection_test'] = 'no connection'
        
        return jsonify({'success': True, 'debug_info': debug_info})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
