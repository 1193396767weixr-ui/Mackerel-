# 英语每日记录

一个跨平台的英语学习记录应用，支持单词、词组、句式的记录和管理。

## 功能特点

- 用户注册/登录系统
- 自动识别单词、词组、句式
- 自动识别词性（名词、动词、形容词等）
- 按日期记录学习内容
- 全部积累页面支持乱序/顺序切换
- 数据导出/导入功能
- 支持桌面和移动端使用

## 快速开始

### 方式一：直接运行（开发模式）

1. 安装后端依赖：
```bash
cd backend
pip install -r requirements.txt
```

2. 启动后端服务：
```bash
python app.py
```

3. 用浏览器打开 `frontend/index.html` 或访问 `http://localhost:5000`

### 方式二：打包成桌面应用

1. 运行打包脚本：
```bash
build.bat
```

2. 生成的可执行文件位于 `dist/英语每日记录.exe`

### 方式三：部署到服务器

1. 将 `backend` 文件夹部署到服务器
2. 安装依赖并运行 Flask 应用
3. 将 `frontend/index.html` 中的 `API_BASE` 改为服务器地址
4. 使用 Nginx 或其他 Web 服务器托管前端页面

## 移动端使用

### iOS (iPhone/iPad)

1. 将前端页面部署到 Web 服务器（如 GitHub Pages、Vercel 等）
2. 用 Safari 打开网址
3. 点击分享按钮 → "添加到主屏幕"
4. 即可像原生 App 一样使用

### Android

1. 将前端页面部署到 Web 服务器
2. 用 Chrome 打开网址
3. 点击菜单 → "添加到主屏幕"

### 打包成移动 App

可以使用以下方案将 Web 应用打包成原生 App：

- **Capacitor** (推荐): 支持 iOS 和 Android
- **Cordova**: 跨平台打包工具
- **React Native WebView**: 嵌入 WebView

## 项目结构

```
我的英语软件/
├── backend/
│   ├── app.py           # Flask 后端服务
│   ├── requirements.txt # Python 依赖
│   └── english_tracker.db # SQLite 数据库（自动生成）
├── frontend/
│   └── index.html       # 前端页面
├── run.py               # 启动脚本
├── build.bat            # Windows 打包脚本
├── english_tracker.spec # PyInstaller 配置
└── README.md            # 说明文档
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/register | POST | 用户注册 |
| /api/login | POST | 用户登录 |
| /api/records | GET | 获取所有记录 |
| /api/records | POST | 添加记录 |
| /api/records/<id> | DELETE | 删除记录 |
| /api/records/export | GET | 导出数据 |
| /api/records/import | POST | 导入数据 |
| /api/user/info | GET | 获取用户信息 |

## 技术栈

- **后端**: Flask + SQLite + JWT 认证
- **前端**: Vue 3 + Element Plus
- **打包**: PyInstaller (桌面) / Capacitor (移动)

## 注意事项

1. 首次运行会自动创建数据库
2. 默认 JWT 密钥建议在生产环境中修改
3. 数据库文件 `english_tracker.db` 包含所有用户数据，请定期备份
