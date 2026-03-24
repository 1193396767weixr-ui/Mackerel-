from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'english-tracker-secret-key-2026')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=30)
jwt = JWTManager(app)

def get_db_url():
    db_url = os.environ.get('POSTGRES_URL') or os.environ.get('DATABASE_URL')
    if not db_url:
        raise Exception('数据库连接字符串未配置，请设置 POSTGRES_URL 或 DATABASE_URL 环境变量')
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    return db_url

def get_db():
    db_url = get_db_url()
    conn = psycopg2.connect(db_url, sslmode='require')
    conn.autocommit = False
    return conn

def init_db():
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f'数据库初始化失败: {e}')
        return str(e)

@app.route('/api/register', methods=['POST'])
def register():
    try:
        init_db()
    except Exception as e:
        return jsonify({'error': f'数据库初始化失败: {str(e)}'}), 500
    
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据无效'}), 400
    
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    
    if len(username) < 3:
        return jsonify({'error': '用户名至少3个字符'}), 400
    
    if len(password) < 6:
        return jsonify({'error': '密码至少6个字符'}), 400
    
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
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({'error': '用户名已存在'}), 400
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': f'注册失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    try:
        init_db()
    except Exception as e:
        return jsonify({'error': f'数据库初始化失败: {str(e)}'}), 500
    
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据无效'}), 400
    
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()
        
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': '用户名或密码错误'}), 401
        
        access_token = create_access_token(identity=str(user['id']))
        return jsonify({
            'message': '登录成功',
            'access_token': access_token,
            'user': {'id': user['id'], 'username': user['username']}
        })
    except Exception as e:
        return jsonify({'error': f'登录失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/records', methods=['GET'])
@jwt_required()
def get_records():
    try:
        init_db()
    except Exception as e:
        return jsonify({'error': f'数据库初始化失败: {str(e)}'}), 500
    
    user_id = int(get_jwt_identity())
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('''
            SELECT id, date, type, content, pos, created_at 
            FROM records 
            WHERE user_id = %s 
            ORDER BY date DESC, created_at DESC
        ''', (user_id,))
        rows = cursor.fetchall()
        
        records = {}
        for row in rows:
            date = row['date']
            if date not in records:
                records[date] = {'words': [], 'phrases': [], 'sentences': []}
            
            item = {
                'id': row['id'],
                'text': row['content'],
                'pos': row['pos']
            }
            records[date][row['type']].append(item)
        
        return jsonify(records)
    except Exception as e:
        return jsonify({'error': f'获取记录失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/records', methods=['POST'])
@jwt_required()
def add_record():
    try:
        init_db()
    except Exception as e:
        return jsonify({'error': f'数据库初始化失败: {str(e)}'}), 500
    
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    content = data.get('content', '').strip()
    record_type = data.get('type', 'words')
    pos = data.get('pos', None)
    
    if not content:
        return jsonify({'error': '内容不能为空'}), 400
    
    if record_type not in ['words', 'phrases', 'sentences']:
        return jsonify({'error': '无效的类型'}), 400
    
    today = datetime.now().strftime('%Y/%m/%d')
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO records (user_id, date, type, content, pos) 
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        ''', (user_id, today, record_type, content, pos))
        record_id = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({
            'message': '添加成功',
            'record': {
                'id': record_id,
                'date': today,
                'type': record_type,
                'text': content,
                'pos': pos
            }
        }), 201
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': f'添加记录失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/records/<int:record_id>', methods=['DELETE'])
@jwt_required()
def delete_record(record_id):
    try:
        init_db()
    except Exception as e:
        return jsonify({'error': f'数据库初始化失败: {str(e)}'}), 500
    
    user_id = int(get_jwt_identity())
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM records WHERE id = %s AND user_id = %s', (record_id, user_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': '记录不存在或无权删除'}), 404
        
        return jsonify({'message': '删除成功'})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': f'删除记录失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/records/export', methods=['GET'])
@jwt_required()
def export_records():
    try:
        init_db()
    except Exception as e:
        return jsonify({'error': f'数据库初始化失败: {str(e)}'}), 500
    
    user_id = int(get_jwt_identity())
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('''
            SELECT id, date, type, content, pos, created_at 
            FROM records 
            WHERE user_id = %s 
            ORDER BY date DESC, created_at DESC
        ''', (user_id,))
        rows = cursor.fetchall()
        
        records = {}
        for row in rows:
            date = row['date']
            if date not in records:
                records[date] = {'words': [], 'phrases': [], 'sentences': []}
            
            item = {
                'id': row['id'],
                'text': row['content'],
                'pos': row['pos']
            }
            records[date][row['type']].append(item)
        
        return jsonify(records)
    except Exception as e:
        return jsonify({'error': f'导出记录失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/records/import', methods=['POST'])
@jwt_required()
def import_records():
    try:
        init_db()
    except Exception as e:
        return jsonify({'error': f'数据库初始化失败: {str(e)}'}), 500
    
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    imported_records = data.get('records', {})
    count = 0
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        for date, items in imported_records.items():
            for record_type in ['words', 'phrases', 'sentences']:
                for item in items.get(record_type, []):
                    text = item.get('text', item) if isinstance(item, dict) else item
                    pos = item.get('pos', None) if isinstance(item, dict) else None
                    
                    cursor.execute('''
                        SELECT id FROM records 
                        WHERE user_id = %s AND date = %s AND type = %s AND content = %s
                    ''', (user_id, date, record_type, text))
                    
                    if not cursor.fetchone():
                        cursor.execute('''
                            INSERT INTO records (user_id, date, type, content, pos) 
                            VALUES (%s, %s, %s, %s, %s)
                        ''', (user_id, date, record_type, text, pos))
                        count += 1
        
        conn.commit()
        return jsonify({'message': f'成功导入 {count} 条记录'})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': f'导入记录失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/user/info', methods=['GET'])
@jwt_required()
def get_user_info():
    try:
        init_db()
    except Exception as e:
        return jsonify({'error': f'数据库初始化失败: {str(e)}'}), 500
    
    user_id = int(get_jwt_identity())
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT id, username, created_at FROM users WHERE id = %s', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': '用户不存在'}), 404
        
        cursor.execute('''
            SELECT 
                SUM(CASE WHEN type = 'words' THEN 1 ELSE 0 END) as words,
                SUM(CASE WHEN type = 'phrases' THEN 1 ELSE 0 END) as phrases,
                SUM(CASE WHEN type = 'sentences' THEN 1 ELSE 0 END) as sentences
            FROM records WHERE user_id = %s
        ''', (user_id,))
        stats = cursor.fetchone()
        
        return jsonify({
            'user': {
                'id': user['id'],
                'username': user['username'],
                'created_at': user['created_at'].isoformat() if user['created_at'] else None
            },
            'stats': {
                'words': stats['words'] or 0,
                'phrases': stats['phrases'] or 0,
                'sentences': stats['sentences'] or 0
            }
        })
    except Exception as e:
        return jsonify({'error': f'获取用户信息失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/init-db', methods=['POST'])
def init_db_route():
    try:
        result = init_db()
        if result == True:
            return jsonify({'message': '数据库初始化成功', 'success': True})
        else:
            return jsonify({'error': result, 'success': False}), 500
    except Exception as e:
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/health', methods=['GET'])
def health():
    try:
        db_url = get_db_url()
        conn = get_db()
        conn.close()
        return jsonify({
            'status': 'ok',
            'message': '服务正常运行',
            'database': 'connected'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': '数据库连接失败',
            'error': str(e)
        }), 500

handler = app
