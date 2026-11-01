const fs=require('fs'),path=require('path'),https=require('https');
const {WebSocket}=require('ws');
(async()=>{
 const source=fs.readFileSync(path.join(__dirname,'noVNC-1.6.0/core/crypto/des.js'),'utf8').replace(/export class /g,'class ');
 const {DESECBCipher}=new Function(source+';return {DESECBCipher};')();
 const password=fs.readFileSync(path.join(__dirname,'credentials.txt'),'utf8').match(/Desktop password: (\S+)/)[1];
 await new Promise((resolve,reject)=>https.get('https://192.168.0.12:8443/vnc.html',{rejectUnauthorized:false},res=>{res.resume();if(res.statusCode===200)resolve();else reject(Error('HTTP '+res.statusCode));}).on('error',reject));
 const ws=new WebSocket('wss://192.168.0.12:8443/websockify',{rejectUnauthorized:false});
 let buf=Buffer.alloc(0),stage=0,rectangles=0,updates=0,request;
 const started=Date.now();
 const timer=setTimeout(()=>{console.error('Timed out waiting for visible screen pixels; updates received:',updates);ws.terminate();process.exit(1);},15000);
 const requestUpdate=()=>{if(ws.readyState===WebSocket.OPEN)ws.send(request);};
 ws.on('error',e=>{console.error(e.message);process.exit(1);});
 ws.on('message',data=>{
  if(stage===7)return;
  buf=Buffer.concat([buf,data]);
  while(true){
   if(stage===0){if(buf.length<12)return;console.log('VNC protocol:',buf.subarray(0,12).toString().trim());buf=buf.subarray(12);ws.send(Buffer.from('RFB 003.008\n'));stage=1;}
   else if(stage===1){if(buf.length<1||buf.length<buf[0]+1)return;const n=buf[0];if(!buf.subarray(1,n+1).includes(2))throw Error('Password auth unavailable');buf=buf.subarray(n+1);ws.send(Buffer.from([2]));stage=2;}
   else if(stage===2){if(buf.length<16)return;const key=DESECBCipher.importKey([...password].map(c=>c.charCodeAt(0)));ws.send(key.encrypt({},buf.subarray(0,16)));buf=buf.subarray(16);stage=3;}
   else if(stage===3){if(buf.length<4)return;if(buf.readUInt32BE(0)!==0)throw Error('Authentication failed');buf=buf.subarray(4);ws.send(Buffer.from([1]));stage=4;}
   else if(stage===4){
    if(buf.length<24)return;
    const nameLength=buf.readUInt32BE(20);if(buf.length<24+nameLength)return;
    const width=buf.readUInt16BE(0),height=buf.readUInt16BE(2);
    console.log('Authenticated desktop:',width+'x'+height);
    buf=buf.subarray(24+nameLength);
    // Request standard 32-bit pixels and raw rectangles; never send input.
    ws.send(Buffer.from([0,0,0,0,32,24,0,1,0,255,0,255,0,255,16,8,0,0,0,0]));
    ws.send(Buffer.from([2,0,0,1,0,0,0,0]));
    request=Buffer.alloc(10);request[0]=3;request.writeUInt16BE(0,2);request.writeUInt16BE(0,4);request.writeUInt16BE(Math.min(width,640),6);request.writeUInt16BE(Math.min(height,480),8);requestUpdate();stage=5;
   }
   else if(stage===5){
    if(buf.length<4)return;
    if(buf[0]===2){buf=buf.subarray(1);continue;}
    if(buf[0]!==0)throw Error('Unexpected framebuffer message: '+buf[0]);
    rectangles=buf.readUInt16BE(2);buf=buf.subarray(4);updates++;
    if(rectangles===0){setTimeout(requestUpdate,150);return;}
    stage=6;
   }
   else {
    if(buf.length<12)return;
    const width=buf.readUInt16BE(4),height=buf.readUInt16BE(6),encoding=buf.readInt32BE(8);
    if(encoding!==0)throw Error('Unexpected encoding: '+encoding);
    const length=width*height*4;if(buf.length<12+length)return;
    const pixels=buf.subarray(12,12+length);const colors=new Set();let nonBlack=0;
    for(let i=0;i<pixels.length;i+=4){const rgb=pixels.readUInt32LE(i)&0xffffff;colors.add(rgb);if(rgb)nonBlack++;}
    buf=buf.subarray(12+length);rectangles--;
    if(nonBlack>0){
     console.log('Visible screen update:',width+'x'+height,'unique colors:',colors.size,'non-black pixels:',nonBlack,'startup ms:',Date.now()-started,'updates:',updates);
     clearTimeout(timer);stage=7;ws.close();return;
    }
    // Capture can initially return a blank placeholder. Check later updates too.
    if(rectangles===0){stage=5;setTimeout(requestUpdate,150);}
   }
  }
 });
})().catch(e=>{console.error(e);process.exit(1);});
