import asyncio
import httpx
import os
import logging
import time
from config import (
    MAX_CONCURRENT_DOWNLOADS, HARDSUB_MAX_RES, HARDSUB_PRESET, 
    HARDSUB_CRF, SUB_FONT, SUB_FONT_SIZE, SUB_FONT_BOLD, 
    SUB_OUTLINE, SUB_OFFSET, WATERMARK_PATH, WATERMARK_SIZE, WATERMARK_OPACITY
)

logger = logging.getLogger(__name__)

class Downloader:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        self.retry_count = 3

    async def download_file(self, stream_info, dest_path, progress_callback=None):
        """Sequential Workflow: Download Raw -> Assemble Sub -> Edit -> Hardsub"""
        async with self.semaphore:
            m3u8_url = stream_info.get("url")
            cookies_dict = stream_info.get("cookies", {})
            if not m3u8_url: return False

            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
            user_agent = "Vigloo/1.1.0 (com.vigloo.android; build:110; Android 13; Model:SM-G998B)"
            
            raw_path = dest_path + ".raw.mp4"
            srt_path = dest_path.replace(".mp4", ".srt")
            
            from config import API_REQUEST_DELAY

            # --- STEP 1: DOWNLOAD RAW VIDEO ---
            logger.info(f"Step 1/3: Downloading Raw Video for {dest_path}")
            if progress_callback: await progress_callback("DOWNLOAD_RAW", 0)
            
            download_success = False
            for attempt in range(self.retry_count):
                try:
                    await asyncio.sleep(API_REQUEST_DELAY) # Avoid API spam
                    cmd = ['ffmpeg', '-y', '-user_agent', user_agent, '-headers', f"Cookie: {cookie_str}\r\n", '-i', m3u8_url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', raw_path]
                    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                    await proc.wait()
                    if proc.returncode == 0 and os.path.exists(raw_path):
                        download_success = True; break
                except Exception as e:
                    logger.warning(f"Raw Download Attempt {attempt+1} failed: {e}")
                await asyncio.sleep(5) # Cooldown before retry
            
            if not download_success: return False

            # --- STEP 2: ASSEMBLE SUBTITLES ---
            logger.info(f"Step 2/3: Assembling Subtitles for {dest_path}")
            if progress_callback: await progress_callback("FETCH_SUB", 0)
            
            has_sub = False
            try:
                async with httpx.AsyncClient(headers={"User-Agent": user_agent}) as client:
                    await asyncio.sleep(API_REQUEST_DELAY)
                    r = await client.get(m3u8_url, cookies=cookies_dict, timeout=10.0)
                    if r.status_code == 200:
                        lines = r.text.splitlines()
                        sub_uri = next((l.split('URI="')[1].split('"')[0] for l in lines if 'TYPE=SUBTITLES' in l and ('"ind"' in l.lower() or '"id"' in l.lower())), None)
                        if not sub_uri:
                            sub_uri = next((l.split('URI="')[1].split('"')[0] for l in lines if 'TYPE=SUBTITLES' in l and '"eng"' in l.lower()), None)
                        
                        if sub_uri:
                            final_sub_url = sub_uri if sub_uri.startswith("http") else m3u8_url.rsplit("/", 1)[0] + "/" + sub_uri
                            await asyncio.sleep(API_REQUEST_DELAY)
                            r_sub = await client.get(final_sub_url, cookies=cookies_dict, timeout=10.0)
                            if r_sub.status_code == 200:
                                sub_lines = r_sub.text.splitlines()
                                bin_content = b""
                                base_sub_url = final_sub_url.rsplit("/", 1)[0] + "/"
                                segments = [l for l in sub_lines if l and not l.startswith("#")]
                                for s_idx, s_line in enumerate(segments):
                                    if s_idx % 10 == 0: await asyncio.sleep(0.2) # Faster jitter for segments
                                    seg_url = s_line if s_line.startswith("http") else base_sub_url + s_line
                                    r_seg = await client.get(seg_url, cookies=cookies_dict, timeout=5.0)
                                    if r_seg.status_code == 200: 
                                        bin_content += r_seg.content
                                
                                temp_bin = srt_path + ".tmp"
                                with open(temp_bin, "wb") as f: f.write(bin_content)
                                sub_cmd = ['ffmpeg', '-y', '-i', temp_bin, srt_path]
                                sub_proc = await asyncio.create_subprocess_exec(*sub_cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                                await sub_proc.wait()
                                if os.path.exists(temp_bin): os.remove(temp_bin)
                                if os.path.exists(srt_path) and os.path.getsize(srt_path) > 100: has_sub = True
            except Exception as e:
                logger.warning(f"Sub Assembly failed: {e}")

            # --- STEP 3: EDIT & HARDSUB ---
            logger.info(f"Step 3/3: Applying Edits & Hardsubbing for {dest_path}")
            if progress_callback: await progress_callback("BURNING", 0)
            
            # Duration for progress
            total_duration = 0
            try:
                probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', raw_path]
                process_probe = await asyncio.create_subprocess_exec(*probe_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout_p, _ = await process_probe.communicate()
                total_duration = float(stdout_p.decode().strip()) if stdout_p else 0
            except: pass

            try:
                video_chain = f"scale=-2:'min({HARDSUB_MAX_RES},ih)'"
                if has_sub:
                    escaped_srt = srt_path.replace("\\", "/").replace(":", "\\:")
                    style = f"FontName={SUB_FONT},FontSize={SUB_FONT_SIZE},PrimaryColour=&HFFFFFF,Bold={SUB_FONT_BOLD},Outline={SUB_OUTLINE},OutlineColour=&H000000,MarginV={SUB_OFFSET}"
                    video_chain += f",subtitles='{escaped_srt}':force_style='{style}'"

                command = ['ffmpeg', '-y', '-i', raw_path]
                if os.path.exists(WATERMARK_PATH):
                    command += ['-i', WATERMARK_PATH]
                    filter_complex = f"[1:v]scale={WATERMARK_SIZE},format=rgba,colorchannelmixer=aa={WATERMARK_OPACITY}[wm];[0:v]{video_chain}[vbase];[vbase][wm]overlay=W-w-20:20[v]"
                    command += ['-filter_complex', filter_complex, '-map', '[v]', '-map', '0:a']
                else:
                    command += ['-vf', video_chain]

                command += ['-c:v', 'libx264', '-preset', HARDSUB_PRESET, '-crf', str(HARDSUB_CRF), '-c:a', 'aac', '-progress', 'pipe:2', dest_path]
                
                process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                
                last_update = 0
                while True:
                    line = await process.stderr.readline()
                    if not line: break
                    line_str = line.decode().strip()
                    if progress_callback and "out_time_ms=" in line_str:
                        try:
                            time_ms = int(line_str.split("=")[1])
                            current_sec = time_ms / 1000000
                            if time.time() - last_update > 2:
                                percent = min(99, (current_sec / total_duration) * 100) if total_duration > 0 else 50
                                await progress_callback("BURNING", percent)
                                last_update = time.time()
                        except: pass

                await process.wait()
                if process.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                    if os.path.exists(raw_path): os.remove(raw_path)
                    if os.path.exists(srt_path): os.remove(srt_path)
                    return True
            except Exception as e:
                logger.error(f"Hardsub/Edit failed: {e}")
            if os.path.exists(raw_path): os.remove(raw_path)
            return False

downloader = Downloader()
