from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
import urllib.request
import urllib.parse
import json

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
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f'数据库连接错误: {e}')
        raise

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
                meaning TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        try:
            cursor.execute('ALTER TABLE records ADD COLUMN IF NOT EXISTS meaning TEXT')
        except:
            pass
        
        try:
            cursor.execute('''
                UPDATE records SET meaning = COALESCE(definition_en, '') || ' ' || COALESCE(definition_zh, '')
                WHERE meaning IS NULL AND (definition_en IS NOT NULL OR definition_zh IS NOT NULL)
            ''')
        except:
            pass
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f'数据库初始化失败: {e}')
        return str(e)

@app.route('/api/health', methods=['GET'])
def health_check():
    db_url = os.environ.get('POSTGRES_URL') or os.environ.get('DATABASE_URL')
    if not db_url:
        return jsonify({
            'status': 'error',
            'message': '数据库未配置',
            'hint': '请在Vercel环境变量中设置 POSTGRES_URL 或 DATABASE_URL'
        }), 500
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        conn.close()
        return jsonify({'status': 'ok', 'message': '数据库连接正常'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'数据库连接失败: {str(e)}', 'url_prefix': db_url[:30] + '...' if db_url else None}), 500

@app.route('/api/test', methods=['GET'])
def test():
    return jsonify({'status': 'ok', 'message': 'API工作正常'})

@app.route('/api/register', methods=['POST'])
def register():
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
    except psycopg2.errors.UniqueViolation:
        if conn:
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
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据无效'}), 400
    
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
            SELECT id, type, content, pos, meaning, created_at 
            FROM records 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        ''', (user_id,))
        rows = cursor.fetchall()
        
        records = []
        for row in rows:
            records.append({
                'id': row['id'],
                'type': row['type'],
                'content': row['content'],
                'pos': row['pos'],
                'meaning': row['meaning'],
                'createdAt': row['created_at'].isoformat() if row['created_at'] else None
            })
        
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
    meaning = data.get('meaning', None)
    
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
            INSERT INTO records (user_id, date, type, content, pos, meaning) 
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        ''', (user_id, today, record_type, content, pos, meaning))
        record_id = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({
            'message': '添加成功',
            'record': {
                'id': record_id,
                'type': record_type,
                'content': content,
                'pos': pos,
                'meaning': meaning
            }
        }), 201
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': f'添加记录失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/records/<int:record_id>', methods=['PUT'])
@jwt_required()
def update_record(record_id):
    try:
        init_db()
    except Exception as e:
        return jsonify({'error': f'数据库初始化失败: {str(e)}'}), 500
    
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM records WHERE id = %s AND user_id = %s', (record_id, user_id))
        if not cursor.fetchone():
            return jsonify({'error': '记录不存在或无权修改'}), 404
        
        update_fields = []
        update_values = []
        
        if 'pos' in data:
            update_fields.append('pos = %s')
            update_values.append(data['pos'])
        if 'meaning' in data:
            update_fields.append('meaning = %s')
            update_values.append(data['meaning'])
        
        if update_fields:
            update_values.append(record_id)
            cursor.execute(f"UPDATE records SET {', '.join(update_fields)} WHERE id = %s", update_values)
            conn.commit()
        
        return jsonify({'message': '更新成功'})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': f'更新记录失败: {str(e)}'}), 500
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

def fetch_english_definition(word):
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if isinstance(data, list) and len(data) > 0:
            definitions = []
            for entry in data:
                if entry.get('meanings'):
                    for meaning in entry['meanings']:
                        pos = meaning.get('partOfSpeech', '')
                        for defn in meaning.get('definitions', [])[:2]:
                            definition_text = defn.get('definition', '')
                            example = defn.get('example', '')
                            if definition_text:
                                text = f"[{pos}] {definition_text}"
                                if example:
                                    text += f" (e.g., {example})"
                                definitions.append(text)
            return definitions[:4] if definitions else None
    except Exception as e:
        print(f"English definition error: {e}")
    return None

def fetch_chinese_definition(word):
    try:
        url = f"http://dict-co.iciba.com/api/dictionary.php?w={urllib.parse.quote(word)}&key=00000000000000000000000000000&type=json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        definitions = []
        if data.get('word_name'):
            if data.get('symbols') and len(data['symbols']) > 0:
                symbol = data['symbols'][0]
                if symbol.get('parts'):
                    for part in symbol['parts'][:4]:
                        pos = part.get('part', '')
                        means = part.get('means', [])
                        if isinstance(means, list):
                            mean_text = '; '.join([m if isinstance(m, str) else m.get('word_mean', '') for m in means[:3]])
                        else:
                            mean_text = str(means)
                        if pos:
                            definitions.append(f"[{pos}] {mean_text}")
                        else:
                            definitions.append(mean_text)
        return definitions if definitions else None
    except Exception as e:
        print(f"Chinese definition error: {e}")
    
    try:
        url = f"https://api.mojidict.com/parse/functions/union-search-v2"
        req_data = json.dumps({
            "text": word,
            "types": ["102", "103", "104", "106", "403"],
            "isNeedCn": True
        }).encode('utf-8')
        req = urllib.request.Request(url, data=req_data, headers={
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0'
        })
        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode('utf-8'))
        
        definitions = []
        if result.get('result') and result['result'].get('result'):
            for item in result['result']['result'][:4]:
                if item.get('title'):
                    definitions.append(item['title'])
                elif item.get('excerpt'):
                    definitions.append(item['excerpt'])
        return definitions if definitions else None
    except Exception as e:
        print(f"Moji dict error: {e}")
    
    return None

@app.route('/api/dictionary/<word>', methods=['GET'])
def lookup_word(word):
    word = word.strip().lower()
    if not word:
        return jsonify({'error': '单词不能为空'}), 400
    
    result = {
        'word': word,
        'definitions_en': None,
        'definitions_zh': None,
        'pos': []
    }
    
    en_defs = fetch_english_definition(word)
    if en_defs:
        result['definitions_en'] = en_defs
    
    zh_defs = fetch_chinese_definition(word)
    if zh_defs:
        result['definitions_zh'] = zh_defs
    
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        pos_set = set()
        if isinstance(data, list):
            for entry in data:
                if entry.get('meanings'):
                    for meaning in entry['meanings']:
                        pos = meaning.get('partOfSpeech', '').lower()
                        if pos:
                            pos_set.add(pos)
        result['pos'] = list(pos_set)
    except:
        pass
    
    return jsonify(result)

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
            SELECT id, type, content, pos, meaning, created_at 
            FROM records 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        ''', (user_id,))
        rows = cursor.fetchall()
        
        records = []
        for row in rows:
            records.append({
                'id': row['id'],
                'type': row['type'],
                'content': row['content'],
                'pos': row['pos'],
                'meaning': row['meaning'],
                'createdAt': row['created_at'].isoformat() if row['created_at'] else None
            })
        
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
    
    imported_records = data.get('records', [])
    count = 0
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        for item in imported_records:
            content = item.get('content', '')
            record_type = item.get('type', 'words')
            pos = item.get('pos', None)
            meaning = item.get('meaning', None)
            
            if not content:
                continue
            
            today = datetime.now().strftime('%Y/%m/%d')
            
            cursor.execute('''
                SELECT id FROM records 
                WHERE user_id = %s AND content = %s
            ''', (user_id, content))
            
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO records (user_id, date, type, content, pos, meaning) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (user_id, today, record_type, content, pos, meaning))
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

handler = app
