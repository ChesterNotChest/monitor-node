#!/usr/bin/env node
/**
 * 假 WSS 服务器 — DEBUG_WSS 模式下的本地开发调试工具
 *
 * 功能:
 *   1. 启动 WebSocket 服务端 ws://localhost:<WSS_PORT>
 *   2. 接受 Node 的 WSS 连接请求
 *   3. 识别身份认证: "debug-token-fixed" → auth_ack (node_id: "debug-node-001")
 *   4. 支持发送 get_devices 和 update_stream 指令
 *   5. 心跳日志（不做响应）
 *   6. 交互式 REPL
 *
 * 用法:
 *   cd tests/mock_server && npm install && node mock_server.js
 *   # 或指定端口: WSS_PORT=9443 node mock_server.js
 *
 * REPL 命令:
 *   get_devices              — 发送 get_devices 指令
 *   update_stream <id> true  — 启用指定设备推流
 *   update_stream <id> false — 停用指定设备推流
 *   help                     — 显示帮助
 *   quit                     — 退出
 */

const WebSocket = require('ws');

const PORT = parseInt(process.env.WSS_PORT || '8443', 10);
const DEBUG_TOKEN = 'debug-token-fixed';
const DEBUG_NODE_ID = 'debug-node-001';

// ---------------------------------------------------------------------------
// 连接管理
// ---------------------------------------------------------------------------

/** @type {Map<string, { ws: WebSocket, nodeId: string, authenticated: boolean }>} */
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
log(`固定 Token: "${DEBUG_TOKEN}"`);
log(`固定 NodeID: "${DEBUG_NODE_ID}"`);
log('');

wss.on('connection', (ws) => {
  const clientId = `client-${++clientCounter}`;
  clients.set(clientId, { ws, nodeId: null, authenticated: false });
  log(`[${clientId}] 新连接`);

  ws.on('message', (raw) => {
    let data;
    try {
      data = JSON.parse(raw.toString());
    } catch {
      log(`[${clientId}] 收到无效 JSON: ${raw.toString().substring(0, 100)}`);
      return;
    }

    const type = data.type || '';
    const client = clients.get(clientId);

    // ---- 身份认证 ----
    if (type === 'auth') {
      const token = data.token || '';
      if (token === DEBUG_TOKEN) {
        client.nodeId = DEBUG_NODE_ID;
        client.authenticated = true;
        const ack = { type: 'auth_ack', node_id: DEBUG_NODE_ID };
        ws.send(JSON.stringify(ack));
        log(`[${clientId}] 认证成功 → NodeID: ${DEBUG_NODE_ID}`);
        log(`[${clientId}] ← 发送: ${JSON.stringify(ack)}`);

        // 自动发送一条 get_devices 验证连通性
        setTimeout(() => {
          if (client.authenticated && ws.readyState === WebSocket.OPEN) {
            const cmd = { command: 'get_devices', node_id: DEBUG_NODE_ID };
            ws.send(JSON.stringify(cmd));
            log(`[${clientId}] → 自动发送: ${JSON.stringify(cmd)}`);
          }
        }, 500);
      } else {
        const err = { type: 'auth_error', message: 'invalid token' };
        ws.send(JSON.stringify(err));
        log(`[${clientId}] 认证拒绝: token="${token}"`);
        log(`[${clientId}] ← 发送: ${JSON.stringify(err)}`);
        ws.close();
      }
      return;
    }

    // ---- 心跳 ----
    if (type === 'heartbeat') {
      log(`[${clientId}] 收到心跳 ♡`);
      return;
    }

    // ---- 指令响应 ----
    if (data.type && data.type.endsWith('_response')) {
      log(`[${clientId}] 收到响应: ${JSON.stringify(data)}`);
      return;
    }

    // ---- 错误 ----
    if (type === 'error') {
      log(`[${clientId}] 收到错误: ${data.message || JSON.stringify(data)}`);
      return;
    }

    // ---- 其他 ----
    log(`[${clientId}] 收到未知消息: ${JSON.stringify(data)}`);
  });

  ws.on('close', () => {
    log(`[${clientId}] 连接断开`);
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
      console.log('  get_devices              — 向所有已认证 Node 发送 get_devices 指令');
      console.log('  update_stream <id> true  — 启用指定设备推流');
      console.log('  update_stream <id> false — 停用指定设备推流');
      console.log('  list                     — 列出所有已连接的客户端');
      console.log('  help                     — 显示此帮助');
      console.log('  quit / exit              — 退出');
      console.log('');
      break;

    case 'get_devices':
      broadcastCommand({ command: 'get_devices', node_id: DEBUG_NODE_ID });
      break;

    case 'update_stream':
      if (parts.length < 3) {
        console.log('用法: update_stream <device_id> true|false');
        break;
      }
      broadcastCommand({
        command: 'update_stream',
        node_id: DEBUG_NODE_ID,
        device_id: parts[1],
        enabled: parts[2] === 'true',
      });
      break;

    case 'list':
      console.log('');
      if (clients.size === 0) {
        console.log('  无已连接客户端');
      } else {
        console.log(`  已连接客户端 (${clients.size}):`);
        for (const [id, client] of clients) {
          console.log(`    ${id}: nodeId=${client.nodeId || '(pending)'}, auth=${client.authenticated}`);
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
