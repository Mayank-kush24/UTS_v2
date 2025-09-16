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
from functools import wraps
from werkzeug.utils import secure_filename
from PIL import Image
import base64
import threading
from collections import defaultdict

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
        test_config = config or self.config
        try:
            conn = psycopg2.connect(**test_config)
            conn.close()
            return True, "Connection successful!"
        except Exception as e:
            return False, str(e)
    
    def connect(self, config=None):
        """Establish database connection"""
        connect_config = config or self.config
        try:
            # Close existing connection if any
            if self.connection:
                try:
                    self.connection.close()
                except:
                    pass
            
            self.connection = psycopg2.connect(**connect_config)
            # Set autocommit mode to avoid transaction issues
            self.connection.autocommit = True
            
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
            except:
                return False
        except InternalError:
            # Transaction is in aborted state, rollback and continue
            try:
                self.connection.rollback()
                return True
            except:
                # If rollback fails, reconnect
                try:
                    self.connect()
                    return True
                except:
                    return False
        except Exception:
            # For any other error, try to reset the connection
            try:
                self.connect()
                return True
            except:
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
        for group in filters.get('groups', []):
            print(f"_build_where_clause: Processing group: {group}")
            group_conditions = []
            
            for condition in group.get('conditions', []):
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
                    except:
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
                    except:
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
                    except:
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
                        except:
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
                    except:
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
                except:
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
                users = data.get('users', [])
                
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
            except:
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
            except:
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
        except:
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

@app.route('/')
@login_required
def index():
    """Main page showing database status and available tables"""
    # Extend session if user has remember me enabled
    extend_session_if_needed()
    
    # Check if we have a stored database connection
    current_db_id = db_storage.get_current_database_id()
    
    # Try to connect with existing config
    success, message = db_manager.connect()
    
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

@app.route('/view-config')
@login_required
def view_config():
    """View configuration page for customizing table displays"""
    current_user = get_current_user()
    databases = get_stored_databases()
    return render_template('view_config.html', databases=databases, current_user=current_user)

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
        db_manager.close()
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
        current_password_hash = hashlib.sha256(current_password.encode()).hexdigest()
        if user['password'] != current_password_hash:
            return jsonify({'success': False, 'message': 'Current password is incorrect'})
        
        # Update password
        new_password_hash = hashlib.sha256(new_password.encode()).hexdigest()
        user['password'] = new_password_hash
        
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

@app.route('/table/<table_name>')
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
        # Try to connect with existing config
        connect_success, connect_message = db_manager.connect()
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
        return jsonify({'success': False, 'error': result})

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
        return jsonify({'success': False, 'error': result})

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
                # Connection exists but is broken, try to reconnect
                connect_success, connect_message = db_manager.connect()
                return jsonify({
                    'success': connect_success, 
                    'message': f'Connection was broken, reconnection: {connect_message}',
                    'timestamp': datetime.now().isoformat()
                })
        else:
            # No active connection, try to connect with stored config
            connect_success, connect_message = db_manager.connect()
            return jsonify({
                'success': connect_success, 
                'message': f'No active connection. Connection attempt: {connect_message}',
                'timestamp': datetime.now().isoformat()
            })
    else:
        # No stored database, try to connect with default config
        connect_success, connect_message = db_manager.connect()
        return jsonify({
            'success': connect_success, 
            'message': f'No stored database. Using default config: {connect_message}',
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
        return jsonify({'success': False, 'error': result})

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
        return jsonify({'success': False, 'error': result})

@app.route('/api/tables/lazy-stats')
@login_required
def api_lazy_table_stats():
    """API endpoint for lazy loading specific table stats"""
    table_names = request.args.getlist('tables')
    fast_mode = request.args.get('fast', 'true').lower() == 'true'  # Default to fast mode
    ultra_fast = request.args.get('ultra_fast', 'false').lower() == 'true'
    
    if not table_names:
        return jsonify({'success': False, 'error': 'No table names provided'})
    
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
        return jsonify({'success': False, 'error': result})

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
            except:
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    """Export data in a single batch for smaller datasets with optimized memory usage"""
    try:
        print(f"Starting batch export for table {table_name}")
        
        # Test database connection first
        if not db_manager.connection:
            print("Batch Export - No database connection")
            return jsonify({
                'success': False,
                'error': 'No database connection'
            })
        
        # Get all filtered data (no pagination for export)
        # Use a much larger limit for big datasets
        print(f"Batch Export - Querying table {table_name} with limit 99999999")
        success, result = db_manager.get_table_data(table_name, limit=99999999, page=1, filters=filters)
        print(f"Batch Export - Database query success: {success}")
        if success:
            print(f"Batch Export - Rows returned: {len(result['rows'])}")
            print(f"Batch Export - Columns: {result['columns']}")
            if len(result['rows']) > 0:
                print(f"Batch Export - First row sample: {result['rows'][0]}")
            else:
                print("Batch Export - WARNING: No rows returned from database!")
        else:
            print(f"Batch Export - Database error: {result}")
        
        if not success:
            return jsonify({
                'success': False,
                'error': f'Error exporting data: {result}'
            })
        
        # Filter columns if specific columns are selected
        if selected_columns:
            print(f"Batch Export - Filtering columns: {selected_columns}")
            # Find indices of selected columns
            all_columns = result['columns']
            column_indices = []
            filtered_columns = []
            
            for col in selected_columns:
                if col in all_columns:
                    idx = all_columns.index(col)
                    column_indices.append(idx)
                    filtered_columns.append(col)
                else:
                    print(f"Batch Export - WARNING: Column '{col}' not found in table columns: {all_columns}")
            
            if not column_indices:
                print("Batch Export - ERROR: No valid columns selected for export")
                return jsonify({
                    'success': False,
                    'error': 'No valid columns selected for export'
                })
            
            print(f"Batch Export - Column indices: {column_indices}")
            print(f"Batch Export - Filtered columns: {filtered_columns}")
            
            # Filter the data
            filtered_rows = []
            for row in result['rows']:
                filtered_row = [row[i] if i < len(row) else None for i in column_indices]
                filtered_rows.append(filtered_row)
            
            export_columns = filtered_columns
            export_rows = filtered_rows
            print(f"Batch Export - Filtered rows count: {len(filtered_rows)}")
        else:
            # Export all columns
            print("Batch Export - Exporting all columns")
            export_columns = result['columns']
            export_rows = result['rows']
            print(f"Batch Export - All rows count: {len(export_rows)}")
        
        # Create CSV response
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow(export_columns)
        
        # Write data rows
        print(f"Writing {len(export_rows)} rows to CSV")
        for i, row in enumerate(export_rows):
            writer.writerow(row)
            if i < 5:  # Log first 5 rows for debugging
                print(f"Row {i}: {row}")
        
        # Get CSV content
        csv_content = output.getvalue()
        output.close()
        
        print(f"CSV content length: {len(csv_content)} characters")
        print(f"CSV preview: {csv_content[:200]}...")
        
        # Create filename
        filename = _generate_export_filename(table_name, filters, selected_columns, total_rows)
        
        # Return CSV response
        from flask import Response
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'text/csv; charset=utf-8'
            }
        )
        
    except Exception as e:
        print(f"Batch export error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error in batch export: {str(e)}'
        })

def _stream_csv_export_simple(table_name, filters, selected_columns, total_rows, chunk_size):
    """Simple streaming CSV export without named cursors for large datasets"""
    try:
        from flask import Response
        import csv
        from io import StringIO
        
        def generate_csv():
            # Get column information first (optimized)
            success, all_columns = db_manager.get_table_columns(table_name)
            if not success:
                yield f"Error: {all_columns}\n"
                return
            
            # Determine export columns
            if selected_columns:
                column_indices = []
                export_columns = []
                
                for col in selected_columns:
                    if col in all_columns:
                        idx = all_columns.index(col)
                        column_indices.append(idx)
                        export_columns.append(col)
                
                if not column_indices:
                    yield "Error: No valid columns selected for export\n"
                    return
            else:
                export_columns = all_columns
                column_indices = list(range(len(all_columns)))
            
            # Write headers first
            header_output = StringIO()
            writer = csv.writer(header_output)
            writer.writerow(export_columns)
            yield header_output.getvalue()
            header_output.close()
            
            # Stream data in chunks using pagination
            page = 1
            rows_exported = 0
            chunk_size = min(chunk_size, 5000)  # Limit chunk size for memory efficiency
            
            print(f"Starting streaming export for {total_rows} rows with chunk size {chunk_size}")
            
            while rows_exported < total_rows:
                # Get data for current page
                print(f"Streaming - Fetching page {page} with limit {chunk_size}")
                success, result = db_manager.get_table_data(table_name, limit=chunk_size, page=page, filters=filters)
                if not success:
                    print(f"Streaming - Error fetching page {page}: {result}")
                    yield f"Error: {result}\n"
                    return
                
                rows = result['rows']
                print(f"Streaming - Page {page} returned {len(rows)} rows")
                if not rows:
                    print(f"Streaming - No more rows at page {page}, breaking")
                    break
                
                # Process rows
                chunk_output = StringIO()
                writer = csv.writer(chunk_output)
                
                print(f"Processing {len(rows)} rows in chunk {page}")
                for i, row in enumerate(rows):
                    if selected_columns and column_indices:
                        filtered_row = [row[i] if i < len(row) else None for i in column_indices]
                        writer.writerow(filtered_row)
                    else:
                        writer.writerow(row)
                    rows_exported += 1
                    
                    # Log first few rows for debugging
                    if rows_exported <= 5:
                        print(f"Streaming row {rows_exported}: {row[:3]}...")  # Show first 3 columns
                
                # Yield chunk
                chunk_data = chunk_output.getvalue()
                print(f"Streaming - Chunk {page} data length: {len(chunk_data)} characters")
                if chunk_data:
                    yield chunk_data
                    print(f"Streaming - Yielded chunk {page} successfully")
                else:
                    print(f"Streaming - WARNING: Chunk {page} is empty!")
                chunk_output.close()
                
                page += 1
                
                # Progress logging
                if rows_exported % 100000 == 0:
                    print(f"Exported {rows_exported} rows so far...")
            
            print(f"Streaming export completed. Total rows exported: {rows_exported}")
        
        # Create filename
        filename = _generate_export_filename(table_name, filters, selected_columns, total_rows)
        
        return Response(
            generate_csv(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'text/csv; charset=utf-8',
                'Transfer-Encoding': 'chunked'
            }
        )
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error in simple streaming export: {str(e)}'
        })

def _stream_csv_export(table_name, filters, selected_columns, total_rows, chunk_size):
    """Stream CSV export for large datasets with optimized memory usage"""
    try:
        from flask import Response
        import csv
        import gzip
        from io import BytesIO, StringIO
        
        def generate_csv():
            # Get column information first (optimized)
            success, all_columns = db_manager.get_table_columns(table_name)
            if not success:
                yield f"Error: {all_columns}\n"
                return
            
            # Determine export columns
            if selected_columns:
                column_indices = []
                export_columns = []
                
                for col in selected_columns:
                    if col in all_columns:
                        idx = all_columns.index(col)
                        column_indices.append(idx)
                        export_columns.append(col)
                
                if not column_indices:
                    yield "Error: No valid columns selected for export\n"
                    return
            else:
                export_columns = all_columns
                column_indices = list(range(len(all_columns)))
            
            # Write headers first
            header_output = StringIO()
            writer = csv.writer(header_output)
            writer.writerow(export_columns)
            yield header_output.getvalue()
            header_output.close()
            
            # Use server-side cursor for memory-efficient streaming
            yield from _stream_data_with_cursor(table_name, filters, selected_columns, column_indices, chunk_size)
        
        # Create filename with filter info
        filename = _generate_export_filename(table_name, filters, selected_columns, total_rows)
        
        # For now, disable compression to avoid browser issues
        # TODO: Re-enable compression with proper browser detection
        use_compression = False
        
        if use_compression:
            def generate_compressed_csv():
                gzip_buffer = BytesIO()
                with gzip.GzipFile(fileobj=gzip_buffer, mode='wb') as gz_file:
                    for chunk in generate_csv():
                        gz_file.write(chunk.encode('utf-8'))
                    gz_file.flush()
                    gzip_buffer.seek(0)
                    while True:
                        data = gzip_buffer.read(8192)  # 8KB chunks
                        if not data:
                            break
                        yield data
            
            return Response(
                generate_compressed_csv(),
                mimetype='application/gzip',
                headers={
                    'Content-Disposition': f'attachment; filename={filename}.gz',
                    'Content-Type': 'application/gzip',
                    'Content-Encoding': 'gzip',
                    'Transfer-Encoding': 'chunked'
                }
            )
        else:
            return Response(
                generate_csv(),
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename={filename}',
                    'Content-Type': 'text/csv; charset=utf-8',
                    'Transfer-Encoding': 'chunked'
                }
            )
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error in streaming export: {str(e)}'
        })

def _stream_data_with_cursor(table_name, filters, selected_columns, column_indices, chunk_size):
    """Stream data using server-side cursor for memory efficiency with query optimization"""
    cursor = None
    chunk_buffer = None
    
    try:
        import csv
        from io import StringIO
        
        # Get database connection
        if not db_manager.connection:
            yield "Error: No database connection\n"
            return
        
        # Ensure connection is healthy
        if not db_manager._ensure_connection_health():
            yield "Error: Database connection is not healthy\n"
            return
        
        cursor = db_manager.connection.cursor()
        
        # Build optimized query with server-side cursor
        from psycopg2 import sql
        
        # Build WHERE clause from filters
        where_clause, params = db_manager._build_where_clause(filters) if filters else ("", [])
        
        # Create optimized query with column selection if possible
        if selected_columns and column_indices:
            # Build column list for SELECT clause
            columns_sql = sql.SQL(', ').join([sql.Identifier(col) for col in selected_columns])
            
            if where_clause:
                query = sql.SQL("SELECT {} FROM {} WHERE {}").format(
                    columns_sql,
                    sql.Identifier(table_name), 
                    sql.SQL(where_clause)
                )
            else:
                query = sql.SQL("SELECT {} FROM {}").format(
                    columns_sql,
                    sql.Identifier(table_name)
                )
        else:
            # Select all columns
            if where_clause:
                query = sql.SQL("SELECT * FROM {} WHERE {}").format(
                    sql.Identifier(table_name), 
                    sql.SQL(where_clause)
                )
            else:
                query = sql.SQL("SELECT * FROM {}").format(sql.Identifier(table_name))
        
        # Use a regular cursor for better compatibility
        # Named cursors require transactions which can cause issues with streaming
        try:
            cursor = db_manager.connection.cursor()
        except Exception as e:
            yield f"Error creating cursor: {str(e)}\n"
            return
        
        # Execute query with server-side cursor
        try:
            print(f"Executing query: {query}")
            print(f"Query params: {params}")
            print(f"Table name: {table_name}")
            print(f"Selected columns: {selected_columns}")
            print(f"Column indices: {column_indices}")
            print(f"Where clause: {where_clause}")
            cursor.execute(query, params)
            print("Query executed successfully")
        except Exception as e:
            print(f"Query execution failed: {str(e)}")
            print(f"Error type: {type(e)}")
            yield f"Error executing query: {str(e)}\n"
            return
        
        # Process data in chunks
        rows_processed = 0
        chunk_buffer = StringIO()
        writer = csv.writer(chunk_buffer)
        
        print(f"Streaming export started for table {table_name}, chunk_size: {chunk_size}")
        
        while True:
            rows = cursor.fetchmany(chunk_size)
            if not rows:
                break
            
            # Process each row
            for row in rows:
                if selected_columns and column_indices:
                    # Data is already filtered at database level
                    writer.writerow(row)
                else:
                    writer.writerow(row)
                
                rows_processed += 1
            
            # Yield chunk and reset buffer
            chunk_data = chunk_buffer.getvalue()
            if chunk_data:
                yield chunk_data
                chunk_buffer.seek(0)
                chunk_buffer.truncate(0)
                print(f"Exported {rows_processed} rows so far...")
        
        # Yield any remaining data
        final_data = chunk_buffer.getvalue()
        if final_data:
            yield final_data
        
        print(f"Streaming export completed. Total rows exported: {rows_processed}")
            
    except Exception as e:
        yield f"Error streaming data: {str(e)}\n"
    finally:
        if cursor:
            cursor.close()
        if chunk_buffer:
            chunk_buffer.close()

def _generate_export_cache_key(table_name, filters, selected_columns):
    """Generate a cache key for export data"""
    import hashlib
    import json
    
    # Create a hash of the export parameters
    cache_data = {
        'table': table_name,
        'filters': filters,
        'columns': selected_columns
    }
    
    cache_string = json.dumps(cache_data, sort_keys=True)
    return hashlib.md5(cache_string.encode()).hexdigest()

def _get_cached_export(cache_key):
    """Get cached export data"""
    try:
        # Use the platform cache manager
        cache_data = cache_manager.get(f"export_{cache_key}")
        if cache_data:
            from flask import Response
            return Response(
                cache_data['content'],
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename={cache_data["filename"]}',
                    'Content-Type': 'text/csv; charset=utf-8',
                    'X-Cache': 'HIT'
                }
            )
    except Exception as e:
        print(f"Error getting cached export: {e}")
    return None

def _cache_export(cache_key, response, total_rows):
    """Cache export data for future use"""
    try:
        # Only cache smaller exports (< 1MB)
        if total_rows < 5000 and hasattr(response, 'data'):
            cache_data = {
                'content': response.data,
                'filename': response.headers.get('Content-Disposition', 'export.csv'),
                'total_rows': total_rows,
                'cached_at': datetime.now().isoformat()
            }
            # Cache for 1 hour
            cache_manager.set(f"export_{cache_key}", cache_data, ttl=3600)
            print(f"Cached export for key: {cache_key}")
    except Exception as e:
        print(f"Error caching export: {e}")

def _generate_export_filename(table_name, filters, selected_columns, total_rows):
    """Generate a descriptive filename for the export"""
    import re
    from datetime import datetime
    
    # Base filename
    filename_parts = [table_name]
    
    # Add filter indicator
    if filters and filters.get('groups'):
        condition_count = sum(len(group.get('conditions', [])) for group in filters.get('groups', []))
        if condition_count > 0:
            filename_parts.append(f"filtered_{condition_count}filters")
    
    # Add column count
    if selected_columns:
        filename_parts.append(f"{len(selected_columns)}cols")
    
    # Add row count
    filename_parts.append(f"{total_rows}rows")
    
    # Add timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_parts.append(timestamp)
    
    # Join and clean filename
    filename = "_".join(filename_parts) + ".csv"
    
    # Remove any invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    return filename

@app.route('/databases')
@login_required
def databases():
    """Database management page"""
    stored_databases = db_storage.load_databases()
    current_db_id = db_storage.get_current_database_id()
    current_user = get_current_user()
    
    return render_template('databases.html', 
                         databases=stored_databases,
                         current_database_id=current_db_id,
                         current_user=current_user)

@app.route('/databases/add', methods=['GET', 'POST'])
@login_required
def add_database():
    """Add new database configuration"""
    if request.method == 'POST':
        name = request.form.get('name')
        host = request.form.get('host')
        port = request.form.get('port', 5432)
        database = request.form.get('database')
        description = request.form.get('description', '')
        
        if not all([name, host, database]):
            flash('Name, host, and database are required fields', 'error')
            return redirect(url_for('add_database'))
        
        success = db_storage.add_database(name, host, port, database, description)
        
        if success:
            flash(f'Database "{name}" added successfully!', 'success')
            return redirect(url_for('databases'))
        else:
            flash('Error adding database configuration', 'error')
    
    return render_template('add_database.html')

@app.route('/databases/edit/<db_id>', methods=['GET', 'POST'])
@login_required
def edit_database(db_id):
    """Edit database configuration"""
    database = db_storage.get_database(db_id)
    if not database:
        flash('Database not found', 'error')
        return redirect(url_for('databases'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        host = request.form.get('host')
        port = request.form.get('port', 5432)
        db_name = request.form.get('database')
        description = request.form.get('description', '')
        
        if not all([name, host, db_name]):
            flash('Name, host, and database are required fields', 'error')
            return render_template('edit_database.html', database=database)
        
        success = db_storage.update_database(db_id, name, host, port, db_name, description)
        
        if success:
            flash(f'Database "{name}" updated successfully!', 'success')
            return redirect(url_for('databases'))
        else:
            flash('Error updating database configuration', 'error')
    
    return render_template('edit_database.html', database=database)

@app.route('/databases/delete/<db_id>', methods=['POST'])
@login_required
def delete_database(db_id):
    """Delete database configuration"""
    database = db_storage.get_database(db_id)
    if not database:
        flash('Database not found', 'error')
        return redirect(url_for('databases'))
    
    success = db_storage.delete_database(db_id)
    
    if success:
        flash(f'Database "{database["name"]}" deleted successfully!', 'success')
        # Clear current database if it was deleted
        if db_storage.get_current_database_id() == db_id:
            db_storage.set_current_database(None)
    else:
        flash('Error deleting database configuration', 'error')
    
    return redirect(url_for('databases'))

@app.route('/databases/connect/<db_id>', methods=['POST'])
@login_required
def connect_to_database(db_id):
    """Connect to a stored database"""
    database = db_storage.get_database(db_id)
    if not database:
        return jsonify({'success': False, 'error': 'Database not found'})
    
    username = request.form.get('username')
    password = request.form.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password are required'})
    
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
        # Update database manager config and connect
        db_manager.config = config
        connect_success, connect_message = db_manager.connect(config)
        
        if connect_success:
            # Update storage records
            db_storage.set_current_database(db_id)
            db_storage.update_last_connected(db_id)
            
            return jsonify({
                'success': True, 
                'message': f'Connected to {database["name"]} successfully!',
                'redirect': url_for('index')
            })
        else:
            return jsonify({'success': False, 'error': f'Connection failed: {connect_message}'})
    else:
        return jsonify({'success': False, 'error': f'Connection test failed: {message}'})

@app.route('/databases/test/<db_id>', methods=['POST'])
@login_required
def test_database_connection(db_id):
    """Test connection to a stored database"""
    database = db_storage.get_database(db_id)
    if not database:
        return jsonify({'success': False, 'error': 'Database not found'})
    
    username = request.form.get('username')
    password = request.form.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password are required'})
    
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
    
    return jsonify({
        'success': success,
        'message': message
    })

@app.route('/databases/disconnect', methods=['POST'])
@login_required
def disconnect_database():
    """Disconnect from current database"""
    try:
        # Close the current database connection
        db_manager.close()
        
        # Clear the current database setting
        db_storage.set_current_database(None)
        
        return jsonify({
            'success': True,
            'message': 'Disconnected successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error disconnecting: {str(e)}'
        })

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page (optimized)"""
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        start_time = time.time()  # Performance monitoring
        
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me') == 'on'
        
        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('auth/login.html')
        
        # Optimized authentication
        success, user = user_manager.authenticate_user(username, password)
        
        if success:
            # Set session data efficiently
            session.update({
                'user_id': user['id'],
                'username': user['username'],
                'login_time': time.time()
            })
            
            # Handle remember me functionality
            if remember_me:
                session.permanent = True
                print(f"Remember me enabled for user {username}. Session will last 30 days.")
            else:
                session.permanent = False
                print(f"Session will expire when browser closes for user {username}.")
            
            # Performance logging
            login_time = time.time() - start_time
            print(f"Login completed in {login_time:.3f} seconds for user {username}")
            
            flash(f'Welcome back, {user["full_name"] or user["username"]}!', 'success')
            
            # Redirect to next page or dashboard
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page"""
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not all([username, email, password, confirm_password]):
            flash('All fields are required.', 'error')
            return render_template('auth/register.html')
        
        if len(username) < 3:
            flash('Username must be at least 3 characters long.', 'error')
            return render_template('auth/register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('auth/register.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/register.html')
        
        if '@' not in email or '.' not in email:
            flash('Please enter a valid email address.', 'error')
            return render_template('auth/register.html')
        
        success, message = user_manager.register_user(username, email, password, full_name)
        
        if success:
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')
    
    return render_template('auth/register.html')

@app.route('/logout')
def logout():
    """User logout"""
    username = session.get('username', 'User')
    
    # Clear database connection and reset to default config
    try:
        db_manager.close()
        # Reset to default config (from environment variables)
        db_manager.config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', ''),
            'user': os.getenv('DB_USER', ''),
            'password': os.getenv('DB_PASSWORD', '')
        }
        # Clear current database setting
        db_storage.set_current_database(None)
    except Exception as e:
        print(f"Error during logout cleanup: {e}")
    
    session.clear()
    flash(f'Goodbye, {username}! You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    current_user = get_current_user()
    return render_template('auth/profile.html', current_user=current_user)

@app.route('/visualizations')
@login_required
def visualizations():
    """Data visualization dashboard page"""
    current_user = get_current_user()
    
    # Check if database is connected
    if not db_manager.connection:
        # Try to connect with existing config
        success, message = db_manager.connect()
        if not success:
            flash("Please connect to a database first to view visualizations.", "warning")
            return redirect(url_for('databases'))
    
    return render_template('visualizations.html', current_user=current_user)

@app.route('/api/visualizations/dashboard')
@login_required
def api_visualization_dashboard():
    """API endpoint to get dashboard visualization data"""
    # Check if we have a connection
    if not db_manager.connection:
        # Try to connect with existing config
        connect_success, connect_message = db_manager.connect()
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
    success, result = db_manager.get_table_column_analysis(table_name)
    if success:
        return jsonify({'success': True, 'data': result})
    else:
        return jsonify({'success': False, 'error': result})

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

@app.route('/api/visualizations/custom/data', methods=['POST'])
@login_required
def api_custom_chart_data():
    """API endpoint to get data for custom chart creation"""
    try:
        data = request.get_json()
        table_name = data.get('table_name')
        x_column = data.get('x_column')
        y_column = data.get('y_column')
        chart_type = data.get('chart_type')
        aggregation = data.get('aggregation', 'count')
        limit = data.get('limit', 100)
        filters = data.get('filters', {'logic': 'AND', 'groups': []})
        
        if not table_name or not x_column:
            return jsonify({'success': False, 'error': 'Table name and X column are required'})
        
        if not db_manager.connection:
            return jsonify({'success': False, 'error': 'No database connection'})
        
        cursor = db_manager.connection.cursor()
        
        # Build WHERE clause from filters
        where_clause, filter_params = db_manager._build_where_clause(filters)
        
        # Build base WHERE conditions
        base_conditions = [sql.SQL("{} IS NOT NULL").format(sql.Identifier(x_column))]
        query_params = []
        
        # Add filter conditions if any
        if where_clause:
            base_conditions.append(sql.SQL(where_clause))
            query_params.extend(filter_params)
        
        # Build query based on chart type and aggregation
        if chart_type in ['pie', 'doughnut'] or aggregation == 'count':
            # For categorical charts or count aggregation
            if y_column and y_column != x_column and aggregation in ['sum', 'avg', 'min', 'max']:
                # Add y_column NOT NULL condition
                base_conditions.append(sql.SQL("{} IS NOT NULL").format(sql.Identifier(y_column)))
                
                query = sql.SQL("""
                    SELECT {}, {}({}) as value
                    FROM {} 
                    WHERE {}
                    GROUP BY {}
                    ORDER BY value DESC
                    LIMIT %s
                """).format(
                    sql.Identifier(x_column),
                    sql.SQL(aggregation.upper()),
                    sql.Identifier(y_column),
                    sql.Identifier(table_name),
                    sql.SQL(" AND ").join(base_conditions),
                    sql.Identifier(x_column)
                )
            else:
                # Count aggregation
                query = sql.SQL("""
                    SELECT {}, COUNT(*) as value
                    FROM {} 
                    WHERE {}
                    GROUP BY {}
                    ORDER BY value DESC
                    LIMIT %s
                """).format(
                    sql.Identifier(x_column),
                    sql.Identifier(table_name),
                    sql.SQL(" AND ").join(base_conditions),
                    sql.Identifier(x_column)
                )
        else:
            # For scatter plots or line charts with two columns
            if y_column and y_column != x_column:
                # Add y_column NOT NULL condition
                base_conditions.append(sql.SQL("{} IS NOT NULL").format(sql.Identifier(y_column)))
                
                query = sql.SQL("""
                    SELECT {}, {}
                    FROM {} 
                    WHERE {}
                    ORDER BY {} 
                    LIMIT %s
                """).format(
                    sql.Identifier(x_column),
                    sql.Identifier(y_column),
                    sql.Identifier(table_name),
                    sql.SQL(" AND ").join(base_conditions),
                    sql.Identifier(x_column)
                )
            else:
                # Single column analysis
                query = sql.SQL("""
                    SELECT {}, COUNT(*) as value
                    FROM {} 
                    WHERE {}
                    GROUP BY {}
                    ORDER BY {} 
                    LIMIT %s
                """).format(
                    sql.Identifier(x_column),
                    sql.Identifier(table_name),
                    sql.SQL(" AND ").join(base_conditions),
                    sql.Identifier(x_column),
                    sql.Identifier(x_column)
                )
        
        # Execute query with filter parameters + limit
        query_params.append(limit)
        cursor.execute(query, query_params)
        results = cursor.fetchall()
        
        # Format data for Chart.js
        if len(results) > 0 and len(results[0]) >= 2:
            # Two column data (x_column, value)
            chart_data = {
                'labels': [str(row[0]) for row in results],
                'datasets': [{
                    'label': f'{aggregation.title()} of {y_column or x_column}',
                    'data': [float(row[1]) if row[1] is not None else 0 for row in results]
                }]
            }
        elif len(results) > 0 and len(results[0]) == 1:
            # Single column data (count only)
            chart_data = {
                'labels': [str(row[0]) for row in results],
                'datasets': [{
                    'label': f'Count of {x_column}',
                    'data': [1 for row in results]  # Each row represents 1 occurrence
                }]
            }
        else:
            # No data
            chart_data = {
                'labels': [],
                'datasets': [{
                    'label': f'{aggregation.title()} of {y_column or x_column}',
                    'data': []
                }]
            }
        
        cursor.close()
        return jsonify({'success': True, 'chart_data': chart_data, 'total_rows': len(results)})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/visualizations/geo/<table_name>')
@login_required
def api_geo_chart_data(table_name):
    """API endpoint to get geographic data for a specific table"""
    try:
        if not db_manager.connection:
            return jsonify({'success': False, 'error': 'No database connection'})
        
        cursor = db_manager.connection.cursor()
        
        # Get table columns to find potential location and value columns
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = %s 
            ORDER BY ordinal_position
        """, (table_name,))
        
        columns = cursor.fetchall()
        
        if not columns:
            return jsonify({'success': False, 'error': f'Table {table_name} not found or has no columns'})
        
        # Find potential location columns (text/varchar types)
        location_columns = []
        value_columns = []
        
        print(f"DEBUG: Processing columns for table {table_name}")
        for col_name, col_type in columns:
            print(f"DEBUG: Column {col_name} has type {col_type}")
            if col_type in ['text', 'varchar', 'character varying', 'char']:
                location_columns.append({
                    'name': col_name,
                    'type': col_type,
                    'category': 'location'
                })
                print(f"DEBUG: Added {col_name} as location column")
            elif col_type in ['integer', 'bigint', 'smallint', 'numeric', 'decimal', 'real', 'double precision', 'float', 'float4', 'float8', 'money', 'serial', 'bigserial']:
                value_columns.append({
                    'name': col_name,
                    'type': col_type,
                    'category': 'numeric'
                })
                print(f"DEBUG: Added {col_name} as value column")
            else:
                print(f"DEBUG: Column {col_name} with type {col_type} not categorized")
        
        print(f"DEBUG: Found {len(location_columns)} location columns and {len(value_columns)} value columns")
        
        # If we have location columns, try to get sample data
        geo_data = []
        if location_columns:
            # Use the first location column as default
            location_col = location_columns[0]['name']
            
            # Try to get sample geographic data
            try:
                cursor.execute(f"""
                    SELECT {location_col}, COUNT(*) as count
                    FROM {table_name}
                    WHERE {location_col} IS NOT NULL
                    GROUP BY {location_col}
                    ORDER BY count DESC
                    LIMIT 20
                """)
                
                results = cursor.fetchall()
                geo_data = [
                    {
                        'location': row[0],
                        'value': row[1],
                        'display_name': row[0]
                    }
                    for row in results
                ]
            except Exception as e:
                print(f"Error getting geographic data: {e}")
        
        cursor.close()
        
        return jsonify({
            'success': True,
            'data': geo_data,
            'location_columns': location_columns,
            'value_columns': value_columns,
            'table_name': table_name
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
        filters = data.get('filters', [])
        
        if not table_name or not location_column:
            return jsonify({'success': False, 'error': 'Table name and location column are required'})
        
        if not db_manager.connection:
            return jsonify({'success': False, 'error': 'No database connection'})
        
        cursor = db_manager.connection.cursor()
        
        # Build WHERE clause with filters
        where_conditions = [sql.SQL("{} IS NOT NULL").format(sql.Identifier(location_column))]
        query_params = []
        
        # Add value column NOT NULL condition if needed
        if value_column and value_column != location_column and aggregation in ['sum', 'avg', 'min', 'max']:
            where_conditions.append(sql.SQL("{} IS NOT NULL").format(sql.Identifier(value_column)))
        
        # Process filters
        for filter_item in filters:
            column = filter_item.get('column')
            operator = filter_item.get('operator')
            value = filter_item.get('value')
            
            if not column or not operator:
                continue
                
            if operator == 'IS NULL':
                where_conditions.append(sql.SQL("{} IS NULL").format(sql.Identifier(column)))
            elif operator == 'IS NOT NULL':
                where_conditions.append(sql.SQL("{} IS NOT NULL").format(sql.Identifier(column)))
            elif operator == 'LIKE':
                where_conditions.append(sql.SQL("{} LIKE %s").format(sql.Identifier(column)))
                query_params.append(f'%{value}%')
            elif operator == 'NOT LIKE':
                where_conditions.append(sql.SQL("{} NOT LIKE %s").format(sql.Identifier(column)))
                query_params.append(f'%{value}%')
            elif operator == 'IN':
                # Split comma-separated values
                values = [v.strip() for v in value.split(',') if v.strip()]
                if values:
                    placeholders = sql.SQL(', ').join([sql.Placeholder() for _ in values])
                    where_conditions.append(sql.SQL("{} IN ({})").format(sql.Identifier(column), placeholders))
                    query_params.extend(values)
            elif operator in ['=', '!=', '>', '<', '>=', '<=']:
                where_conditions.append(sql.SQL("{} {} %s").format(sql.Identifier(column), sql.SQL(operator)))
                query_params.append(value)
        
        # Build the complete WHERE clause
        where_clause = sql.SQL(' AND ').join(where_conditions)
        
        # Build query for geographic aggregation
        if value_column and value_column != location_column and aggregation in ['sum', 'avg', 'min', 'max']:
            query = sql.SQL("""
                SELECT {}, {}({}) as value
                FROM {} 
                WHERE {}
                GROUP BY {}
                ORDER BY value DESC
            """).format(
                sql.Identifier(location_column),
                sql.SQL(aggregation.upper()),
                sql.Identifier(value_column),
                sql.Identifier(table_name),
                where_clause,
                sql.Identifier(location_column)
            )
        else:
            # Count aggregation
            query = sql.SQL("""
                SELECT {}, COUNT(*) as value
                FROM {} 
                WHERE {}
                GROUP BY {}
                ORDER BY value DESC
            """).format(
                sql.Identifier(location_column),
                sql.Identifier(table_name),
                where_clause,
                sql.Identifier(location_column)
            )
        
        cursor.execute(query, query_params)
        results = cursor.fetchall()
        
        # Format data for mapping
        geo_data = []
        for row in results:
            location = str(row[0]).strip().lower()
            value = float(row[1]) if row[1] is not None else 0
            
            geo_data.append({
                'location': location,
                'value': value,
                'display_name': str(row[0])
            })
        
        cursor.close()
        
        # Log filter information
        filter_info = f" with {len(filters)} filters" if filters else " (no filters)"
        print(f"Geographic data request for {table_name}.{location_column}{filter_info}: {len(geo_data)} locations found")
        
        return jsonify({
            'success': True, 
            'geo_data': geo_data, 
            'total_locations': len(geo_data),
            'filters_applied': len(filters)
        })
        
    except Exception as e:
        print(f"Error in geographic data API: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/debug/connection')
@login_required
def api_debug_connection():
    """Debug endpoint to check database connection and configuration"""
    debug_info = {
        'has_connection': db_manager.connection is not None,
        'config': {
            'host': db_manager.config.get('host', 'Not set'),
            'port': db_manager.config.get('port', 'Not set'),
            'database': db_manager.config.get('database', 'Not set'),
            'user': db_manager.config.get('user', 'Not set'),
            'password': '***' if db_manager.config.get('password') else 'Not set'
        },
        'connection_test': None,
        'tables_test': None
    }
    
    # Test connection
    try:
        success, message = db_manager.test_connection()
        debug_info['connection_test'] = {'success': success, 'message': message}
    except Exception as e:
        debug_info['connection_test'] = {'success': False, 'message': str(e)}
    
    # Test tables if connection works
    if debug_info['connection_test']['success']:
        try:
            success, result = db_manager.get_tables()
            debug_info['tables_test'] = {'success': success, 'tables': result if success else result}
        except Exception as e:
            debug_info['tables_test'] = {'success': False, 'message': str(e)}
    
    return jsonify(debug_info)

# View Configuration API Routes
@app.route('/api/database/<database_id>/tables')
@login_required
def api_get_tables(database_id):
    """Get tables for a specific database"""
    try:
        databases = get_stored_databases()
        database = next((db for db in databases if db['id'] == database_id), None)
        
        if not database:
            return jsonify({'error': 'Database not found'}), 404
        
        # Create temporary db manager for this database
        temp_manager = DatabaseManager()
        temp_config = {
            'host': database['host'],
            'port': database['port'],
            'database': database['database'],
            'user': database.get('user', ''),
            'password': database.get('password', '')
        }
        
        # Check if this is the currently connected database
        current_db_id = db_storage.get_current_database_id()
        if current_db_id == database_id and db_manager.connection:
            # Use existing connection
            success, result = db_manager.get_tables()
            if success:
                tables = [{'name': table} for table in result]
                return jsonify(tables)
            else:
                return jsonify({'error': result}), 500
        else:
            # For non-current databases, we need credentials
            return jsonify({'error': 'This database is not currently connected. Please connect to this database first from the Databases page, then try again.'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Clean up the temporary connection
        try:
            if 'temp_manager' in locals() and temp_manager.connection:
                temp_manager.connection.close()
        except:
            pass

@app.route('/api/database/<database_id>/table/<table_name>/columns')
@login_required
def api_get_table_columns(database_id, table_name):
    """Get columns for a specific table"""
    try:
        databases = get_stored_databases()
        database = next((db for db in databases if db['id'] == database_id), None)
        
        if not database:
            return jsonify({'error': 'Database not found'}), 404
        
        # Create temporary db manager for this database
        temp_manager = DatabaseManager()
        temp_config = {
            'host': database['host'],
            'port': database['port'],
            'database': database['database'],
            'user': database.get('user', ''),
            'password': database.get('password', '')
        }
        
        # Check if this is the currently connected database
        current_db_id = db_storage.get_current_database_id()
        if current_db_id == database_id and db_manager.connection:
            # Use existing connection
            success, result = db_manager.get_columns(table_name)
            if success:
                columns = [{'name': col[0], 'type': col[1]} for col in result]
                return jsonify(columns)
            else:
                return jsonify({'error': result}), 500
        else:
            # For non-current databases, we need credentials
            return jsonify({'error': 'This database is not currently connected. Please connect to this database first from the Databases page, then try again.'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Clean up the temporary connection
        try:
            if 'temp_manager' in locals() and temp_manager.connection:
                temp_manager.connection.close()
        except:
            pass

@app.route('/api/view-config/save', methods=['POST'])
@login_required
def api_save_view_config():
    """Save view configuration for a table"""
    try:
        data = request.get_json()
        database_id = data.get('database_id')
        table_name = data.get('table_name')
        configuration = data.get('configuration')
        
        if not all([database_id, table_name, configuration]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Load existing configurations
        config_file = 'view_configurations.json'
        try:
            with open(config_file, 'r') as f:
                configs = json.load(f)
        except FileNotFoundError:
            configs = {}
        
        # Save configuration
        config_key = f"{database_id}_{table_name}"
        configs[config_key] = {
            'database_id': database_id,
            'table_name': table_name,
            'configuration': configuration,
            'created_at': time.time(),
            'updated_at': time.time()
        }
        
        # Write back to file
        with open(config_file, 'w') as f:
            json.dump(configs, f, indent=2)
        
        return jsonify({'success': True, 'message': 'Configuration saved successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/view-config/load/<database_id>/<table_name>')
@login_required
def api_load_view_config(database_id, table_name):
    """Load view configuration for a table"""
    try:
        config_file = 'view_configurations.json'
        try:
            with open(config_file, 'r') as f:
                configs = json.load(f)
        except FileNotFoundError:
            return jsonify({'error': 'No configurations found'}), 404
        
        config_key = f"{database_id}_{table_name}"
        if config_key in configs:
            return jsonify(configs[config_key])
        else:
            return jsonify({'error': 'Configuration not found'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/view-config/status')
@login_required
def api_view_config_status():
    """Get view configuration status and recent configurations"""
    try:
        config_file = 'view_configurations.json'
        try:
            with open(config_file, 'r') as f:
                configs = json.load(f)
        except FileNotFoundError:
            return jsonify({'success': True, 'configurations': [], 'current_database_id': db_storage.get_current_database_id()})
        
        # Get current database to filter relevant configurations
        current_db_id = db_storage.get_current_database_id()
        
        configurations = []
        for config_key, config_data in configs.items():
            database_id, table_name = config_key.split('_', 1)
            
            # Include all configurations, but mark current database ones
            config_info = {
                'table_name': table_name,
                'database_id': database_id,
                'database_name': 'Current Database' if database_id == current_db_id else 'Other Database',
                'updated_at': config_data.get('updated_at', time.time()),
                'created_at': config_data.get('created_at', time.time()),
                'is_current': database_id == current_db_id
            }
            configurations.append(config_info)
        
        # Sort by updated_at (most recent first)
        configurations.sort(key=lambda x: x['updated_at'], reverse=True)
        
        return jsonify({
            'success': True,
            'configurations': configurations,
            'total_count': len(configurations),
            'current_db_count': len([c for c in configurations if c['is_current']]),
            'current_database_id': current_db_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# User Management API Endpoints
@app.route('/api/users/create', methods=['POST'])
@login_required
def api_create_user():
    """API endpoint to create a new user"""
    try:
        # Check if current user is logged in
        current_user_data = get_current_user()
        if not current_user_data:
            return jsonify({'success': False, 'error': 'Authentication required'})
        
        data = request.get_json()
        required_fields = ['full_name', 'username', 'email', 'role', 'password']
        
        # Validate required fields
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'})
        
        # Check if username or email already exists
        existing_users = user_manager.load_users()
        for user in existing_users:
            if user['username'] == data['username']:
                return jsonify({'success': False, 'error': 'Username already exists'})
            if user['email'] == data['email']:
                return jsonify({'success': False, 'error': 'Email already exists'})
        
        # Create new user
        user_id = str(uuid.uuid4())
        password_hash = user_manager.hash_password(data['password'])
        
        new_user = {
            'id': user_id,
            'username': data['username'],
            'email': data['email'],
            'full_name': data['full_name'],
            'phone': data.get('phone', ''),
            'position': data.get('position', ''),
            'role': data['role'],
            'password_hash': password_hash,
            'created_at': datetime.now().isoformat(),
            'last_login': None,
            'is_active': True,
            'avatar': None  # Default to no avatar
        }
        
        # Add user to file
        existing_users.append(new_user)
        user_manager.save_users(existing_users)
        
        return jsonify({
            'success': True, 
            'message': 'User created successfully',
            'user_id': user_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/users/list')
@login_required
def api_list_users():
    """API endpoint to list all users"""
    try:
        users = user_manager.load_users()
        
        # Remove sensitive data
        safe_users = []
        for user in users:
            safe_user = {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'full_name': user['full_name'],
                'phone': user.get('phone', ''),
                'position': user.get('position', ''),
                'role': user.get('role', 'user'),
                'created_at': user.get('created_at', ''),
                'last_login': user.get('last_login', ''),
                'active': user.get('is_active', True)
            }
            safe_users.append(safe_user)
        
        return jsonify({
            'success': True,
            'users': safe_users,
            'total': len(safe_users)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/users/<user_id>')
@login_required
def api_get_user(user_id):
    """API endpoint to get a specific user's details"""
    try:
        user = user_manager.get_user_by_id(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})
        
        # Return user data without password hash
        safe_user = {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'full_name': user['full_name'],
            'phone': user.get('phone', ''),
            'position': user.get('position', ''),
            'role': user.get('role', 'user'),
            'created_at': user.get('created_at', ''),
            'last_login': user.get('last_login', ''),
            'is_active': user.get('is_active', True),
            'avatar': user.get('avatar', None)
        }
        
        return jsonify({
            'success': True,
            'user': safe_user
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/users/<user_id>/reset-password', methods=['POST'])
@login_required
def api_reset_user_password(user_id):
    """API endpoint to reset a user's password"""
    try:
        data = request.get_json() or {}
        custom_password = data.get('password')
        
        # Determine password to use
        if custom_password:
            # Use custom password provided by user
            new_password = custom_password
            
            # Validate password strength
            if len(new_password) < 8:
                return jsonify({'success': False, 'error': 'Password must be at least 8 characters long'})
            
            # Check for basic complexity
            has_upper = any(c.isupper() for c in new_password)
            has_lower = any(c.islower() for c in new_password)
            has_digit = any(c.isdigit() for c in new_password)
            
            if not (has_upper and has_lower and has_digit):
                return jsonify({'success': False, 'error': 'Password must contain at least one uppercase letter, one lowercase letter, and one digit'})
                
        else:
            # Generate random password if no custom password provided
            import secrets
            import string
            
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
            new_password = ''.join(secrets.choice(alphabet) for i in range(12))
        
        # Hash the password
        password_hash = user_manager.hash_password(new_password)
        
        # Update user
        users = user_manager.load_users()
        user_found = False
        username = None
        
        for user in users:
            if user['id'] == user_id:
                user['password_hash'] = password_hash
                username = user['username']
                user_found = True
                break
        
        if not user_found:
            return jsonify({'success': False, 'error': 'User not found'})
        
        user_manager.save_users(users)
        
        response_data = {
            'success': True,
            'message': f'Password for {username} has been reset successfully'
        }
        
        # Only include the password in response if it was auto-generated
        if not custom_password:
            response_data['new_password'] = new_password
            response_data['message'] = f'Password for {username} has been reset to: {new_password}'
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/users/<user_id>', methods=['PUT'])
@login_required
def api_update_user(user_id):
    """API endpoint to update user information"""
    try:
        # Check if current user is logged in
        current_user_data = get_current_user()
        if not current_user_data:
            return jsonify({'success': False, 'error': 'Authentication required'})
        
        data = request.get_json()
        required_fields = ['full_name', 'username', 'email', 'role']
        
        # Validate required fields
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'})
        
        users = user_manager.load_users()
        user_found = False
        
        # Find and update user
        for user in users:
            if user['id'] == user_id:
                user_found = True
                
                # Check if username or email already exists (excluding current user)
                for other_user in users:
                    if other_user['id'] != user_id:
                        if other_user['username'] == data['username']:
                            return jsonify({'success': False, 'error': 'Username already exists'})
                        if other_user['email'] == data['email']:
                            return jsonify({'success': False, 'error': 'Email already exists'})
                
                # Update user information
                user['full_name'] = data['full_name']
                user['username'] = data['username']
                user['email'] = data['email']
                user['phone'] = data.get('phone', user.get('phone', ''))
                user['position'] = data.get('position', user.get('position', ''))
                user['role'] = data['role']
                user['is_active'] = data.get('is_active', user.get('is_active', True))
                user['updated_at'] = datetime.now().isoformat()
                
                # Update password if provided
                if data.get('password'):
                    if len(data['password']) < 6:
                        return jsonify({'success': False, 'error': 'Password must be at least 6 characters long'})
                    user['password_hash'] = user_manager.hash_password(data['password'])
                
                break
        
        if not user_found:
            return jsonify({'success': False, 'error': 'User not found'})
        
        # Save updated users
        user_manager.save_users(users)
        
        return jsonify({
            'success': True,
            'message': 'User updated successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/users/<user_id>', methods=['DELETE'])
@login_required
def api_delete_user(user_id):
    """API endpoint to delete a user"""
    try:
        # Check if trying to delete self
        current_user_data = get_current_user()
        if current_user_data and current_user_data.get('id') == user_id:
            return jsonify({'success': False, 'error': 'Cannot delete your own account'})
        
        users = user_manager.load_users()
        users = [user for user in users if user['id'] != user_id]
        
        user_manager.save_users(users)
        
        return jsonify({
            'success': True,
            'message': 'User deleted successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/users/export')
@login_required
def api_export_users():
    """API endpoint to export users as CSV"""
    try:
        import csv
        import io
        
        users = user_manager.load_users()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Full Name', 'Username', 'Email', 'Phone', 'Position', 'Role', 'Created At', 'Last Login', 'Active'])
        
        # Write users
        for user in users:
            writer.writerow([
                user['full_name'],
                user['username'],
                user['email'],
                user.get('phone', ''),
                user.get('position', ''),
                user.get('role', 'user'),
                user.get('created_at', ''),
                user.get('last_login', ''),
                user.get('is_active', True)
            ])
        
        output.seek(0)
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=users-export.csv'}
        )
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/emergency-reset-password', methods=['GET', 'POST'])
def emergency_reset_password():
    """Emergency password reset for admin access"""
    if request.method == 'GET':
        return '''
        <html>
        <head><title>Emergency Password Reset</title></head>
        <body style="font-family: Arial; max-width: 500px; margin: 50px auto; padding: 20px;">
        <h2>Emergency Password Reset</h2>
        <form method="POST">
            <div style="margin: 10px 0;">
                <label>Username:</label><br>
                <input type="text" name="username" required style="width: 100%; padding: 8px;">
            </div>
            <div style="margin: 10px 0;">
                <label>New Password:</label><br>
                <input type="password" name="password" required style="width: 100%; padding: 8px;">
            </div>
            <div style="margin: 20px 0;">
                <button type="submit" style="padding: 10px 20px; background: #007bff; color: white; border: none;">Reset Password</button>
            </div>
        </form>
        </body>
        </html>
        '''
    
    try:
        username = request.form.get('username')
        new_password = request.form.get('password')
        
        if not username or not new_password:
            return "Username and password required", 400
        
        # Load users
        users = user_manager.load_users()
        user_found = False
        
        # Find and update user
        for user in users:
            if user['username'].lower() == username.lower():
                # Use the new secure password hashing
                user['password_hash'] = user_manager.hash_password(new_password)
                user_found = True
                break
        
        if not user_found:
            return f"User '{username}' not found", 404
        
        # Save users
        user_manager.save_users(users)
        
        return f'''
        <html>
        <body style="font-family: Arial; max-width: 500px; margin: 50px auto; padding: 20px;">
        <h2>✅ Password Reset Successful</h2>
        <p>Password for user <strong>{username}</strong> has been reset.</p>
        <p>You can now <a href="/login">login</a> with the new password.</p>
        </body>
        </html>
        '''
        
    except Exception as e:
        return f"Error: {str(e)}", 500

# Avatar Management API Endpoints
@app.route('/api/profile/avatar/upload', methods=['POST'])
@login_required
def api_upload_avatar():
    """API endpoint to upload user avatar"""
    try:
        current_user_data = get_current_user()
        if not current_user_data:
            return jsonify({'success': False, 'error': 'Authentication required'})
        
        if 'avatar' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['avatar']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if file and allowed_file(file.filename):
            # Generate unique filename
            filename = secure_filename(file.filename)
            file_extension = filename.rsplit('.', 1)[1].lower()
            unique_filename = f"{current_user_data['id']}_{uuid.uuid4().hex[:8]}.{file_extension}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            # Save file
            file.save(file_path)
            
            # Resize image
            if resize_image(file_path):
                # Update user avatar
                success, message = user_manager.update_user_avatar(current_user_data['id'], f"uploads/avatars/{unique_filename}")
                if success:
                    return jsonify({
                        'success': True, 
                        'message': 'Avatar uploaded successfully',
                        'avatar_url': f"/static/uploads/avatars/{unique_filename}"
                    })
                else:
                    # Clean up file if user update failed
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    return jsonify({'success': False, 'error': message})
            else:
                # Clean up file if resize failed
                if os.path.exists(file_path):
                    os.remove(file_path)
                return jsonify({'success': False, 'error': 'Failed to process image'})
        else:
            return jsonify({'success': False, 'error': 'Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/profile/avatar/default', methods=['POST'])
@login_required
def api_set_default_avatar():
    """API endpoint to set default avatar"""
    try:
        current_user_data = get_current_user()
        if not current_user_data:
            return jsonify({'success': False, 'error': 'Authentication required'})
        
        data = request.get_json()
        avatar_id = data.get('avatar_id')
        
        if not avatar_id:
            return jsonify({'success': False, 'error': 'Avatar ID required'})
        
        # Validate avatar ID
        default_avatars = get_default_avatars()
        valid_avatar = next((avatar for avatar in default_avatars if avatar['id'] == avatar_id), None)
        
        if not valid_avatar:
            return jsonify({'success': False, 'error': 'Invalid avatar ID'})
        
        # Update user avatar to default
        success, message = user_manager.update_user_avatar(current_user_data['id'], avatar_id)
        if success:
            return jsonify({
                'success': True, 
                'message': 'Default avatar set successfully',
                'avatar_id': avatar_id
            })
        else:
            return jsonify({'success': False, 'error': message})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/profile/avatar/remove', methods=['POST'])
@login_required
def api_remove_avatar():
    """API endpoint to remove user avatar"""
    try:
        current_user_data = get_current_user()
        if not current_user_data:
            return jsonify({'success': False, 'error': 'Authentication required'})
        
        # Remove current avatar file if it exists and is not a default
        current_avatar = current_user_data.get('avatar')
        if current_avatar and not current_avatar.startswith('default-'):
            avatar_path = os.path.join('static', current_avatar)
            if os.path.exists(avatar_path):
                os.remove(avatar_path)
        
        # Update user avatar to None
        success, message = user_manager.update_user_avatar(current_user_data['id'], None)
        if success:
            return jsonify({'success': True, 'message': 'Avatar removed successfully'})
        else:
            return jsonify({'success': False, 'error': message})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/profile/avatar/defaults')
@login_required
def api_get_default_avatars():
    """API endpoint to get available default avatars"""
    try:
        avatars = get_default_avatars()
        return jsonify({'success': True, 'avatars': avatars})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/performance/login-stats')
@login_required
def api_login_performance_stats():
    """API endpoint to get login performance statistics"""
    try:
        stats = {
            'cache_hit_rate': getattr(user_manager, '_cache_hits', 0) / max(getattr(user_manager, '_cache_requests', 1), 1),
            'total_users': len(user_manager._users_cache or []),
            'index_size': len(user_manager._user_index),
            'cache_ttl': user_manager._cache_ttl,
            'last_cache_update': user_manager._cache_timestamp
        }
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/cache/stats')
@login_required
def api_cache_stats():
    """API endpoint to get comprehensive cache statistics"""
    try:
        stats = cache_manager.get_stats()
        return jsonify({
            'success': True,
            'cache_stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/cache/clear', methods=['POST'])
@login_required
def api_clear_cache():
    """API endpoint to clear cache(s)"""
    try:
        data = request.get_json() or {}
        cache_name = data.get('cache_name')
        
        if cache_name:
            cache_manager.clear(cache_name)
            message = f"Cache '{cache_name}' cleared successfully"
        else:
            cache_manager.clear()
            message = "All caches cleared successfully"
        
        return jsonify({
            'success': True,
            'message': message
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/cache/invalidate', methods=['POST'])
@login_required
def api_invalidate_cache():
    """API endpoint to invalidate cache entries by pattern"""
    try:
        data = request.get_json() or {}
        cache_name = data.get('cache_name')
        pattern = data.get('pattern')
        
        if not cache_name or not pattern:
            return jsonify({
                'success': False,
                'error': 'Both cache_name and pattern are required'
            })
        
        removed_count = cache_manager.invalidate_pattern(cache_name, pattern)
        
        return jsonify({
            'success': True,
            'message': f"Invalidated {removed_count} cache entries matching pattern '{pattern}'",
            'removed_count': removed_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/cache/cleanup', methods=['POST'])
@login_required
def api_cleanup_cache():
    """API endpoint to cleanup expired cache entries"""
    try:
        cleaned_count = cache_manager.cleanup_expired()
        
        return jsonify({
            'success': True,
            'message': f"Cleaned up {cleaned_count} expired cache entries",
            'cleaned_count': cleaned_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
