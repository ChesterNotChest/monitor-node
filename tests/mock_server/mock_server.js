#!/usr/bin/env node
/**
 * 假 WSS 服务器 — DEBUG_WSS 模式下的本地开发调试工具
 *
 * 协议对齐 Server 侧的 node-wss-connection spec:
 *   Node → Server:  {"token": "xxx"}
 *   Server → Node:  {"session_token": "sess_xxx", "videos": [...], "audios": [...]}
 *   Server → Node:  {"command": "UPDATE_STREAM", "device_type": "video", "device_id": 1, "enable": true}
 *   Node → Server:  {"success": true, "message": "推流已启动"}
 *
 * 用法:
 *   cd tests/mock_server && npm install && node mock_server.js
 *
 * REPL 命令:
 *   update_stream video 1 true   — 启用视频设备 (device_id=1)
 *   update_stream audio 2 false  — 停用音频设备 (device_id=2)
 *   list                         — 列出已连接客户端
 *   help                         — 显示帮助
 *   quit                         — 退出
 */

const WebSocket = require('ws');

const PORT = parseInt(process.env.WSS_PORT || '8443', 10);
const DEBUG_TOKEN = 'debug-token-fixed';
const DEBUG_SESSION_TOKEN = 'sess-debug-000000000001';

// 假设备列表（模拟 Server 数据库中该 Node 下的设备）
const DEBUG_VIDEOS = [
  { id: 1, name: 'USB2.0 HD UVC WebCam' },
  { id: 2, name: 'OBS Virtual Camera' },
];
const DEBUG_AUDIOS = [
  { id: 3, name: '麦克风阵列 (Realtek(R) Audio)' },
];

// ---------------------------------------------------------------------------
// 连接管理
// ---------------------------------------------------------------------------

/** @type {Map<string, { ws: WebSocket, sessionToken: string, authenticated: boolean }>} */
const clients = new Map();
let clientCounter = 0;

function timestamp() {
  return new Date().toISOString();
}

function log(msg) {
  console.log(`[${timestamp()}] ${msg}`);
}

// ---------------------------------------------------------------------------
// WebSocket 服务器
// ---------------------------------------------------------------------------

const wss = new WebSocket.Server({ port: PORT });

log(`假 WSS 服务器已启动: ws://localhost:${PORT}`);
log(`协议: Server-aligned (token → session_token + device maps → UPDATE_STREAM)`);
log(`固定 Token: "${DEBUG_TOKEN}"`);
log(`固定 Session: "${DEBUG_SESSION_TOKEN}"`);
log(`假设备: ${DEBUG_VIDEOS.length} video, ${DEBUG_AUDIOS.length} audio`);
log('');

wss.on('connection', (ws) => {
  const clientId = `client-${++clientCounter}`;
  clients.set(clientId, { ws, sessionToken: null, authenticated: false });
  log(`[${clientId}] 新连接`);

  ws.on('message', (raw) => {
    let data;
    try {
      data = JSON.parse(raw.toString());
    } catch {
      log(`[${clientId}] 收到无效 JSON: ${raw.toString().substring(0, 100)}`);
      return;
    }

    const client = clients.get(clientId);

    // ---- 身份认证: {"token": "xxx"} ----
    if (data.token && !client.authenticated) {
      const token = data.token;
      if (token === DEBUG_TOKEN) {
        client.sessionToken = DEBUG_SESSION_TOKEN;
        client.authenticated = true;
        const ack = {
          session_token: DEBUG_SESSION_TOKEN,
          videos: DEBUG_VIDEOS,
          audios: DEBUG_AUDIOS,
        };
        ws.send(JSON.stringify(ack));
        log(`[${clientId}] 认证成功 → session=${DEBUG_SESSION_TOKEN}`);
        log(`[${clientId}] ← 发送: ${JSON.stringify(ack)}`);

        // 自动发送一条 UPDATE_STREAM 验证连通性
        setTimeout(() => {
          if (client.authenticated && ws.readyState === WebSocket.OPEN) {
            const cmd = {
              command: 'UPDATE_STREAM',
              device_type: 'video',
              device_id: 1,
              enable: true,
            };
            ws.send(JSON.stringify(cmd));
            log(`[${clientId}] → 自动发送: ${JSON.stringify(cmd)}`);
          }
        }, 500);
      } else {
        log(`[${clientId}] 认证拒绝: token="${token}"`);
        ws.close();
      }
      return;
    }

    // ---- 心跳 ----
    if (data.type === 'heartbeat') {
      log(`[${clientId}] 收到心跳 ♡`);
      return;
    }

    // ---- Node 响应: {"success": true/false, "message": "..."} ----
    if (data.hasOwnProperty('success')) {
      log(`[${clientId}] 收到响应: ${JSON.stringify(data)}`);
      return;
    }

    // ---- 其他 ----
    log(`[${clientId}] 收到未知消息: ${JSON.stringify(data)}`);
  });

  ws.on('close', () => {
    log(`[${clientId}] 连接断开 (session=${clients.get(clientId)?.sessionToken || '(pending)'})`);
    clients.delete(clientId);
  });

  ws.on('error', (err) => {
    log(`[${clientId}] 连接错误: ${err.message}`);
  });
});

// ---------------------------------------------------------------------------
// REPL
// ---------------------------------------------------------------------------

const readline = require('readline');
const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  prompt: '> ',
});

console.log('交互式 REPL 已就绪。输入 help 查看命令。');
console.log('');
rl.prompt();

rl.on('line', (line) => {
  const input = line.trim();

  if (!input) {
    rl.prompt();
    return;
  }

  const parts = input.split(/\s+/);
  const cmd = parts[0].toLowerCase();

  switch (cmd) {
    case 'help':
      console.log('');
      console.log('可用命令:');
      console.log('  update_stream video <id> true   — 启用视频设备推流');
      console.log('  update_stream audio <id> false  — 停用音频设备推流');
      console.log('  list                            — 列出所有已连接的客户端');
      console.log('  help                            — 显示此帮助');
      console.log('  quit / exit                     — 退出');
      console.log('');
      console.log('假设备列表:');
      for (const v of DEBUG_VIDEOS) {
        console.log(`  video  id=${v.id}  ${v.name}`);
      }
      for (const a of DEBUG_AUDIOS) {
        console.log(`  audio  id=${a.id}  ${a.name}`);
      }
      console.log('');
      break;

    case 'update_stream':
      if (parts.length < 4) {
        console.log('用法: update_stream <video|audio> <device_id> <true|false>');
        console.log('示例: update_stream video 1 true');
        break;
      }
      broadcastCommand({
        command: 'UPDATE_STREAM',
        device_type: parts[1],
        device_id: parseInt(parts[2], 10),
        enable: parts[3] === 'true',
      });
      break;

    case 'list':
      console.log('');
      if (clients.size === 0) {
        console.log('  无已连接客户端');
      } else {
        console.log(`  已连接客户端 (${clients.size}):`);
        for (const [id, client] of clients) {
          console.log(`    ${id}: session=${client.sessionToken || '(pending)'}, auth=${client.authenticated}`);
        }
      }
      console.log('');
      break;

    case 'quit':
    case 'exit':
      console.log('正在关闭...');
      wss.close();
      rl.close();
      process.exit(0);
      break;

    default:
      console.log(`未知命令: "${cmd}"。输入 help 查看帮助。`);
  }

  rl.prompt();
});

rl.on('close', () => {
  process.exit(0);
});

// ---------------------------------------------------------------------------
// 辅助函数
// ---------------------------------------------------------------------------

function broadcastCommand(cmdObj) {
  const msg = JSON.stringify(cmdObj);
  let sent = 0;
  for (const [id, client] of clients) {
    if (client.authenticated && client.ws.readyState === WebSocket.OPEN) {
      client.ws.send(msg);
      log(`[${id}] → 发送: ${msg}`);
      sent++;
    }
  }
  if (sent === 0) {
    console.log('没有已认证的客户端可发送。');
  } else {
    console.log(`已发送给 ${sent} 个客户端。`);
  }
}
