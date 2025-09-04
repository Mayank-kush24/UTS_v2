from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session
import psycopg2
from psycopg2 import sql
from psycopg2 import OperationalError, InterfaceError, InternalError
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import uuid
import hashlib
import secrets
from functools import wraps

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

# Session configuration
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_TYPE'] = 'filesystem'

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
        """Get list of all tables in the database"""
        if not self.connection:
            return False, "No database connection"
        
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
        if not filters or not isinstance(filters, dict):
            return "", []
        
        conditions = []
        params = []
        
        # Process filter groups
        for group in filters.get('groups', []):
            group_conditions = []
            
            for condition in group.get('conditions', []):
                field = condition.get('field')
                operation = condition.get('operation')
                value = condition.get('value')
                
                if not field or not operation:
                    continue
                
                # Build condition based on operation
                sql_condition, condition_params = self._build_condition(field, operation, value)
                if sql_condition:
                    group_conditions.append(sql_condition)
                    params.extend(condition_params)
            
            if group_conditions:
                group_logic = group.get('logic', 'AND')
                group_clause = f" {group_logic} ".join(group_conditions)
                if len(group_conditions) > 1:
                    group_clause = f"({group_clause})"
                conditions.append(group_clause)
        
        if conditions:
            main_logic = filters.get('logic', 'AND')
            return f" {main_logic} ".join(conditions), params
        
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
        """Get database statistics"""
        if not self.connection:
            return False, "No database connection"
        
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
            
            # Get database size
            cursor.execute("""
                SELECT pg_size_pretty(pg_database_size(current_database()));
            """)
            db_size = cursor.fetchone()[0]
            
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
                'database_size': db_size,
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
                    return True, {
                        'total_tables': total_tables,
                        'database_size': db_size,
                        'table_stats': table_stats
                    }
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
        """Hash password with salt"""
        salt = secrets.token_hex(32)
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
        return salt + password_hash.hex()
    
    def verify_password(self, password, hashed):
        """Verify password against hash"""
        try:
            salt = hashed[:64]
            stored_hash = hashed[64:]
            password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
            return password_hash.hex() == stored_hash
        except:
            return False
    
    def load_users(self):
        """Load all users from storage"""
        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)
                return data.get('users', [])
        except Exception as e:
            print(f"Error loading users: {e}")
            return []
    
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
            'is_active': True
        }
        
        users.append(new_user)
        
        if self.save_users(users):
            return True, "User registered successfully"
        else:
            return False, "Error saving user"
    
    def authenticate_user(self, username, password):
        """Authenticate user with username/email and password"""
        users = self.load_users()
        
        for user in users:
            if (user['username'].lower() == username.lower() or user['email'].lower() == username.lower()) and user['is_active']:
                if self.verify_password(password, user['password_hash']):
                    # Update last login
                    user['last_login'] = datetime.now().isoformat()
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
        """Load all stored database configurations"""
        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)
                return data.get('databases', [])
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

@app.route('/')
@login_required
def index():
    """Main page showing database status and available tables"""
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
                         current_user=current_user)

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
            flash("Configuration saved and connection established!", "success")
            return redirect(url_for('index'))
        else:
            flash(f"Configuration saved but connection failed: {connect_message}", "warning")
    else:
        flash(f"Configuration not saved - Connection test failed: {message}", "error")
    
    return redirect(url_for('config'))

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
        
        return render_template('table.html', 
                             table_name=table_name, 
                             columns=result['columns'], 
                             rows=result['rows'],
                             limit=limit,
                             page=page,
                             total_rows=result['total_rows'],
                             total_pages=total_pages,
                             filtered=result.get('filtered', False))
    else:
        flash(f"Error loading table data: {result}", "error")
        return redirect(url_for('index'))

@app.route('/api/tables')
@login_required
def api_tables():
    """API endpoint to get list of tables"""
    success, result = db_manager.get_tables()
    if success:
        return jsonify({'success': True, 'tables': result})
    else:
        return jsonify({'success': False, 'error': result})

@app.route('/api/stats')
@login_required
def api_stats():
    """API endpoint to get database statistics"""
    success, result = db_manager.get_database_stats()
    if success:
        return jsonify({'success': True, 'stats': result})
    else:
        return jsonify({'success': False, 'error': result})

@app.route('/api/connection/status')
@login_required
def api_connection_status():
    """API endpoint to check connection status"""
    success, message = db_manager.test_connection()
    return jsonify({
        'success': success, 
        'message': message,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/table/<table_name>/info')
@login_required
def api_table_info(table_name):
    """API endpoint to get table information"""
    success, result = db_manager.get_table_info(table_name)
    if success:
        return jsonify({'success': True, 'info': result})
    else:
        return jsonify({'success': False, 'error': result})

@app.route('/api/tables/bulk-stats')
@login_required
def api_bulk_table_stats():
    """API endpoint to get bulk table statistics"""
    table_names = request.args.getlist('tables')
    limit = request.args.get('limit', 20, type=int)
    
    success, result = db_manager.get_bulk_table_stats(table_names if table_names else None, limit)
    if success:
        return jsonify({'success': True, 'stats': result})
    else:
        return jsonify({'success': False, 'error': result})

@app.route('/api/tables/lazy-stats')
@login_required
def api_lazy_table_stats():
    """API endpoint for lazy loading specific table stats"""
    table_names = request.args.getlist('tables')
    fast_mode = request.args.get('fast', 'false').lower() == 'true'
    
    if not table_names:
        return jsonify({'success': False, 'error': 'No table names provided'})
    
    if fast_mode:
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
    """Export filtered table data"""
    try:
        # Get filter parameters
        filters = request.args.get('filters')
        if filters:
            try:
                import json
                filters = json.loads(filters)
            except:
                filters = None
        
        # Get all data (no pagination for export)
        success, result = db_manager.get_table_data(table_name, limit=999999, page=1, filters=filters)
        
        if not success:
            return jsonify({
                'success': False,
                'error': f'Error exporting data: {result}'
            })
        
        # Create CSV response
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow(result['columns'])
        
        # Write data rows
        for row in result['rows']:
            writer.writerow(row)
        
        output.seek(0)
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename={table_name}_export.csv'
            }
        )
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error exporting data: {str(e)}'
        })

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
    """User login page"""
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me') == 'on'
        
        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('auth/login.html')
        
        success, user = user_manager.authenticate_user(username, password)
        
        if success:
            session['user_id'] = user['id']
            session['username'] = user['username']
            
            if remember_me:
                session.permanent = True
            
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
    session.clear()
    flash(f'Goodbye, {username}! You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    current_user = get_current_user()
    return render_template('auth/profile.html', current_user=current_user)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
