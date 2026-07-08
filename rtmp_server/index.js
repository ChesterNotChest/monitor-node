/**
 * Embedded RTMP server for local STREAM_DEBUG verification.
 *
 * Accepts ffmpeg RTMP pushes on  rtmp://127.0.0.1:1935/live/<stream-key>
 * Serves RTMP pulls on the same address for OBS / VLC.
 */

const NodeMediaServer = require("node-media-server");

const config = {
  rtmp: {
    port: 1935,
    chunk_size: 60000,
    gop_cache: true,
    ping: 30,
    ping_timeout: 60,
  },
};

const nms = new NodeMediaServer(config);

// Signal handling — must be registered BEFORE nms.run()
process.on("SIGINT", () => { nms.stop(); process.exit(0); });
process.on("SIGTERM", () => { nms.stop(); process.exit(0); });

// nms.run() blocks — the line above runs first, then the event loop starts.
console.log("[RTMP server] rtmp://127.0.0.1:1935/live");
nms.run();
