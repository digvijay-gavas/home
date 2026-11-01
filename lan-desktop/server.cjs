const https = require('https');
const fs = require('fs');
const path = require('path');
const net = require('net');
const { WebSocketServer, createWebSocketStream } = require('ws');
const root = path.join(__dirname, 'noVNC-1.6.0');
const allowed = ip => ip === '127.0.0.1' || /^192\.168\.0\.\d+$/.test(ip || '');
const server = https.createServer({key: fs.readFileSync(path.join(__dirname,'server.key')),cert:fs.readFileSync(path.join(__dirname,'server.crt'))}, (req,res) => {
  if (!allowed(req.socket.remoteAddress)) { res.writeHead(403); return res.end(); }
  let url;
  try { url = decodeURIComponent(new URL(req.url,'https://localhost').pathname); } catch { res.writeHead(400); return res.end(); }
  if (url === '/') {res.writeHead(302,{Location:'/vnc.html?autoconnect=1&resize=scale&show_dot=1&quality=4&compression=1&path=websockify'});return res.end();}
  const file = path.resolve(root,'.'+url);
  if (!file.startsWith(root+path.sep)) {res.writeHead(403);return res.end();}
  fs.readFile(file,(err,data)=>{if(err){res.writeHead(404);return res.end();}res.writeHead(200,{'Content-Type':({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.json':'application/json'})[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(data);});
});
// VNC already compresses its screen updates; avoid another compression layer.
const wss = new WebSocketServer({noServer:true,maxPayload:4*1024*1024,perMessageDeflate:false});
server.on('upgrade',(req,socket,head)=>{
  if (!allowed(socket.remoteAddress) || req.url !== '/websockify') return socket.destroy();
  if(req.headers.origin && req.headers.origin !== 'https://'+req.headers.host) return socket.destroy();
  socket.setNoDelay(true);
  wss.handleUpgrade(req,socket,head,ws=>wss.emit('connection',ws));
});
wss.on('connection',ws=>{
  const tcp=net.connect(5900,'127.0.0.1');
  tcp.setNoDelay(true);
  const stream=createWebSocketStream(ws);
  // Stream backpressure prevents unchecked frame queues on slower clients.
  tcp.pipe(stream).pipe(tcp);
  const cleanup=()=>{tcp.destroy();stream.destroy();};
  tcp.on('error',cleanup);tcp.on('close',cleanup);
  stream.on('error',cleanup);stream.on('close',()=>tcp.destroy());
});
server.listen(8443,'0.0.0.0',()=>console.log('LAN Desktop listening on HTTPS port 8443'));
