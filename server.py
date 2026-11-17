import os
import sys
import json
import subprocess
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
STATIC_DIR = os.path.join(BASE_DIR, "static")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

class TikTokEnhancerHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.serve_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
        elif path.startswith("/output/"):
            filename = os.path.basename(path)
            file_path = os.path.join(OUTPUT_DIR, filename)
            self.serve_file(file_path, "video/mp4")
        elif path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            file_path = os.path.join(STATIC_DIR, rel_path)
            self.serve_file(file_path, "text/plain")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def serve_file(self, file_path, content_type):
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"File not found")
            return

        size = os.path.getsize(file_path)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                self.wfile.write(chunk)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/enhance":
            self.handle_enhance()
        elif path == "/api/tiktok-upload":
            self.handle_tiktok_upload()
        else:
            self.send_response(404)
            self.end_headers()

    def handle_enhance(self):
        try:
            content_type = self.headers.get('Content-Type', '')
            if not content_type.startswith('multipart/form-data'):
                self.send_json({"error": "Content-Type must be multipart/form-data"}, 400)
                return

            boundary = content_type.split("boundary=")[-1].strip()
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            parts = body.split(b"--" + boundary.encode())
            video_bytes = None
            preset = "4k_ultra"
            video_filename = "input_video.mp4"

            for part in parts:
                if b'Content-Disposition' in part:
                    head, val = part.split(b"\r\n\r\n", 1)
                    head_str = head.decode('utf-8', errors='ignore')
                    val = val.rstrip(b"\r\n")
                    if 'name="video"' in head_str:
                        if 'filename="' in head_str:
                            import re
                            match = re.search(r'filename="([^"]+)"', head_str)
                            if match:
                                video_filename = match.group(1)
                        video_bytes = val
                    elif 'name="preset"' in head_str:
                        preset = val.decode('utf-8', errors='ignore').strip()

            if not video_bytes or len(video_bytes) < 100:
                self.send_json({"error": "Tiada fail video dijumpai atau fail kosong."}, 400)
                return

            input_path = os.path.join(UPLOAD_DIR, f"in_{os.path.basename(video_filename)}")
            output_name = f"enhanced_{os.path.splitext(os.path.basename(video_filename))[0]}.mp4"
            output_path = os.path.join(OUTPUT_DIR, output_name)

            with open(input_path, "wb") as f:
                f.write(video_bytes)

            success, msg = self.process_video(input_path, output_path, preset)
            if not success:
                self.send_json({"error": f"Gagal proses video: {msg}"}, 500)
                return

            self.send_json({
                "status": "success",
                "message": "Video berjaya ditingkatkan kualiti!",
                "download_url": f"/output/{output_name}",
                "filename": output_name,
                "preset": preset
            })
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def process_video(self, input_path, output_path, preset):
        # Profil penambahbaikan kualiti TikTok
        if preset == "4k_ultra":
            # 4K Upscale (2160x3840 portrait), contrast/saturation boost, unsharp detail mask
            vf = "scale=2160:3840:flags=lanczos,unsharp=5:5:1.2:5:5:0.0,eq=contrast=1.08:brightness=0.01:saturation=1.12"
            bitrate = "18M"
        elif preset == "2k_crisp":
            # 2K / 1440p (1440x2560 portrait)
            vf = "scale=1440:2560:flags=lanczos,unsharp=5:5:1.0:5:5:0.0,eq=contrast=1.06:brightness=0.01:saturation=1.10"
            bitrate = "12M"
        else: # "1080p_pro"
            # 1080x1920 optimum TikTok high-bitrate
            vf = "scale=1080:1920:flags=lanczos,unsharp=3:3:0.8:3:3:0.0,eq=contrast=1.05:saturation=1.08"
            bitrate = "8M"

        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "17",
            "-b:v", bitrate,
            "-maxrate", bitrate,
            "-bufsize", f"{int(bitrate[:-1])*2}M",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            output_path
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            return False, res.stderr[-500:]
        return True, "OK"

    def handle_tiktok_upload(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            video_filename = data.get("filename")
            caption = data.get("caption", "#fyp #trending")
            access_token = data.get("access_token", "")

            video_path = os.path.join(OUTPUT_DIR, video_filename)
            if not os.path.exists(video_path):
                self.send_json({"error": "Fail video tidak wujud."}, 404)
                return

            if not access_token:
                # Mode Simulasi / Direct Guidance jika tiada TikTok Dev Token
                self.send_json({
                    "status": "ready_to_share",
                    "mode": "share_url",
                    "message": "Video siap sepenuhnya dengan format optimum TikTok!",
                    "video_url": f"/output/{video_filename}",
                    "caption": caption,
                    "tip": "Gunakan butang 'Buka TikTok & Post' di bawah untuk muat naik terus ke akaun anda!"
                })
                return

            # Direct Post via TikTok Content Posting API jika token dibekalkan
            # 1. Init API
            init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
            video_size = os.path.getsize(video_path)
            init_payload = json.dumps({
                "post_info": {
                    "title": caption,
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": video_size,
                    "total_chunk_count": 1
                }
            }).encode('utf-8')

            req = urllib.request.Request(init_url, data=init_payload, headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8"
            })

            try:
                with urllib.request.urlopen(req) as resp:
                    resp_data = json.loads(resp.read().decode('utf-8'))
                    if resp_data.get("error", {}).get("code") == "ok":
                        upload_url = resp_data["data"]["upload_url"]
                        publish_id = resp_data["data"]["publish_id"]

                        # 2. Upload video binary
                        with open(video_path, "rb") as vf:
                            video_bin = vf.read()

                        put_req = urllib.request.Request(upload_url, data=video_bin, method="PUT", headers={
                            "Content-Type": "video/mp4",
                            "Content-Length": str(video_size),
                            "Content-Range": f"bytes 0-{video_size - 1}/{video_size}"
                        })
                        with urllib.request.urlopen(put_req) as put_resp:
                            self.send_json({
                                "status": "success",
                                "message": "Berjaya di-upload terus ke akaun TikTok!",
                                "publish_id": publish_id
                            })
                            return
                    else:
                        self.send_json({"error": f"TikTok API Error: {resp_data.get('error', {}).get('message')}"}, 400)
                        return
            except urllib.error.HTTPError as he:
                err_body = he.read().decode('utf-8', errors='ignore')
                self.send_json({"error": f"TikTok HTTP {he.code}: {err_body}"}, 400)
                return

        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

if __name__ == "__main__":
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, TikTokEnhancerHandler)
    print(f"Server berjalan di: http://localhost:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer dihentikan.")
