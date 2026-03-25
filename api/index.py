from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta
import json

app = Flask(__name__)
CORS(app)

app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'english-tracker-secret-key-2026')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=30)
jwt = JWTManager(app)

try:
    import pg8000
    USE_PG8000 = True
except ImportError:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        USE_PG8000 = False
    except ImportError:
        USE_PG8000 = None

def get_db_url():
    db_url = os.environ.get('POSTGRES_URL') or os.environ.get('DATABASE_URL')
    if not db_url:
        return None
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    return db_url

def parse_db_url(db_url):
    from urllib.parse import urlparse
    parsed = urlparse(db_url)
    return {
        'host': parsed.hostname,
        'port': parsed.port or 5432,
        'database': parsed.path[1:],
        'user': parsed.username,
        'password': parsed.password
    }

def get_db():
    if USE_PG8000 is None:
        raise Exception('数据库驱动未安装')
    
    db_url = get_db_url()
    if not db_url:
        raise Exception('数据库未配置')
    
    if USE_PG8000:
        params = parse_db_url(db_url)
        conn = pg8000.connect(
            host=params['host'],
            port=params['port'],
            database=params['database'],
            user=params['user'],
            password=params['password'],
            ssl_context=True
        )
    else:
        conn = psycopg2.connect(db_url)
    
    conn.autocommit = False
    return conn

def init_db():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS records (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                pos TEXT,
                meaning TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE')
        except:
            pass
        
        cursor.execute('SELECT id FROM users WHERE username = %s', ('admin',))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (username, password_hash, is_admin) 
                VALUES (%s, %s, %s)
            ''', ('admin', generate_password_hash('admin123'), True))
        
        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

@app.route('/api/test', methods=['GET'])
def test():
    return jsonify({'status': 'ok', 'message': 'API工作正常', 'driver': 'pg8000' if USE_PG8000 else 'psycopg2' if USE_PG8000 is False else 'none'})

@app.route('/api/health', methods=['GET'])
def health_check():
    db_url = get_db_url()
    if not db_url:
        return jsonify({'status': 'error', 'message': '数据库未配置'}), 500
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        conn.close()
        return jsonify({'status': 'ok', 'message': '数据库连接正常'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    if len(username) < 3:
        return jsonify({'error': '用户名至少3个字符'}), 400
    if len(password) < 6:
        return jsonify({'error': '密码至少6个字符'}), 400
    
    try:
        init_db()
    except Exception as e:
        return jsonify({'error': f'数据库初始化失败: {str(e)}'}), 500
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        password_hash = generate_password_hash(password)
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id', 
                      (username, password_hash))
        user_id = cursor.fetchone()[0]
        conn.commit()
        
        access_token = create_access_token(identity=str(user_id))
        return jsonify({
            'message': '注册成功',
            'access_token': access_token,
            'user': {'id': user_id, 'username': username}
        }), 201
    except Exception as e:
        if conn:
            conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            return jsonify({'error': '用户名已存在'}), 400
        return jsonify({'error': f'注册失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    
    try:
        init_db()
    except Exception as e:
        return jsonify({'error': f'数据库初始化失败: {str(e)}'}), 500
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, password_hash, is_admin FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()
        
        if not user or not check_password_hash(user[2], password):
            return jsonify({'error': '用户名或密码错误'}), 401
        
        access_token = create_access_token(identity=str(user[0]))
        return jsonify({
            'message': '登录成功',
            'access_token': access_token,
            'user': {'id': user[0], 'username': user[1], 'is_admin': user[3] or False}
        })
    except Exception as e:
        return jsonify({'error': f'登录失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

def admin_required():
    user_id = int(get_jwt_identity())
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT is_admin FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()
    conn.close()
    if not user or not user[0]:
        return False
    return True

@app.route('/api/admin/users', methods=['GET'])
@jwt_required()
def get_users():
    if not admin_required():
        return jsonify({'error': '需要管理员权限'}), 403
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.id, u.username, u.is_admin, u.created_at
            FROM users u ORDER BY u.created_at DESC
        ''')
        rows = cursor.fetchall()
        
        users = []
        for row in rows:
            cursor.execute('SELECT COUNT(*) FROM records WHERE user_id = %s', (row[0],))
            record_count = cursor.fetchone()[0]
            users.append({
                'id': row[0],
                'username': row[1],
                'is_admin': row[2] or False,
                'created_at': row[3].isoformat() if row[3] else None,
                'record_count': record_count
            })
        return jsonify(users)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/admin/users/<int:user_id>/password', methods=['PUT'])
@jwt_required()
def update_user_password(user_id):
    if not admin_required():
        return jsonify({'error': '需要管理员权限'}), 403
    
    data = request.get_json() or {}
    new_password = data.get('password', '')
    
    if len(new_password) < 6:
        return jsonify({'error': '密码至少6个字符'}), 400
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        password_hash = generate_password_hash(new_password)
        cursor.execute('UPDATE users SET password_hash = %s WHERE id = %s', (password_hash, user_id))
        conn.commit()
        return jsonify({'message': '密码修改成功'})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    if not admin_required():
        return jsonify({'error': '需要管理员权限'}), 403
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM records WHERE user_id = %s', (user_id,))
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        conn.commit()
        return jsonify({'message': '用户删除成功'})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/admin/stats', methods=['GET'])
@jwt_required()
def get_admin_stats():
    if not admin_required():
        return jsonify({'error': '需要管理员权限'}), 403
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        user_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM records')
        record_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM records WHERE type = %s', ('words',))
        word_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM records WHERE type = %s', ('phrases',))
        phrase_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM records WHERE type = %s', ('sentences',))
        sentence_count = cursor.fetchone()[0]
        
        return jsonify({
            'users': user_count,
            'records': record_count,
            'words': word_count,
            'phrases': phrase_count,
            'sentences': sentence_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/records', methods=['GET'])
@jwt_required()
def get_records():
    user_id = int(get_jwt_identity())
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, type, content, pos, meaning, created_at 
            FROM records WHERE user_id = %s ORDER BY created_at DESC
        ''', (user_id,))
        rows = cursor.fetchall()
        
        records = []
        for row in rows:
            records.append({
                'id': row[0],
                'type': row[1],
                'content': row[2],
                'pos': row[3],
                'meaning': row[4],
                'createdAt': row[5].isoformat() if row[5] else None
            })
        return jsonify(records)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/records', methods=['POST'])
@jwt_required()
def add_record():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    
    content = data.get('content', '').strip()
    record_type = data.get('type', 'words')
    pos = data.get('pos')
    meaning = data.get('meaning')
    
    if not content:
        return jsonify({'error': '内容不能为空'}), 400
    
    today = datetime.now().strftime('%Y/%m/%d')
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO records (user_id, date, type, content, pos, meaning) 
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        ''', (user_id, today, record_type, content, pos, meaning))
        record_id = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({
            'message': '添加成功',
            'record': {'id': record_id, 'type': record_type, 'content': content, 'pos': pos, 'meaning': meaning}
        }), 201
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/records/<int:record_id>', methods=['PUT'])
@jwt_required()
def update_record(record_id):
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM records WHERE id = %s AND user_id = %s', (record_id, user_id))
        if not cursor.fetchone():
            return jsonify({'error': '记录不存在'}), 404
        
        if 'meaning' in data:
            cursor.execute('UPDATE records SET meaning = %s WHERE id = %s', (data['meaning'], record_id))
            conn.commit()
        
        return jsonify({'message': '更新成功'})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/records/<int:record_id>', methods=['DELETE'])
@jwt_required()
def delete_record(record_id):
    user_id = int(get_jwt_identity())
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM records WHERE id = %s AND user_id = %s', (record_id, user_id))
        conn.commit()
        return jsonify({'message': '删除成功'})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()
